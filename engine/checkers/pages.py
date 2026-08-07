"""Deterministic validation for acceptance schema v2 page and navigation contracts."""
from __future__ import annotations

import json
import posixpath
from collections import deque
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from . import register
from .base import Checker, CheckerResult, status_from_bool


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href is not None:
                self.hrefs.append(href)


def _safe_file(value):
    if not isinstance(value, str) or not value.endswith(".html") or "\\" in value:
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    return path.as_posix()


def _target_from_href(source, href):
    parsed = urlsplit(href)
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None
    target = posixpath.normpath(posixpath.join(posixpath.dirname(source), unquote(parsed.path)))
    return "<invalid>" if target == ".." or target.startswith("../") or target.startswith("/") else target


@register("pages")
class PagesChecker(Checker):
    """Validate declared pages, local anchors, declared navigation, and entry reachability."""
    name = "pages"

    def check(self, target_dir: str, *, run_id: str = "", acceptance_path: str = "") -> CheckerResult:
        checks = []
        try:
            contract = json.loads(Path(acceptance_path).read_text(encoding="utf-8")) if acceptance_path else {}
        except (OSError, json.JSONDecodeError):
            checks.append({"name": "页面合同", "pass": False, "status": "failed", "detail": "acceptance v2 JSON 无法读取"})
            return CheckerResult(0, 1, checks, False)
        if contract.get("schema_version") != 2 or "pages" not in contract:
            checks.append({"name": "页面合同", "pass": True, "status": "skipped", "detail": "旧 acceptance 未声明 schema_version=2 pages 合同"})
            return CheckerResult(1, 1, checks, True)

        pages = contract.get("pages")
        navigation = contract.get("navigation")
        entry = _safe_file(contract.get("entry"))
        valid_pages = isinstance(pages, list) and pages and all(isinstance(page, dict) for page in pages)
        valid_navigation = isinstance(navigation, list) and all(isinstance(item, dict) for item in navigation)
        page_files = [_safe_file(page.get("file")) for page in pages] if valid_pages else []
        page_ids = [page.get("id") for page in pages] if valid_pages else []
        entry_count = sum(page.get("entry") is True for page in pages) if valid_pages else 0
        if (not entry or not valid_navigation or not valid_pages or any(not item for item in page_files)
                or len(set(page_files)) != len(page_files) or any(not isinstance(item, str) or not item for item in page_ids)
                or len(set(page_ids)) != len(page_ids) or entry not in page_files or entry_count != 1
                or next((page.get("file") for page in pages if page.get("entry") is True), None) != entry):
            checks.append({"name": "页面合同", "pass": False, "status": "failed", "detail": "pages/entry 必须是唯一安全 HTML 文件，且只有一个 entry"})
            return CheckerResult(0, 1, checks, False)

        declared = set(page_files)
        links = {}
        for filename in page_files:
            path = Path(target_dir, filename)
            exists = path.is_file()
            checks.append({"name": f"页面存在:{filename}", "pass": exists, "status": status_from_bool(exists), "detail": "存在" if exists else "缺失"})
            if not exists:
                continue
            parser = _Links()
            try:
                parser.feed(path.read_text(encoding="utf-8", errors="replace"))
            except OSError as exc:
                checks.append({"name": f"页面读取:{filename}", "pass": False, "status": "failed", "detail": str(exc)[:120]})
                continue
            links[filename] = {_target_from_href(filename, href) for href in parser.hrefs}
            for target in links[filename]:
                if target is None:
                    continue
                exists = target != "<invalid>" and Path(target_dir, target).is_file()
                checks.append({"name": f"链接存在:{filename}→{target}", "pass": exists, "status": status_from_bool(exists), "detail": "存在" if exists else "本地跳转目标缺失或越界"})

        edges = {filename: set() for filename in page_files}
        seen_navigation = set()
        for item in navigation:
            source, target = _safe_file(item.get("from")), _safe_file(item.get("to"))
            key = (source, target)
            valid = source in declared and target in declared and key not in seen_navigation
            seen_navigation.add(key)
            present = valid and target in links.get(source, set())
            checks.append({"name": f"声明跳转:{source}→{target}", "pass": present, "status": status_from_bool(present), "detail": "HTML 链接已验证" if present else "合同引用无效、重复或 HTML 未包含该链接"})
            if present:
                edges[source].add(target)

        reachable, queue = {entry}, deque([entry])
        while queue:
            for target in edges[queue.popleft()]:
                if target not in reachable:
                    reachable.add(target)
                    queue.append(target)
        for filename in page_files:
            passed = filename in reachable
            checks.append({"name": f"入口可达:{filename}", "pass": passed, "status": status_from_bool(passed), "detail": "从入口的声明导航可达" if passed else "未从入口的声明导航可达"})
        passed = sum(check["pass"] for check in checks)
        return CheckerResult(passed, len(checks), checks, passed == len(checks))
