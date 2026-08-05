"""离线参考生成器:仅凭 case.json 确定性地产出一个可通过 verify.py 的 Flask 产物。

用途:
  - 冒烟/CI:无需 DEEPSEEK_API_KEY 即可验证整条 Harness 流水线是否自洽;
  - 确定性基线:作为"黄金参考实现",复跑必然字节一致;
  - 教学:展示满足全部契约的最小骨架。

注意:这是"参考实现",不是业务实现;数据为占位内容,但严格满足 case.json 的
     required_fields / field_rules / min_items,以及 UI/接口/结构约束。

实现约定:所有文件内容一律用「纯字符串拼接」构建,不使用 % 格式化 / f-string /
     str.format,以避免与 Jinja 模板中的 {{ }} / {% %} 记号冲突。
"""
import json
import os

# 1x1 透明 PNG(占位图,满足 needs_images 的用例)
_PNG_1x1 = bytes([
    0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00, 0x00, 0x0D,
    0x49, 0x48, 0x44, 0x52, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
    0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4, 0x89, 0x00, 0x00, 0x00,
    0x0D, 0x49, 0x44, 0x41, 0x54, 0x78, 0x9C, 0x62, 0x00, 0x01, 0x00, 0x00,
    0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00, 0x00, 0x00, 0x00, 0x49,
    0x45, 0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82,
])


def _make_string(field, i, rule):
    """按 field_rules 造一个满足长度约束的占位字符串。"""
    if field == "date":
        return "2026-07-" + ("%02d" % ((i % 28) + 1))
    min_len = rule.get("min_len")
    max_len = rule.get("max_len")
    s = field + "示例" + str(i)
    if min_len:
        filler = "这是用于满足最小长度约束的占位正文段落内容。"
        while len(s) < min_len:
            s += filler
    if max_len and len(s) > max_len:
        s = s[:max_len]
    return s


def _make_records(case):
    """按 required_fields + field_rules 造 min_items 条确定性数据。"""
    fields = case["required_fields"]
    rules = case.get("field_rules", {})
    numeric = case.get("numeric_fields", {})
    image_field = case.get("image_field")
    records = []
    for i in range(1, case["min_items"] + 1):
        rec = {}
        for f in fields:
            rule = rules.get(f, {})
            t = rule.get("type") or numeric.get(f)
            if f == "id":
                rec[f] = i
            elif case.get("needs_images") and f == image_field:
                rec[f] = "static/img/" + str(i) + ".png"
            elif t == "int":
                rec[f] = 100 + i
            elif t == "number":
                rec[f] = round(9.9 + i, 2)  # > 0
            else:
                rec[f] = _make_string(f, i, rule)
        records.append(rec)
    return records


def _derive_routes(case):
    """从 case.routes 推导 Flask 路由模式与链接前缀。"""
    r = case["routes"]

    def to_pattern(sample):
        head = sample.rsplit("/", 1)[0]
        return head + "/<int:id>", head

    detail_pattern, detail_prefix = to_pattern(r["detail_sample"])
    api_detail_pattern, _ = to_pattern(r["api_detail_missing"])
    return {
        "list": r["list"],
        "detail_pattern": detail_pattern,
        "detail_prefix": detail_prefix,
        "api_list": r["api_list"],
        "api_detail_pattern": api_detail_pattern,
    }


def _app_py(case, rt):
    """生成 app.py(唯一 loader、四路由、404 契约、端口从环境变量读取)。"""
    loader = case["loader_function"]
    fns = case["route_functions"]
    entity = case.get("entity", "item")
    return (
        "import os\n"
        "import json\n"
        "from flask import Flask, render_template, jsonify, abort\n\n"
        "app = Flask(__name__)\n"
        "DATA_PATH = os.path.join(os.path.dirname(__file__), \"" + case["data_file"] + "\")\n"
        "PORT = int(os.environ.get(\"PORT\", 5000))\n\n"
        "def " + loader + "():\n"
        "    \"\"\"唯一数据读取入口。\"\"\"\n"
        "    try:\n"
        "        with open(DATA_PATH, encoding=\"utf-8\") as f:\n"
        "            return json.load(f)\n"
        "    except (OSError, json.JSONDecodeError) as e:\n"
        "        app.logger.error(\"数据加载失败: %s\", e)\n"
        "        return []\n\n"
        "def _find(items, id):\n"
        "    \"\"\"按 id 查找单条。\"\"\"\n"
        "    for it in items:\n"
        "        if it.get(\"id\") == id:\n"
        "            return it\n"
        "    return None\n\n"
        "@app.route(\"" + rt["list"] + "\")\n"
        "def " + fns[0] + "():\n"
        "    \"\"\"列表页。\"\"\"\n"
        "    return render_template(\"list.html\", items=" + loader + "())\n\n"
        "@app.route(\"" + rt["detail_pattern"] + "\")\n"
        "def " + fns[1] + "(id):\n"
        "    \"\"\"详情页,不存在返回 404。\"\"\"\n"
        "    item = _find(" + loader + "(), id)\n"
        "    if item is None:\n"
        "        abort(404)\n"
        "    return render_template(\"detail.html\", item=item)\n\n"
        "@app.route(\"" + rt["api_list"] + "\")\n"
        "def " + fns[2] + "():\n"
        "    \"\"\"JSON 列表。\"\"\"\n"
        "    return jsonify(" + loader + "())\n\n"
        "@app.route(\"" + rt["api_detail_pattern"] + "\")\n"
        "def " + fns[3] + "(id):\n"
        "    \"\"\"JSON 详情,不存在返回 404。\"\"\"\n"
        "    item = _find(" + loader + "(), id)\n"
        "    if item is None:\n"
        "        return jsonify({\"error\": \"" + entity + " not found\"}), 404\n"
        "    return jsonify(item)\n\n"
        "@app.errorhandler(404)\n"
        "def not_found(e):\n"
        "    \"\"\"统一 404 页。\"\"\"\n"
        "    return render_template(\"base.html\", not_found=True), 404\n\n"
        "if __name__ == \"__main__\":\n"
        "    app.run(host=\"0.0.0.0\", port=PORT)\n"
    )


def _base_html(case):
    # 若用例声明了 must_contain_text,把这些字面文案写进共用页脚,
    # 列表页与详情页都会带上——离线参考实现也能过 must_contain_text 门禁。
    must = case.get("must_contain_text") or []
    footer = ("<footer class=\"site-footer\">" + " ".join(must) + "</footer>\n") if must else ""
    return (
        "<!doctype html>\n<html lang=\"zh\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<title>" + case["title"] + "</title>\n"
        "<link rel=\"stylesheet\" href=\"{{ url_for('static', filename='css/style.css') }}\">\n"
        "</head>\n<body>\n"
        "{% if not_found %}<h1 class=\"notfound\">404 Not Found</h1>\n"
        "{% else %}{% block body %}{% endblock %}{% endif %}\n"
        + footer +
        "<script src=\"{{ url_for('static', filename='js/main.js') }}\"></script>\n"
        "</body>\n</html>\n"
    )


def _list_card_child(case, rt, cls):
    """按 class 名启发式渲染一个列表卡片子元素(让样例也能过 list_card_children 硬校验)。"""
    if "cover" in cls or "img" in cls or "thumb" in cls:
        return "    <img class=\"" + cls + "\" src=\"{{ url_for('static', filename='img/' ~ item.id ~ '.png') }}\" alt=\"\">\n"
    if "title" in cls:
        return "    <h3 class=\"" + cls + "\"><a href=\"" + rt["detail_prefix"] + "/{{ item.id }}\">{{ item.title }}</a></h3>\n"
    if "summary" in cls:
        for cand in ("summary", "desc", "content"):
            if cand in case["required_fields"]:
                return "    <p class=\"" + cls + "\">{{ item." + cand + " }}</p>\n"
        return "    <p class=\"" + cls + "\">{{ item.title }}</p>\n"
    if "meta" in cls:
        return "    <div class=\"" + cls + "\">#{{ item.id }}</div>\n"
    return "    <div class=\"" + cls + "\">{{ item.title }}</div>\n"


def _list_html(case, rt):
    marker = case["list_marker"]
    children = case.get("list_card_children") or []
    if children:
        inner = "".join(_list_card_child(case, rt, c) for c in children)
    else:
        inner = ""
        if case.get("needs_images"):
            inner += "    <img class=\"thumb\" src=\"{{ url_for('static', filename='img/' ~ item.id ~ '.png') }}\" alt=\"\">\n"
        inner += "    <h3 class=\"card-title\"><a href=\"" + rt["detail_prefix"] + "/{{ item.id }}\">{{ item.title }}</a></h3>\n"
    return (
        "{% extends \"base.html\" %}\n{% block body %}\n"
        "<header class=\"topbar\"><h1 class=\"site-title\">" + case["title"] + "</h1></header>\n"
        "<main class=\"list\">\n"
        "{% for item in items %}\n"
        "  <article class=\"" + marker + "\">\n"
        + inner +
        "  </article>\n"
        "{% endfor %}\n</main>\n{% endblock %}\n"
    )


def _detail_html(case, rt):
    parts = [
        "{% extends \"base.html\" %}\n{% block body %}\n",
        "<h1 class=\"detail-title\">{{ item.title }}</h1>\n",
        "<div class=\"meta\">#{{ item.id }}</div>\n",
    ]
    if case.get("needs_images"):
        parts.append("<img class=\"main-img\" src=\"{{ url_for('static', filename='img/' ~ item.id ~ '.png') }}\" alt=\"\">\n")
    if "desc" in case["required_fields"]:
        text_field = "desc"
    elif "content" in case["required_fields"]:
        text_field = "content"
    else:
        text_field = "title"
    for m in case["detail_markers"]:
        if m.startswith("btn"):
            label = "加入购物车" if "cart" in m else ("立即购买" if "buy" in m else m)
            parts.append("<button class=\"" + m + "\">" + label + "</button>\n")
        else:
            parts.append("<div class=\"" + m + "\">{{ item." + text_field + " }}</div>\n")
    parts.append("<a class=\"back\" href=\"" + rt["list"] + "\">返回列表</a>\n")
    parts.append("{% endblock %}\n")
    return "".join(parts)


def _style_css(case):
    lines = ["/* 参考实现样式;包含 case.colors 全部配色 */\n",
             "body{font-family:sans-serif;margin:0;color:#333333}\n"]
    for idx, c in enumerate(case["colors"]):
        lines.append(".c" + str(idx) + "{color:" + c + ";border-color:" + c + "}\n")
    lines.append("." + case["list_marker"] + "{border:1px solid #eee;padding:12px;margin:12px}\n")
    for m in case["detail_markers"]:
        col = case["colors"][0] if case["colors"] else "#000000"
        lines.append("." + m + "{background:" + col + ";color:#fff;padding:8px}\n")
    return "".join(lines)


def _test_app_py(case, rt):
    return (
        "import os\nimport sys\nimport unittest\n"
        "sys.path.insert(0, os.path.join(os.path.dirname(__file__), \"..\"))\n"
        "from app import app\n\n"
        "class AppTest(unittest.TestCase):\n"
        "    def setUp(self):\n"
        "        self.c = app.test_client()\n\n"
        "    def test_api_list(self):\n"
        "        r = self.c.get(\"" + rt["api_list"] + "\")\n"
        "        self.assertEqual(r.status_code, 200)\n"
        "        self.assertGreaterEqual(len(r.get_json()), " + str(case["min_items"]) + ")\n\n"
        "    def test_api_detail_ok(self):\n"
        "        r = self.c.get(\"" + case["routes"]["api_detail_ok"] + "\")\n"
        "        self.assertEqual(r.status_code, 200)\n"
        "        self.assertIn(\"id\", r.get_json())\n\n"
        "    def test_api_detail_missing(self):\n"
        "        r = self.c.get(\"" + case["routes"]["api_detail_missing"] + "\")\n"
        "        self.assertEqual(r.status_code, 404)\n\n"
        "    def test_list_page(self):\n"
        "        r = self.c.get(\"" + rt["list"] + "\")\n"
        "        self.assertEqual(r.status_code, 200)\n\n"
        "if __name__ == \"__main__\":\n    unittest.main()\n"
    )


def _readme(case, rt):
    return (
        "# " + case["title"] + "(Harness-4 参考实现)\n\n"
        "> 由离线参考生成器产出,严格满足本用例契约。数据为占位内容。\n\n"
        "## 运行\n```bash\npip install -r requirements.txt\npython app.py\n```\n\n"
        "## 目录\n- `app.py` Flask 入口(全部路由)\n- `" + case["data_file"] + "` 数据源\n"
        "- `templates/` 页面\n- `static/` 样式与脚本\n- `tests/` 单元测试\n\n"
        "## 接口\n- `GET " + rt["list"] + "` 列表页\n"
        "- `GET " + rt["detail_pattern"] + "` 详情页\n"
        "- `GET " + rt["api_list"] + "` JSON 列表\n"
        "- `GET " + rt["api_detail_pattern"] + "` JSON 详情(缺失 404)\n"
    )


def _write(path, content, binary=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if binary:
        with open(path, "wb") as f:
            f.write(content)
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


def generate(case, constraints, out_dir):
    """确定性地把一个完整产物写入 out_dir。"""
    rt = _derive_routes(case)
    records = _make_records(case)

    _write(os.path.join(out_dir, "app.py"), _app_py(case, rt))
    _write(os.path.join(out_dir, "requirements.txt"), "Flask==3.0.3\n")
    _write(os.path.join(out_dir, "README.md"), _readme(case, rt))
    _write(os.path.join(out_dir, "templates/base.html"), _base_html(case))
    _write(os.path.join(out_dir, "templates/list.html"), _list_html(case, rt))
    _write(os.path.join(out_dir, "templates/detail.html"), _detail_html(case, rt))
    _write(os.path.join(out_dir, "static/css/style.css"), _style_css(case))
    _write(os.path.join(out_dir, "static/js/main.js"), "// 参考实现:无额外脚本\nconsole.log('ready');\n")
    _write(os.path.join(out_dir, case["data_file"]),
           json.dumps(records, ensure_ascii=False, indent=2) + "\n")
    _write(os.path.join(out_dir, "tests/test_app.py"), _test_app_py(case, rt))

    if case.get("needs_images"):
        for i in range(1, case["min_items"] + 1):
            _write(os.path.join(out_dir, "static/img/" + str(i) + ".png"), _PNG_1x1, binary=True)

    return True
