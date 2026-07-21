"""Harness 真实生成器:调用 DeepSeek,依据 rules/ + spec/ + prompt.md 生成产物。

用法: python harness/run_model.py <产物目录> [反馈日志路径]
依赖: 仅 Python 标准库(urllib);密钥从环境变量 DEEPSEEK_API_KEY 读取。
生成确定性: temperature=0(见 3.md 3.3)。
"""
import glob
import json
import os
import re
import struct
import sys
import urllib.request
import zlib

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))

API_KEY = os.environ.get("DEEPSEEK_API_KEY")
BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

# 输出格式约定:模型只能用这个格式吐文件,便于确定性解析
FILE_RE = re.compile(r"<<<FILE:\s*(.+?)>>>\n(.*?)\n<<<ENDFILE>>>", re.S)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def build_context():
    """把约束层 + 规格层 + 入口提示词拼成系统上下文。"""
    parts = [read(os.path.join(HARNESS_DIR, "prompt.md")), "\n\n===== 约束(rules) ====="]
    for p in sorted(glob.glob(os.path.join(HARNESS_DIR, "rules", "*.md"))):
        parts.append(f"\n### {os.path.basename(p)}\n{read(p)}")
    parts.append("\n\n===== 规格(spec) =====")
    for p in sorted(glob.glob(os.path.join(HARNESS_DIR, "spec", "*.md"))):
        parts.append(f"\n### {os.path.basename(p)}\n{read(p)}")
    parts.append(
        "\n\n===== 输出格式(强制) =====\n"
        "只输出文件,不要任何解释、不要 markdown 代码围栏。每个文件用如下格式:\n"
        "<<<FILE: 相对路径>>>\n文件内容\n<<<ENDFILE>>>\n"
        "必须输出: app.py, requirements.txt, data/products.json, "
        "templates/base.html, templates/list.html, templates/detail.html, "
        "static/css/style.css, static/js/main.js"
    )
    return "".join(parts)


def call_deepseek(system, user):
    """调用 DeepSeek Chat 接口,temperature=0 保证确定性。"""
    if not API_KEY:
        sys.exit("[run_model] 缺少环境变量 DEEPSEEK_API_KEY(请先 source .env)")
    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0,
        "max_tokens": 8192,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions", data=body,
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]["content"]


def write_files(text, out):
    """按约定格式解析模型输出并落盘。"""
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
    return [b[0].strip() for b in blocks]


def ensure_images(out):
    """模型无法产出二进制图片,这里按 products.json 补占位 PNG。"""
    pj = os.path.join(out, "data", "products.json")
    if not os.path.exists(pj):
        return
    colors = [(255, 80, 0), (41, 128, 185), (39, 174, 96), (142, 68, 173),
              (230, 126, 34), (52, 73, 94), (22, 160, 133), (192, 57, 43)]
    img_dir = os.path.join(out, "static", "img")
    os.makedirs(img_dir, exist_ok=True)
    for i, item in enumerate(json.load(open(pj, encoding="utf-8"))):
        pid = item.get("id", i + 1)
        _png(os.path.join(img_dir, f"{pid}.png"), colors[i % len(colors)])
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
        sys.exit("用法: python harness/run_model.py <产物目录> [反馈日志]")
    out = sys.argv[1]
    system = build_context()
    user = "请依据以上约束与规格,生成全部文件。"
    if len(sys.argv) >= 3 and os.path.exists(sys.argv[2]):
        user += ("\n\n上一轮验收失败,以下是失败日志,只需修复失败项并重新输出全部文件:\n"
                 + read(sys.argv[2]))
    print(f"[run_model] 调用 {MODEL} 生成到 {out} ...")
    text = call_deepseek(system, user)
    write_files(text, out)
    ensure_images(out)
    print("[run_model] 生成完成")


if __name__ == "__main__":
    main()
