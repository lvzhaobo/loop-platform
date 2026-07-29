"""Harness-4 生成器(case 驱动,场景中立)。

模式:
  - real  :调用 DeepSeek,依据 prompt + rules + 该用例 spec + case.json(唯一事实源)生成;
  - sample:离线参考生成器(不烧额度,产物确定性、必过 verify),用于冒烟/CI/确定性基线。

用法: python harness-4/tools/run_model.py <case> <产物目录> [反馈日志]
环境: HARNESS_MODE=real|sample;密钥从环境变量 DEEPSEEK_API_KEY 读取。
"""
import glob
import json
import os
import re
import struct
import sys
import time
import urllib.request
import zlib

# 本脚本以命令行方式运行,确保能从自身目录导入同级 sample_generator
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sample_generator  # noqa: E402

ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # loop/engine/
LOOP_DIR = os.path.dirname(ENGINE_DIR)  # loop/

API_KEY = os.environ.get("DEEPSEEK_API_KEY")
BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
TEMPERATURE = float(os.environ.get("HARNESS_TEMPERATURE", "0"))
SEED = int(os.environ.get("HARNESS_SEED", "42"))
MODE = os.environ.get("HARNESS_MODE", "real")

FILE_RE = re.compile(r"<<<FILE:\s*(.+?)>>>\n(.*?)\n<<<ENDFILE>>>", re.S)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def harness_version():
    try:
        return read(os.path.join(ENGINE_DIR, "VERSION")).strip()
    except OSError:
        return "unknown"


def required_files(constraints, case):
    """产物必须包含的文件 = 全局基础骨架 + 该用例专属文件(如 data/<entity>.json)。"""
    return list(constraints["base_required_files"]) + list(case.get("extra_required_files", []))


def _load_conditional_rules(manifest: dict) -> list[str]:
    """按 manifest.tech 条件加载语言和前端规则。返回规则文本列表。"""
    parts = []
    lang = (manifest.get("tech", {}) or {}).get("language", "python")
    framework = (manifest.get("tech", {}) or {}).get("framework", "")

    # 语言规则
    lang_dir = os.path.join(ENGINE_DIR, "rules", "lang")
    lang_file = os.path.join(lang_dir, f"{lang}.md")
    if os.path.exists(lang_file):
        parts.append(f"\n\n===== 语言规范 rules/lang/{lang}.md [生效: language={lang}] =====")
        parts.append(read(lang_file))
    else:
        # 尝试通用规则
        for p in sorted(glob.glob(os.path.join(lang_dir, "*.md"))):
            parts.append(f"\n### {os.path.basename(p)}\n{read(p)}")

    # 前端规则（只要产物包含 HTML/CSS 文件就生效）
    frontend_dir = os.path.join(ENGINE_DIR, "rules", "frontend")
    req_files = manifest.get("required_files", [])
    has_html = any(f.endswith(".html") for f in req_files)
    has_css = any(f.endswith(".css") for f in req_files)
    if has_html or has_css:
        for p in sorted(glob.glob(os.path.join(frontend_dir, "*.md"))):
            parts.append(f"\n\n===== 前端规范 rules/frontend/{os.path.basename(p)} [生效: 含HTML/CSS] =====")
            parts.append(read(p))

    return parts


def build_context(case, constraints):
    """把 AGENTS + prompt + 分层约束 + 条件规则 + spec + 事实源 拼成系统上下文。"""
    case_dir = os.path.join(LOOP_DIR, "cases", case["name"])
    parts = []

    # AGENTS.md 最高优先级
    agents_path = os.path.join(ENGINE_DIR, "AGENTS.md")
    if os.path.exists(agents_path):
        parts.append("===== AGENTS.md (项目级 Agent 指令, 最高优先级) =====\n")
        parts.append(read(agents_path))

    parts.append("\n\n===== 系统提示 prompt.md =====")
    parts.append(read(os.path.join(ENGINE_DIR, "prompt.md")))
    parts.append(f"\n\n===== 本次任务 =====\n{case['title']}")

    for label, sub in [("通用基座 rules/base", "rules/base"),
                       ("任务约束 rules/task", "rules/task")]:
        parts.append(f"\n\n===== {label} =====")
        for p in sorted(glob.glob(os.path.join(ENGINE_DIR, sub, "*.md"))):
            parts.append(f"\n### {os.path.basename(p)}\n{read(p)}")

    # 条件规则（语言 + 前端）
    manifest = {"tech": {"language": "python", "framework": "flask"},
                "required_files": case.get("extra_required_files", [])}
    # 尝试从 manifest.json 读取更准确的信息
    manifest_path = os.path.join(case_dir, "spec", "manifest.json")
    if os.path.exists(manifest_path):
        try:
            manifest = json.loads(open(manifest_path).read())
        except Exception:
            pass
    parts.extend(_load_conditional_rules(manifest))

    parts.append(f"\n\n===== 规格 cases/{case['name']}/spec =====")
    for p in sorted(glob.glob(os.path.join(case_dir, "spec", "*.md"))):
        parts.append(f"\n### {os.path.basename(p)}\n{read(p)}")
    parts.append(
        "\n\n===== 硬性事实(唯一事实源 case.json,不得违反) =====\n"
        + json.dumps(case, ensure_ascii=False, indent=2)
    )
    must = case.get("must_contain_text") or []
    if must:
        parts.append(
            "\n\n===== 必须出现的字面文案(逐字,不得改写/翻译/省略) =====\n"
            + "\n".join("- " + s for s in must)
            + "\n以上每条文案必须原样出现在渲染后的页面 HTML 中;"
            "建议写入所有页面共用的 base 模板(如页头/页脚),确保列表页与详情页都能看到。"
        )
    parts.append(
        "\n\n===== 输出格式(强制) =====\n"
        "只输出文件,不要任何解释、不要 markdown 代码围栏。每个文件用如下格式:\n"
        "<<<FILE: 相对路径>>>\n文件内容\n<<<ENDFILE>>>\n"
        "必须输出以下全部文件: " + ", ".join(required_files(constraints, case))
    )
    return "".join(parts)


def build_context_spec(manifest, cdir, constraints):
    """Spec 形态：AGENTS.md + prompt.spec.md + 条件规则 + 验收标准。"""
    parts = []

    agents_path = os.path.join(ENGINE_DIR, "AGENTS.md")
    if os.path.exists(agents_path):
        parts.append("===== AGENTS.md (项目级 Agent 指令, 最高优先级) =====\n")
        parts.append(read(agents_path))

    parts.append("\n\n===== 系统提示 prompt.spec.md =====")
    parts.append(read(os.path.join(ENGINE_DIR, "prompt.spec.md")))
    parts.append(f"\n\n===== 本次任务 =====\n{manifest.get('title', manifest['name'])}")

    parts.append("\n\n===== 通用基座 rules/base =====")
    for p in sorted(glob.glob(os.path.join(ENGINE_DIR, "rules/base", "*.md"))):
        parts.append(f"\n### {os.path.basename(p)}\n{read(p)}")
    spec_md = os.path.join(cdir, "spec", "spec.md")
    if os.path.exists(spec_md):
        parts.append("\n\n===== 需求规格 spec/spec.md =====\n" + read(spec_md))
    ac_path = os.path.join(cdir, "spec", "acceptance.json")
    if os.path.exists(ac_path):
        ac = load_json(ac_path)
        parts.append("\n\n===== 验收标准 TC/AC(你的产物将被逐条自动检查,务必全部满足) =====\n"
                     + json.dumps(ac.get("acceptance", []), ensure_ascii=False, indent=2)
                     + "\n说明:http_* 会真起服务访问该路由;file_exists/text_* 检查文件内容;"
                       "unit_test 会跑对应测试文件(需真实可跑通);manual 项你无需处理。")
    req = manifest.get("required_files", [])
    parts.append(
        "\n\n===== 输出格式(强制) =====\n"
        "只输出文件,不要任何解释、不要 markdown 代码围栏。每个文件用如下格式:\n"
        "<<<FILE: 相对路径>>>\n文件内容\n<<<ENDFILE>>>\n"
        "必须输出以下全部文件: " + ", ".join(req)
    )
    return "".join(parts)


def call_deepseek(system, user):
    """调用 DeepSeek Chat,固定 temperature 与 seed 以尽量保证确定性。"""
    if not API_KEY:
        sys.exit("[run_model] 缺少 DEEPSEEK_API_KEY(请先 source .env,或用 HARNESS_MODE=sample 离线模式)")
    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": TEMPERATURE,
        "seed": SEED,
        "max_tokens": 8192,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions", data=body,
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def write_files(text, out):
    blocks = FILE_RE.findall(text)
    if not blocks:
        sys.exit("[run_model] 未解析到任何文件,模型输出不符合格式")
    for rel, content in blocks:
        rel = rel.strip()
        dst = os.path.join(out, rel)
        os.makedirs(os.path.dirname(dst) or out, exist_ok=True)
        with open(dst, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[run_model] 写入 {rel}")


def write_meta(out, name, mode):
    """落地确定性日志:记录用例/模型/版本/seed/温度/模式,回填到 _verify.log 头部。"""
    meta = {
        "harness_version": harness_version(),
        "case": name,
        "mode": mode,
        "model": MODEL if mode == "real" else "sample-generator",
        "temperature": TEMPERATURE,
        "seed": SEED,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(os.path.join(out, "_run_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    header = (f"# harness={meta['harness_version']} case={name} mode={mode} "
              f"model={meta['model']} temperature={TEMPERATURE} seed={SEED} at={meta['generated_at']}\n")
    with open(os.path.join(out, "_verify.log"), "w", encoding="utf-8") as f:
        f.write(header)
    print("[run_model] 已写确定性元数据 _run_meta.json / _verify.log 头部")


def ensure_images(out, case):
    """真实模式下模型常只写图片路径不产图片,这里**按数据里 image_field 的实际取值**补齐彩色
    占位图:兼容前导 '/' 的绝对式写法与任意文件名,确保「数据引用到的每张图都真实落地」。"""
    if not case.get("needs_images"):
        return
    pj = os.path.join(out, case["data_file"])
    if not os.path.exists(pj):
        return
    field = case.get("image_field")
    colors = [(255, 80, 0), (41, 128, 185), (39, 174, 96), (142, 68, 173),
              (230, 126, 34), (52, 73, 94), (22, 160, 133), (192, 57, 43)]
    made = 0
    for i, item in enumerate(load_json(pj)):
        rel = item.get(field) if field else None
        rel = str(rel).lstrip("/") if rel else f"static/img/{item.get('id', i + 1)}.png"
        dst = os.path.join(out, rel)
        os.makedirs(os.path.dirname(dst) or out, exist_ok=True)
        if not os.path.exists(dst):
            _png(dst, colors[i % len(colors)])
            made += 1
    print(f"[run_model] 已补齐占位图片(按数据引用路径,新增 {made} 张)")


def _png(path, rgb, size=400):
    if os.path.exists(path):
        return
    r, g, b = rgb
    raw = bytearray()
    for _ in range(size):
        raw.append(0)
        raw += bytes((r, g, b)) * size

    def chunk(typ, data):
        c = typ + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n"
                + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
                + chunk(b"IEND", b""))


def main():
    if len(sys.argv) < 3:
        sys.exit("用法: python harness-4/tools/run_model.py <case> <产物目录> [反馈日志]")
    case_name, out = sys.argv[1], sys.argv[2]
    # 无外部约束文件，Spec 是唯一事实源
    constraints = {}
    cdir = os.path.join(LOOP_DIR, "cases", case_name)
    case_path = os.path.join(cdir, "case.json")
    manifest_path = os.path.join(cdir, "spec", "manifest.json")
    feedback = sys.argv[3] if len(sys.argv) >= 4 and os.path.exists(sys.argv[3]) else None

    # 形态判定:有 case.json 走 catalog(原路径,行为不变);否则有 spec/manifest.json 走 Spec 形态。
    if os.path.exists(case_path):
        case = load_json(case_path)
        if MODE == "sample":
            print(f"[run_model] 用例={case_name} 离线参考生成器 -> {out}")
            sample_generator.generate(case, constraints, out)
            write_meta(out, case_name, "sample")
            print("[run_model] 生成完成(sample)")
            return
        user = "请依据以上约束与规格,生成全部文件。"
        if feedback:
            user += "\n\n上一轮验收失败,以下是失败日志,只需修复失败项并重新输出全部文件:\n" + read(feedback)
        print(f"[run_model] 用例={case_name} 调用 {MODEL} (temp={TEMPERATURE}, seed={SEED}) 生成到 {out} ...")
        text = call_deepseek(build_context(case, constraints), user)
        write_files(text, out)
        ensure_images(out, case)
        write_meta(out, case_name, "real")
        print("[run_model] 生成完成(real)")
        return

    if os.path.exists(manifest_path):
        manifest = load_json(manifest_path)
        if MODE == "sample":
            sys.exit("[run_model] Spec 形态暂不支持 sample 离线模式(交互产物无法模板化确定性生成),请用 HARNESS_MODE=real")
        user = "请依据以上规格与验收标准,生成全部文件。"
        if feedback:
            user += "\n\n上一轮验收失败,以下是失败日志,只需修复失败项并重新输出全部文件:\n" + read(feedback)
        print(f"[run_model] 用例={case_name}(Spec 形态)调用 {MODEL} (temp={TEMPERATURE}, seed={SEED}) 生成到 {out} ...")
        text = call_deepseek(build_context_spec(manifest, cdir, constraints), user)
        write_files(text, out)
        write_meta(out, case_name, "real")
        print("[run_model] 生成完成(real, spec)")
        return

    sys.exit(f"[run_model] 用例 {case_name} 既无 case.json 也无 spec/manifest.json,无法生成")


if __name__ == "__main__":
    main()
