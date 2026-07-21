"""Harness-2 生成器:调用 DeepSeek,依据 rules/base + rules/task + spec + prompt 生成产物。

补全点(相对 harness/):
- 读取分层约束(base 通用基座 + task 任务专属)
- 落地确定性:temperature/seed 来自 config.env,写 _run_meta.json 并回填 _verify.log 头部
用法: python harness-2/run_model.py <产物目录> [反馈日志]
依赖: 仅标准库;密钥从环境变量 DEEPSEEK_API_KEY 读取。
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

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))

API_KEY = os.environ.get("DEEPSEEK_API_KEY")
BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
TEMPERATURE = float(os.environ.get("HARNESS_TEMPERATURE", "0"))
SEED = int(os.environ.get("HARNESS_SEED", "42"))

FILE_RE = re.compile(r"<<<FILE:\s*(.+?)>>>\n(.*?)\n<<<ENDFILE>>>", re.S)

REQUIRED = [
    "app.py", "requirements.txt", "README.md", "data/products.json",
    "templates/base.html", "templates/list.html", "templates/detail.html",
    "static/css/style.css", "static/js/main.js", "tests/test_app.py",
]


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def harness_version():
    try:
        return read(os.path.join(HARNESS_DIR, "VERSION")).strip()
    except OSError:
        return "unknown"


def build_context():
    """把 prompt + 分层约束 + 规格拼成系统上下文。"""
    parts = [read(os.path.join(HARNESS_DIR, "prompt.md"))]
    for label, sub in [("通用基座 rules/base", "rules/base"),
                       ("任务约束 rules/task", "rules/task"),
                       ("规格 spec", "spec")]:
        parts.append(f"\n\n===== {label} =====")
        for p in sorted(glob.glob(os.path.join(HARNESS_DIR, sub, "*.md"))):
            parts.append(f"\n### {os.path.basename(p)}\n{read(p)}")
    parts.append(
        "\n\n===== 输出格式(强制) =====\n"
        "只输出文件,不要任何解释、不要 markdown 代码围栏。每个文件用如下格式:\n"
        "<<<FILE: 相对路径>>>\n文件内容\n<<<ENDFILE>>>\n"
        "必须输出以下全部文件: " + ", ".join(REQUIRED)
    )
    return "".join(parts)


def call_deepseek(system, user):
    """调用 DeepSeek Chat,固定 temperature 与 seed 以保证确定性。"""
    if not API_KEY:
        sys.exit("[run_model] 缺少 DEEPSEEK_API_KEY(请先 source .env)")
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


def write_meta(out):
    """落地确定性日志:记录模型/版本/seed/温度,回填到 _verify.log 头部。"""
    meta = {
        "harness_version": harness_version(),
        "model": MODEL,
        "temperature": TEMPERATURE,
        "seed": SEED,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(os.path.join(out, "_run_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    header = (f"# harness={meta['harness_version']} model={MODEL} "
              f"temperature={TEMPERATURE} seed={SEED} at={meta['generated_at']}\n")
    with open(os.path.join(out, "_verify.log"), "w", encoding="utf-8") as f:
        f.write(header)
    print("[run_model] 已写确定性元数据 _run_meta.json / _verify.log 头部")


def ensure_images(out):
    pj = os.path.join(out, "data", "products.json")
    if not os.path.exists(pj):
        return
    colors = [(255, 80, 0), (41, 128, 185), (39, 174, 96), (142, 68, 173),
              (230, 126, 34), (52, 73, 94), (22, 160, 133), (192, 57, 43)]
    img_dir = os.path.join(out, "static", "img")
    os.makedirs(img_dir, exist_ok=True)
    for i, item in enumerate(json.load(open(pj, encoding="utf-8"))):
        _png(os.path.join(img_dir, f"{item.get('id', i + 1)}.png"), colors[i % len(colors)])
    print("[run_model] 已补齐占位图片")


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
    if len(sys.argv) < 2:
        sys.exit("用法: python harness-2/run_model.py <产物目录> [反馈日志]")
    out = sys.argv[1]
    user = "请依据以上约束与规格,生成全部文件。"
    if len(sys.argv) >= 3 and os.path.exists(sys.argv[2]):
        user += "\n\n上一轮验收失败,以下是失败日志,只需修复失败项并重新输出全部文件:\n" + read(sys.argv[2])
    print(f"[run_model] 调用 {MODEL} (temp={TEMPERATURE}, seed={SEED}) 生成到 {out} ...")
    text = call_deepseek(build_context(), user)
    write_files(text, out)
    ensure_images(out)
    write_meta(out)
    print("[run_model] 生成完成")


if __name__ == "__main__":
    main()
