"""Loop 引擎 Python 编排层：Maker → Checker → Publish → Deploy。"""

import json, os, sys, time
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parent.parent
ENGINE_DIR = LOOP_DIR / "engine"
sys.path.insert(0, str(LOOP_DIR))
sys.path.insert(0, str(ENGINE_DIR))


def run(spec_text: str, maker_name: str = "deepseek") -> dict:
    """运行完整 Loop 编排。"""
    log = []
    output_dir = ""

    # 1. Maker 生成
    log.append("[Maker] 开始生成...")
    from makers import load_maker
    maker = load_maker(maker_name)
    ts = time.strftime("%Y%m%d-%H%M%S")
    output_dir = str(LOOP_DIR.parent / "output" / f"loop-{ts}")
    os.makedirs(output_dir, exist_ok=True)

    prompt = spec_text + "\n\n你是代码生成器。用 Python Flask 和原生 HTML/CSS/JS 实现以上需求。\n【重要】必须严格按照以下格式输出每个文件：\n<<<FILE: app.py>>>\n文件内容\n<<<ENDFILE>>>\n<<<FILE: requirements.txt>>>\n文件内容\n<<<ENDFILE>>>\n每个文件都这样包裹。"
    result = maker.generate(output_dir, prompt)
    if not result.success:
        return {"ok": False, "error": result.error, "log": log, "output_dir": output_dir}

    cost = result.cost_estimate_yuan
    files = list(result.files.keys())
    log.append(f"[Maker] ✅ 生成完成 ({len(files)} 文件, ¥{cost:.4f})")
    for f in files:
        log.append(f"[Maker]   📄 {f}")

    # 2. Checker 验证
    log.append("[Checker] 验证中...")
    from checkers.all_checker import AllChecker
    checker = AllChecker()
    ck_result = checker.check(output_dir)
    if ck_result.all_pass:
        log.append(f"[Checker] ✅ 全部通过 ({ck_result.pass_count}/{ck_result.total_count})")
    else:
        log.append(f"[Checker] ❌ 未通过 ({ck_result.pass_count}/{ck_result.total_count})")
        for ck in ck_result.checks:
            icon = "✅" if ck["pass"] else "❌"
            log.append(f"[Checker]   {icon} {ck['name']}: {ck.get('detail', '')}")

    return {
        "ok": ck_result.all_pass,
        "output_dir": output_dir,
        "files": files,
        "cost_yuan": cost,
        "checks": ck_result.checks,
        "check_pass": ck_result.pass_count,
        "check_total": ck_result.total_count,
        "log": log,
    }


if __name__ == "__main__":
    result = run("做一个番茄时钟：25分钟专注计时，5分钟休息，开始/暂停/重置按钮，深色主题")
    print(json.dumps(result, ensure_ascii=False, indent=2))
