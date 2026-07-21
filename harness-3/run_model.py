"""Harness-3 生成器(case 驱动):调用 DeepSeek,依据 rules + 指定用例的 spec + case.json 生成产物。

相对 harness-2 的升级:
- 多用例:接收 <case>,只加载该用例 cases/<case>/spec + case.json(唯一事实源)
- 需输出的文件清单、是否配图,均从事实源派生,不再硬编码
用法: python harness-3/run_model.py <case> <产物目录> [反馈日志]
依赖: 仅标准库;密钥从环境变量 DEEPSEEK_API_KEY 读取。
"""
import glob
import json
import os
import re
import struct
import sys
import time
import urllib.error
import urllib.request
import zlib

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))

API_KEY = os.environ.get("DEEPSEEK_API_KEY")
BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
TEMPERATURE = float(os.environ.get("HARNESS_TEMPERATURE", "0"))
SEED = int(os.environ.get("HARNESS_SEED", "42"))

FILE_RE = re.compile(r"<<<FILE:\s*(.+?)>>>\n(.*?)\n<<<ENDFILE>>>", re.S)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def harness_version():
    try:
        return read(os.path.join(HARNESS_DIR, "VERSION")).strip()
    except OSError:
        return "unknown"


def required_files(constraints, case):
    """产物必须包含的文件 = 全局基础骨架 + 该用例专属文件(如 data/<entity>.json)。"""
    return list(constraints["base_required_files"]) + list(case.get("extra_required_files", []))


def build_context(case, constraints):
    """把 prompt + 分层约束 + 该用例 spec + 事实源摘要 拼成系统上下文。"""
    case_dir = os.path.join(HARNESS_DIR, "cases", case["name"])
    parts = [read(os.path.join(HARNESS_DIR, "prompt.md"))]
    parts.append(f"\n\n===== 本次任务 =====\n{case['title']}")
    for label, sub in [("通用基座 rules/base", "rules/base"),
                       ("任务约束 rules/task", "rules/task")]:
        parts.append(f"\n\n===== {label} =====")
        for p in sorted(glob.glob(os.path.join(HARNESS_DIR, sub, "*.md"))):
            parts.append(f"\n### {os.path.basename(p)}\n{read(p)}")
    parts.append(f"\n\n===== 规格 cases/{case['name']}/spec =====")
    for p in sorted(glob.glob(os.path.join(case_dir, "spec", "*.md"))):
        parts.append(f"\n### {os.path.basename(p)}\n{read(p)}")
    parts.append(
        "\n\n===== 硬性事实(唯一事实源 case.json,不得违反) =====\n"
        + json.dumps(case, ensure_ascii=False, indent=2)
    )
    parts.append(
        "\n\n===== 输出格式(强制) =====\n"
        "只输出文件,不要任何解释、不要 markdown 代码围栏。每个文件用如下格式:\n"
        "<<<FILE: 相对路径>>>\n文件内容\n<<<ENDFILE>>>\n"
        "必须输出以下全部文件: " + ", ".join(required_files(constraints, case))
    )
    return "".join(parts)


def call_deepseek(system, user, retries=3):
    """调用 DeepSeek Chat,固定 temperature 与 seed 以保证确定性。
    瞬时网络错误(读超时/连接错误/5xx)按指数退避自动重试,
    避免一次网络抖动就拖垮整条生成流水线。"""
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
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                f"{BASE_URL}/chat/completions", data=body,
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read())["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            # 4xx(鉴权/参数)是确定性错误,重试无益 → 直接失败
            if e.code < 500:
                sys.exit(f"[run_model] DeepSeek 返回 {e.code},不可重试: {e.reason}")
            last_err = e
        except (TimeoutError, urllib.error.URLError, ConnectionError, OSError) as e:
            last_err = e
        if attempt < retries:
            wait = 2 ** attempt  # 2s, 4s, 8s...
            print(f"[run_model] 第 {attempt}/{retries} 次调用失败({last_err}),{wait}s 后重试...")
            time.sleep(wait)
    sys.exit(f"[run_model] DeepSeek 连续 {retries} 次调用失败,放弃: {last_err}")


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


def write_meta(out, case):
    """落地确定性日志:记录用例/模型/版本/seed/温度,回填到 _verify.log 头部。"""
    meta = {
        "harness_version": harness_version(),
        "case": case["name"],
        "model": MODEL,
        "temperature": TEMPERATURE,
        "seed": SEED,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(os.path.join(out, "_run_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    header = (f"# harness={meta['harness_version']} case={case['name']} model={MODEL} "
              f"temperature={TEMPERATURE} seed={SEED} at={meta['generated_at']}\n")
    with open(os.path.join(out, "_verify.log"), "w", encoding="utf-8") as f:
        f.write(header)
    print("[run_model] 已写确定性元数据 _run_meta.json / _verify.log 头部")


def ensure_images(out, case):
    if not case.get("needs_images"):
        return
    pj = os.path.join(out, case["data_file"])
    if not os.path.exists(pj):
        return
    colors = [(255, 80, 0), (41, 128, 185), (39, 174, 96), (142, 68, 173),
              (230, 126, 34), (52, 73, 94), (22, 160, 133), (192, 57, 43)]
    img_dir = os.path.join(out, "static", "img")
    os.makedirs(img_dir, exist_ok=True)
    for i, item in enumerate(load_json(pj)):
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
    if len(sys.argv) < 3:
        sys.exit("用法: python harness-3/run_model.py <case> <产物目录> [反馈日志]")
    case_name, out = sys.argv[1], sys.argv[2]
    constraints = load_json(os.path.join(HARNESS_DIR, "constraints.json"))
    case = load_json(os.path.join(HARNESS_DIR, "cases", case_name, "case.json"))

    user = "请依据以上约束与规格,生成全部文件。"
    if len(sys.argv) >= 4 and os.path.exists(sys.argv[3]):
        user += "\n\n上一轮验收失败,以下是失败日志,只需修复失败项并重新输出全部文件:\n" + read(sys.argv[3])
    print(f"[run_model] 用例={case_name} 调用 {MODEL} (temp={TEMPERATURE}, seed={SEED}) 生成到 {out} ...")
    text = call_deepseek(build_context(case, constraints), user)
    write_files(text, out)
    ensure_images(out, case)
    write_meta(out, case)
    print("[run_model] 生成完成")


if __name__ == "__main__":
    main()
