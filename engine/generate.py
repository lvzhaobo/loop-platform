#!/usr/bin/env python3
"""Loop 生成闭环（多用例回归 + 失败反馈重试 + 确定性复跑校验 + 护栏）。

替代 generate.sh。支持 HARNESS_MODE=sample 离线模式。

用法:
  python engine/generate.py                           # 跑 run_cases
  HARNESS_CASES=education python engine/generate.py    # 跑指定用例
  HARNESS_MODE=sample python engine/generate.py        # 离线模式
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# F2: 使用 PlatformPaths 集中管理路径
from engine.core.paths import PlatformPaths, find_root

LOOP_DIR = PlatformPaths.ROOT
ROOT = PlatformPaths.ROOT
ENGINE_DIR = PlatformPaths.ENGINE_DIR

sys.path.insert(0, str(ENGINE_DIR))
sys.path.insert(0, str(ENGINE_DIR / "tools"))
import makers  # noqa: E402

# ── 配置 ──
def expand_env(value: str) -> str:
    """展开 ${VAR:-default} 语法。"""
    import re as _re
    def _replace(match):
        var = match.group(1)
        default = match.group(2)
        return os.environ.get(var, default)
    return _re.sub(r'\$\{(\w+):-([^}]*)\}', _replace, value)


def load_config():
    """加载 config.env 和 .env 中的环境变量。"""
    config_file = LOOP_DIR / "config.env"
    if config_file.exists():
        with open(config_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("export "):
                    line = line[7:]
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.partition("=")
                    v = v.strip().strip('"').strip("'")
                    k = k.strip()
                    if k not in os.environ:
                        os.environ[k] = expand_env(v)
    # .env 覆盖
    env_file = ROOT / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("export "):
                    line = line[7:]
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.partition("=")
                    os.environ[k.strip()] = expand_env(v.strip().strip('"').strip("'"))

load_config()

MODE = os.environ.get("HARNESS_MODE", "real")
MAX_RETRY = int(os.environ.get("HARNESS_MAX_RETRY", "5"))
DET_CHECK = os.environ.get("HARNESS_DET_CHECK", "1") == "1"
COST_CAP = float(os.environ.get("HARNESS_COST_CAP", "100"))
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
VERIFY_PORT = os.environ.get("HARNESS_VERIFY_PORT", "5060")

# 用例集
CASES_ENV = os.environ.get("HARNESS_CASES", "").strip()
if CASES_ENV:
    CASES = CASES_ENV.split()
else:
    # 从根目录 cases/ 自动发现所有可用用例（F1: 迁移后路径）
    _all = [p.name for p in Path("cases").iterdir() if p.is_dir() and (p / "spec" / "manifest.json").exists()]
    CASES = _all if _all else ["education"]


def hash_output(out_dir: Path) -> str:
    """产物文件 SHA256 指纹。"""
    hasher = hashlib.sha256()
    for f in sorted(out_dir.rglob("*")):
        if f.is_file() and ".git" not in f.parts and "__pycache__" not in f.parts:
            rel = f.relative_to(out_dir)
            if "reports" in rel.parts or f.name.startswith("_"):
                continue
            hasher.update(rel.as_posix().encode())
            hasher.update(f.read_bytes())
    return hasher.hexdigest()


def estimate_cost(prompt_chars: int, response_chars: int) -> float:
    """估算 DeepSeek 花费（元）。"""
    in_tok = prompt_chars / 4
    out_tok = response_chars / 4
    return round(in_tok / 1_000_000 * 1.0 + out_tok / 1_000_000 * 2.0, 6)


def generate_one(case: str, out_dir: Path, feedback: str | None = None):
    """生成一个用例。返回 (success, cost)。"""
    maker_name = os.environ.get("HARNESS_MAKER", "deepseek")
    maker = makers.load_maker(maker_name)

    if MODE == "sample":
        from sample_generator import generate as sample_gen
        constraints = {}
        manifest_path = LOOP_DIR / "cases" / case / "spec" / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            if manifest.get("archetype") == "spec":
                # spec 类型不走 sample_generator（它需要 field_rules/min_items 等旧版字段）
                print(f"  ⚠ [{case}] spec archetype, sample 模式不适用，跳过生成")
                return True, 0.0
            sample_gen(manifest, constraints, str(out_dir))
        elif (LOOP_DIR / "cases" / case / "case.json").exists():
            case_data = json.loads((LOOP_DIR / "cases" / case / "case.json").read_text())
            case_data["name"] = case
            sample_gen(case_data, constraints, str(out_dir))
        else:
            print(f"  ⚠ 跳过 {case}: 无 manifest.json 也无 case.json")
            return False, 0.0
        return True, 0.0

    # 真实模式
    from run_model import build_context, build_context_spec
    constraints = {}

    # 读 manifest 或 case.json
    manifest_path = LOOP_DIR / "cases" / case / "spec" / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        prompt = build_context_spec(manifest, str(LOOP_DIR / "cases" / case), constraints)
    elif (LOOP_DIR / "cases" / case / "case.json").exists():
        case_data = json.loads((LOOP_DIR / "cases" / case / "case.json").read_text())
        case_data["name"] = case
        prompt = build_context(case_data, constraints)
    else:
        print(f"  ⚠ 跳过 {case}: 无 manifest.json 也无 case.json")
        return False, 0.0

    out_dir.mkdir(parents=True, exist_ok=True)
    result = maker.generate(str(out_dir), prompt, feedback)
    if not result.success:
        print(f"  ❌ 生成失败: {result.error}")
        return False, result.cost_estimate_yuan

    # 验证
    verify_script = ENGINE_DIR / "tools" / "verify_ac.py"
    if not verify_script.exists():
        verify_script = ENGINE_DIR / "tools" / "verify.py"
    proc = subprocess.run(
        [sys.executable, str(verify_script), case, str(out_dir)],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    verify_log = proc.stdout + proc.stderr
    (out_dir / "_verify.log").write_text(verify_log)

    if proc.returncode == 0:
        return True, result.cost_estimate_yuan
    return False, result.cost_estimate_yuan


def detect_stall(verify_log_path: Path) -> bool:
    """卡死检测：连续 3 次相同失败 → 判定卡死。"""
    history_file = verify_log_path.parent / "_stall_hashes.txt"
    current_hash = hashlib.sha256(verify_log_path.read_bytes()).hexdigest()
    hashes = []
    if history_file.exists():
        hashes = [l.strip() for l in history_file.read_text().strip().splitlines() if l.strip()]
    hashes.append(current_hash)
    history_file.write_text("\n".join(hashes[-10:]) + "\n")
    return len(hashes) >= 3 and len(set(hashes[-3:])) == 1


def main():
    ts = time.strftime("%Y%m%d-%H%M%S")
    print(f"本次批次:{ts}  模式:{MODE}  回归用例:{' '.join(CASES)}")
    print(f"护栏:花费上限 ¥{COST_CAP}  卡死检测:连续3次相同失败终止")

    overall = 0
    batch_cost = 0.0

    for case in CASES:
        out_dir = ROOT / "output" / f"{ts}-{case}"
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n=== 用例 [{case}] → {out_dir} ===")

        result = "fail"
        attempts = 0
        feedback = None
        stall_file = out_dir / "_verify.log"

        for i in range(1, MAX_RETRY + 1):
            attempts = i
            print(f"--- [{case}] 第 {i} 次生成 ---")

            if batch_cost >= COST_CAP:
                print(f"⛔ 花费已达上限 ¥{COST_CAP}，终止本批")
                result = "fail_cost_cap"
                break

            ok, cost = generate_one(case, out_dir, feedback)
            batch_cost += cost
            print(f"  ↳ 本轮花费: ¥{cost:.4f}  累计: ¥{batch_cost:.4f}")

            if ok:
                print(f"✅ [{case}] 第 {i} 次通过")
                result = "pass"
                break

            print(f"❌ [{case}] 第 {i} 次未通过，带反馈重生成")
            # 卡死检测
            if stall_file.exists() and detect_stall(stall_file):
                print(f"⛔ 卡死检测触发，终止该用例")
                result = "fail_stalled"
                break

            # 快照失败产物
            snap = out_dir.parent / f"{out_dir.name}-attempt{i}-fail"
            if snap.exists():
                shutil.rmtree(snap)
            shutil.copytree(out_dir, snap)
            print(f"  ↳ 产物已留档: {snap}")
            feedback = str(stall_file) if stall_file.exists() else None

            if MODE == "sample":
                break

        # 确定性复跑
        det = "skip"
        if result == "pass" and DET_CHECK:
            rerun_dir = ROOT / "output" / f"{ts}-{case}-rerun"
            rerun_dir.mkdir(parents=True, exist_ok=True)
            print(f"--- [{case}] 确定性复跑 → {rerun_dir} ---")
            ok2, _ = generate_one(case, rerun_dir)
            if ok2:
                h1 = hash_output(out_dir)
                h2 = hash_output(rerun_dir)
                det = "identical" if h1 == h2 else "drift"
                print(f"{'✅' if det=='identical' else '⚠️'} [{case}] 确定性:{det}")
            else:
                det = "drift"

        # 写入运行记录
        runs_file = ROOT / "output" / "runs.jsonl"
        with open(runs_file, "a") as f:
            f.write(json.dumps({
                "ts": ts, "case": case, "dir": str(out_dir.relative_to(ROOT)),
                "mode": MODE, "attempts": attempts, "result": result,
                "determinism": det, "model": MODEL, "cost_yuan": round(batch_cost, 4),
            }, ensure_ascii=False) + "\n")

        if result != "pass":
            overall = 1

    print(f"\n💰 本批总花费: ¥{batch_cost:.4f} / 上限 ¥{COST_CAP}")
    if overall == 0:
        print("✅ 全部回归用例通过")
    else:
        print("❌ 有用例未通过 → 加强约束（改约束，不改产物）")
    sys.exit(overall)


if __name__ == "__main__":
    main()
