"""delivery-loop 主循环(编排层)。

职责:从需求池自主取任务 → 子进程调用 harness-4 引擎生成+验证 → 回写状态到来源。
harness-4 被当作黑盒引擎调用(bash harness-4/generate.sh),本层不 import 其内部代码,
也不改其任何产物。引擎结果通过退出码 + output/runs.jsonl 回读。

用法: python delivery-loop/orchestrator.py
环境: 见 delivery-loop/config.env(HARNESS_BACKLOG_SOURCE / HARNESS_MODE / ...)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from adapters import Task, load_adapter  # noqa: E402
import publisher  # noqa: E402
import deployer  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 仓库根
HARNESS = "harness-4"
RUNS_JSONL = os.path.join(ROOT, "output", "runs.jsonl")
SPEC_DIR = os.path.join(ROOT, "delivery-loop", "specs")
VALID_CASES = ("ecommerce", "blog", "education")


def run_engine(case: str, mode: str) -> int:
    """子进程调用 harness-4:仅跑指定单个用例。返回引擎退出码(0=全部通过)。"""
    env = os.environ.copy()
    env["HARNESS_CASES"] = case   # generate.sh 优先读此变量,只跑这一个用例
    env["HARNESS_MODE"] = mode
    print(f"[delivery-loop] → 调用 harness-4 引擎:case={case} mode={mode}")
    proc = subprocess.run(["bash", f"{HARNESS}/generate.sh"], cwd=ROOT, env=env)
    return proc.returncode


def latest_run(case: str) -> dict:
    """从 output/runs.jsonl 回读该用例最近一次运行记录(产物目录/重试次数/结果)。"""
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
    """把来源(如飞书文档)拉到的 Spec 落地为文件,便于查看与后续 spec 编译。"""
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
    """case 是否可跑:预置用例,或已编译出契约——
    catalog 形态看 cases/<case>/case.json;Spec 形态(单页交互工具)看 cases/<case>/spec/manifest.json。

    generate.sh 以 HARNESS_CASES 直跑指定用例,不受 constraints.json["cases"] 限制,
    故只要契约在,引擎即可生成+验证——这也从根上打破了写死的 case 边界。
    """
    if case in VALID_CASES:
        return True
    cdir = os.path.join(ROOT, HARNESS, "cases", case)
    return (os.path.exists(os.path.join(cdir, "case.json"))
            or os.path.exists(os.path.join(cdir, "spec", "manifest.json")))


def compile_from_spec(task: Task) -> tuple[str | None, str, str | None]:
    """把自由文本 Spec 交给 harness-4 的 spec 编译层(子进程,黑盒调用,不 import 引擎内部)。

    成功:返回 (case_name, spec_path, None);失败:返回 (None, spec_path, 原因)。
    编译层内部已跑 compile_spec --check 与合规契约门禁,任一不过即非零退出。
    注:编译需 LLM(DEEPSEEK_API_KEY);离线无 key 时会非零退出 → 上层降级为 fetched。
    """
    spec_path = save_spec(task)  # 先持久化原始 Spec(无论编译成败都留档)
    name = slugify_case(task.id)
    cmd = [sys.executable, f"{HARNESS}/tools/spec_compiler.py",
           "--name", name, "--input", os.path.join(ROOT, spec_path)]
    # 形态:任务可显式声明 archetype=spec(单页交互工具,如计时器),编译走 Spec 路径产出
    # spec.md+manifest.json+acceptance.json;缺省 catalog(列表/详情站,原行为不变)。
    archetype = str(task.extra.get("archetype", "catalog")).strip().lower()
    if archetype == "spec":
        cmd += ["--archetype", "spec"]
    print(f"[delivery-loop] ⚙ [{task.id}] 调用 spec 编译层:{name} ← {spec_path} (archetype={archetype})")
    proc = subprocess.run(cmd, cwd=ROOT)
    if proc.returncode == 0 and case_available(name):
        return name, spec_path, None
    return None, spec_path, "spec 编译或契约门禁未通过(详见上方输出)"


def process(task: Task, adapter, mode: str) -> bool:
    now = time.strftime("%Y-%m-%d %H:%M:%S")

    # 拉取失败(如飞书文档无权限/网络错误):适配器已把原因塞进 extra.fetch_error
    if task.extra.get("fetch_error"):
        adapter.report(task.id, "failed", finished_at=now,
                        reason=f"来源拉取失败:{task.extra['fetch_error']}")
        print(f"[delivery-loop] ✗ [{task.id}] 来源拉取失败")
        return False

    # 无 case 但有 Spec 正文:先用 spec 编译层把自由文本编译成合规 case(Phase 2)。
    # 编译+门禁通过 → 赋予 task.case,落入下方引擎链路;失败 → 落地 Spec 标 fetched,不硬闯。
    if not task.case and task.spec_text:
        name, spec_path, err = compile_from_spec(task)
        if name:
            task.case = name
            print(f"[delivery-loop] ⚙ [{task.id}] Spec 已编译为合规 case={name},进入生成链路")
        else:
            adapter.report(task.id, "fetched", finished_at=now, spec_path=spec_path,
                           note=f"Spec 已落地;spec 编译未通过门禁,暂不生成:{err}")
            print(f"[delivery-loop] ● [{task.id}] Spec 编译未通过,标 fetched → {spec_path}")
            return True

    # 已映射(或已由 spec 编译得到)harness-4 用例 → 走引擎真实生成+验证
    if task.case:
        if not case_available(task.case):
            adapter.report(task.id, "failed", finished_at=now,
                            reason=f"未知 case '{task.case}'(cases/ 下无 case.json)")
            print(f"[delivery-loop] ✗ [{task.id}] 未知 case={task.case}")
            return False
        adapter.report(task.id, "running", started_at=now)
        code = run_engine(task.case, mode)
        run = latest_run(task.case)
        fin = time.strftime("%Y-%m-%d %H:%M:%S")
        if code == 0:
            fields = dict(output_dir=run.get("dir"), attempts=run.get("attempts"),
                          determinism=run.get("determinism"))
            print(f"[delivery-loop] ✓ [{task.id}] 完成 → {run.get('dir')}")
            # L1 发布到 GitHub(HARNESS_AUTOCOMMIT=1 时):产物目录 git 提交 → 推送
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
                    print(f"[delivery-loop] ⇪ [{task.id}] 已推送 {pub['remote']} → {where} ({pub.get('commit')})")
                    # L4 拉取式部署到 ECS(ECS_DEPLOY=1 且已推送成功时)
                    if os.environ.get("ECS_DEPLOY") == "1":
                        # 端口与子目录优先用 publisher 算出的(B 方案 sampleN → 端口),否则回退环境变量
                        app_port = pub.get("port") or os.environ.get("ECS_APP_PORT", "5000")
                        dep = deployer.deploy(app_port, subdir=pub.get("subdir"))
                        fields["deploy"] = dep
                        if dep.get("deployed"):
                            print(f"[delivery-loop] 🚀 [{task.id}] 已部署 ECS → {dep.get('url')}")
                        else:
                            print(f"[delivery-loop] ⚠ [{task.id}] 部署未完成：{dep.get('reason')}")
                elif pub.get("committed"):
                    print(f"[delivery-loop] ⇪ [{task.id}] 已本地提交 {pub.get('commit')}；{pub.get('reason')}")
                else:
                    print(f"[delivery-loop] ⚠ [{task.id}] 发布未完成：{pub.get('reason')}")
            adapter.report(task.id, "done", finished_at=fin, **fields)
            return True
        adapter.report(task.id, "failed", finished_at=fin,
                       output_dir=run.get("dir"), attempts=run.get("attempts"),
                       reason="引擎验收未通过,详见产物目录 _verify.log")
        print(f"[delivery-loop] ✗ [{task.id}] 引擎未通过(exit={code})")
        return False

    adapter.report(task.id, "failed", finished_at=now,
                    reason="既无 case 映射也无 Spec 正文,无法处理")
    print(f"[delivery-loop] ✗ [{task.id}] 无 case 也无 spec_text")
    return False


def main() -> int:
    source = os.environ.get("HARNESS_BACKLOG_SOURCE", "local")
    backlog_file = os.environ.get("HARNESS_BACKLOG_FILE", "delivery-loop/backlog/backlog.jsonl")
    mode = os.environ.get("HARNESS_MODE", "sample")
    max_tasks = int(os.environ.get("HARNESS_MAX_TASKS", "0") or 0)
    only_task = os.environ.get("HARNESS_ONLY_TASK", "").strip()  # 非空=只交付该任务 id,空=整池

    adapter = load_adapter(source, backlog_file=os.path.join(ROOT, backlog_file))
    pending = adapter.list_pending()
    if only_task:
        pending = [t for t in pending if t.id == only_task]
        if not pending:
            print(f"[delivery-loop] 指定任务 {only_task} 不在待处理列表(可能已完成/不存在),结束。")
            return 0
    if max_tasks > 0:
        pending = pending[:max_tasks]

    scope = f"单条={only_task}" if only_task else "整池"
    print(f"[delivery-loop] 来源={source} 模式={mode} 范围={scope} 待办={len(pending)} 条")
    if not pending:
        print("[delivery-loop] 需求池无 pending 任务,结束。")
        return 0

    ok = fail = 0
    for task in pending:
        print(f"\n===== 处理 [{task.id}] {task.title} (case={task.case}, prio={task.priority}) =====")
        if process(task, adapter, mode):
            ok += 1
        else:
            fail += 1

    print(f"\n[delivery-loop] 批次结束:成功 {ok} / 失败 {fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
