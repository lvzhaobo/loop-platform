"""Loop 编排层主循环。

职责:从需求池自主取任务 → 子进程调用引擎生成+验证 → 回写状态到来源。
引擎被当作黑盒调用(python engine/generate.py),本层不 import 其内部代码,
也不改其任何产物。引擎结果通过退出码 + output/runs.jsonl 回读。

唯一需求来源:飞书云文档 / 直接文本。通过 feishu_docs.json 统一管理,
飞书文档执行时实时拉取,直接文本已预存。

用法: python pipeline/orchestrator.py
环境: 见 config.env
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 仓库根
ENGINE = "engine"
RUNS_JSONL = os.path.join(ROOT, "output", "runs.jsonl")
SPEC_DIR = os.path.join(ROOT, "data", "specs")

# 兼容直接执行和 python -m pipeline.orchestrator；不再依赖不存在的 pipeline/adapters。
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "engine", "tools"))
from adapters.base import Task  # noqa: E402
from adapters.feishu_adapter import FeishuAdapter  # noqa: E402
from pipeline import deployer, publisher  # noqa: E402
import tracer  # noqa: E402


def run_engine(case: str, mode: str) -> int:
    """子进程调用引擎:仅跑指定单个用例。返回引擎退出码(0=全部通过)。"""
    env = os.environ.copy()
    env["HARNESS_CASES"] = case
    env["HARNESS_MODE"] = mode
    print(f"[loop] → 调用引擎:case={case} mode={mode}")
    proc = subprocess.run([sys.executable, f"{ENGINE}/generate.py"], cwd=ROOT, env=env)
    return proc.returncode


def latest_run(case: str) -> dict:
    """从 output/runs.jsonl 回读该用例最近一次运行记录。"""
    if not os.path.exists(RUNS_JSONL):
        return {}
    last: dict = {}
    with open(RUNS_JSONL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("case") == case:
                last = rec
    return last


def save_spec(task: Task) -> str:
    """把来源拉到的 Spec 落地为文件,便于查看与后续 spec 编译。"""
    os.makedirs(SPEC_DIR, exist_ok=True)
    path = os.path.join(SPEC_DIR, f"{task.id}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# {task.title}\n\n> 来源:{task.source}  id:{task.id}\n\n")
        f.write(task.spec_text or "")
    return os.path.relpath(path, ROOT)


def slugify_case(task_id: str) -> str:
    """把任务 id 规整成可作目录/用例名的 slug(仅字母数字下划线)。"""
    s = re.sub(r"[^0-9A-Za-z]+", "_", task_id).strip("_").lower()
    return s or "case"


def case_available(case: str) -> bool:
    """case 是否可跑:已编译出契约即可。"""
    cdir = os.path.join(ROOT, "cases", case)
    return os.path.exists(os.path.join(cdir, "spec", "manifest.json"))


def compile_from_spec(task: Task) -> tuple[str | None, str, str | None]:
    """把自由文本 Spec 交给编译层。

    优先走 MumuSpec 六轮调度器（--mumuspec），失败时回退简单 spec 编译。
    """
    spec_path = save_spec(task)
    name = slugify_case(task.id)

    # 尝试 MumuSpec 编译（六轮 Skill 调度器）
    mumu_cmd = [sys.executable, f"{ENGINE}/tools/mumuspec_compiler.py",
                "--name", name, "--input", os.path.join(ROOT, spec_path)]
    print(f"[loop] ⚙ [{task.id}] MumuSpec 编译:{name} ← {spec_path}")
    proc = subprocess.run(mumu_cmd, cwd=ROOT)
    if proc.returncode == 0 and case_available(name):
        print(f"[loop] ✓ [{task.id}] MumuSpec 编译成功 → case={name}")
        return name, spec_path, None

    # 回退：简单 spec 编译
    print(f"[loop] ⚠ [{task.id}] MumuSpec 失败，回退简单 spec 编译")
    cmd = [sys.executable, f"{ENGINE}/tools/spec_compiler.py",
           "--name", name, "--input", os.path.join(ROOT, spec_path)]
    cmd += ["--archetype", "spec"]
    proc = subprocess.run(cmd, cwd=ROOT)
    if proc.returncode == 0 and case_available(name):
        return name, spec_path, None
    return None, spec_path, "spec 编译或契约门禁未通过(详见上方输出)"


def process(task: Task, adapter, mode: str) -> bool:
    now = time.strftime("%Y-%m-%d %H:%M:%S")

    if task.extra.get("fetch_error"):
        adapter.report(task.id, "failed", finished_at=now,
                        reason=f"来源拉取失败:{task.extra['fetch_error']}")
        print(f"[loop] ✗ [{task.id}] 来源拉取失败")
        return False

    if not task.case and task.spec_text:
        name, spec_path, err = compile_from_spec(task)
        if name:
            task.case = name
            print(f"[loop] ⚙ [{task.id}] Spec 已编译为合规 case={name},进入生成链路")
        else:
            adapter.report(task.id, "fetched", finished_at=now, spec_path=spec_path,
                           note=f"Spec 已落地;spec 编译未通过门禁,暂不生成:{err}")
            print(f"[loop] ● [{task.id}] Spec 编译未通过,标 fetched → {spec_path}")
            return True

    if task.case:
        if not case_available(task.case):
            adapter.report(task.id, "failed", finished_at=now,
                            reason=f"未知 case '{task.case}'(cases/ 下无 case.json)")
            print(f"[loop] ✗ [{task.id}] 未知 case={task.case}")
            return False
        adapter.report(task.id, "running", started_at=now)
        code = run_engine(task.case, mode)
        run = latest_run(task.case)
        fin = time.strftime("%Y-%m-%d %H:%M:%S")
        if code == 0:
            fields = dict(output_dir=run.get("dir"), attempts=run.get("attempts"),
                          determinism=run.get("determinism"))
            print(f"[loop] ✓ [{task.id}] 完成 → {run.get('dir')}")
            if os.environ.get("HARNESS_AUTOCOMMIT") == "1" and run.get("dir"):
                prefix = os.environ.get("HARNESS_GIT_BRANCH_PREFIX", "harness")
                stamp = time.strftime("%Y%m%d-%H%M%S")
                branch = f"{prefix}/{task.id}-{stamp}"
                pub = publisher.publish(
                    os.path.join(ROOT, run["dir"]), branch,
                    message=f"[{task.id}] {task.title} (case={task.case})",
                )
                fields["publish"] = pub
                if pub.get("pushed"):
                    where = pub.get("path") or branch
                    print(f"[loop] ⇪ [{task.id}] 已推送 {pub['remote']} → {where} ({pub.get('commit')})")
                    if os.environ.get("ECS_DEPLOY") == "1":
                        app_port = pub.get("port") or os.environ.get("ECS_APP_PORT", "5000")
                        dep = deployer.deploy(app_port, subdir=pub.get("subdir"))
                        fields["deploy"] = dep
                        if dep.get("deployed"):
                            print(f"[loop] 🚀 [{task.id}] 已部署 ECS → {dep.get('url')}")
                        else:
                            print(f"[loop] ⚠ [{task.id}] 部署未完成：{dep.get('reason')}")
                elif pub.get("committed"):
                    print(f"[loop] ⇪ [{task.id}] 已本地提交 {pub.get('commit')}；{pub.get('reason')}")
                else:
                    print(f"[loop] ⚠ [{task.id}] 发布未完成：{pub.get('reason')}")
            adapter.report(task.id, "done", finished_at=fin, **fields)
            return True
        adapter.report(task.id, "failed", finished_at=fin,
                       output_dir=run.get("dir"), attempts=run.get("attempts"),
                       reason="引擎验收未通过,详见产物目录 _verify.log")
        print(f"[loop] ✗ [{task.id}] 引擎未通过(exit={code})")
        return False

    adapter.report(task.id, "failed", finished_at=now,
                    reason="既无 case 映射也无 Spec 正文,无法处理")
    print(f"[loop] ✗ [{task.id}] 无 case 也无 spec_text")
    return False


def _task_snapshot(task: Task) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "source": task.source,
        "case": task.case,
        "spec_text": task.spec_text or "",
        "priority": task.priority,
        "extra": task.extra,
    }


def run_profile(profile_id: str, only_task: str = "", max_tasks: int = 0) -> int:
    """兼容 facade：委托给 Phase 4 的事件化 ProfileRunExecutor。"""
    from engine.core.observability import EventError
    from engine.core.profiles import ProfileError
    from engine.core.run_executor import ProfileRunExecutor

    try:
        results = ProfileRunExecutor().execute(
            profile_id, task_id=only_task, max_tasks=max_tasks or 1,
        )
    except (ProfileError, EventError) as exc:
        print(f"[loop] Profile 无法启动: {exc}")
        return 2
    for result in results:
        marker = "✓" if result.status == "passed" else "✗"
        print(f"[loop] {marker} [{result.task_id}] run={result.run_id} status={result.status}")
    return 0 if all(result.status == "passed" for result in results) else 1


def legacy_main() -> int:
    """保留历史飞书/环境变量编排入口，供未迁移调用方继续使用。"""
    docs_file = os.path.join(ROOT, os.environ.get("HARNESS_FEISHU_DOCS", "data/backlog.json"))
    state_file = os.path.join(ROOT, os.environ.get("HARNESS_FEISHU_STATE", "data/state.json"))
    adapter = FeishuAdapter(docs_file, state_file)
    mode = os.environ.get("HARNESS_MODE", "real")
    max_tasks = int(os.environ.get("HARNESS_MAX_TASKS", "0") or 0)
    only_task = os.environ.get("HARNESS_ONLY_TASK", "").strip()

    pending = adapter.list_pending()
    if only_task:
        pending = [t for t in pending if t.id == only_task]
        if not pending:
            print(f"[loop] 指定任务 {only_task} 不在待处理列表(可能已完成/不存在),结束。")
            return 0
    if max_tasks > 0:
        pending = pending[:max_tasks]

    scope = f"单条={only_task}" if only_task else "整池"
    print(f"[loop] 来源=feishu 模式={mode} 范围={scope} 待办={len(pending)} 条")
    if not pending:
        print("[loop] 需求池无 pending 任务,结束。")
        return 0

    cost_cap = float(os.environ.get("HARNESS_COST_CAP", "100"))
    cases_str = ",".join(t.case or t.id for t in pending)
    tracer.batch_start(mode, cases_str, cost_cap)

    ok = fail = 0
    for task in pending:
        print(f"\n===== 处理 [{task.id}] {task.title} (case={task.case}, prio={task.priority}) =====")
        tracer.gen_start(task.case or task.id, 1)
        if process(task, adapter, mode):
            ok += 1
            tracer.case_done(task.case or task.id, "pass", 1, "skip", 0)
        else:
            fail += 1
            tracer.case_done(task.case or task.id, "fail", 1, "skip", 0)

    tracer.batch_end(ok, fail, 0)
    print(f"\n[loop] 批次结束:成功 {ok} / 失败 {fail}")
    return 0 if fail == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Loop Platform 编排器")
    parser.add_argument("--profile", help="按冻结 Run Plan 执行指定 Profile；省略则走 legacy 兼容入口")
    parser.add_argument("--only-task", default="", help="仅执行指定 task id")
    parser.add_argument("--max-tasks", type=int, default=0, help="最多执行的 pending task 数")
    args = parser.parse_args()
    if args.profile:
        return run_profile(args.profile, args.only_task, args.max_tasks)
    return legacy_main()


if __name__ == "__main__":
    sys.exit(main())
