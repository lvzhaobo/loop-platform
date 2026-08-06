"""PlatformPaths — 集中路径解析，消除裸 Path("loop/cases")、父目录 .env、sys.path 隐式定位。

用法:
    from engine.core.paths import PlatformPaths, load_config, find_root

    root = find_root()
    cases = PlatformPaths.CASES_DIR
    config = load_config()
"""

from __future__ import annotations

import os
import re
import warnings
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


# ── 仓库根发现 ──

@lru_cache(maxsize=1)
def find_root() -> Path:
    """从任意工作目录找到仓库根。

    策略：
    1. 环境变量 LOOP_ROOT
    2. 从当前目录逐级向上查找 engine/ + studio/ 特征目录
    3. 从本文件路径逐级向上查找
    4. 回退到当前工作目录
    """
    if (env := os.environ.get("LOOP_ROOT")):
        return Path(env).resolve()

    feature_dirs = {"engine", "studio"}

    for start in [Path.cwd(), Path(__file__).resolve()]:
        for p in [start, *start.parents]:
            if all((p / d).is_dir() for d in feature_dirs):
                return p.resolve()

    # 回退
    fallback = Path.cwd()
    warnings.warn(f"未找到仓库根（engine+studio），回退到 cwd: {fallback}")
    return fallback.resolve()


# ── 平台路径 ──

class PlatformPaths:
    """所有运行时路径与配置的单例解析点。
    
    访问旧 loop/ 路径时自动输出 DeprecationWarning。
    """

    ROOT: Path = find_root()

    # ── 数据目录（F1 迁移后从根直接访问）──
    CASES_DIR: Path = ROOT / "cases"
    DATA_DIR: Path = ROOT / "data"
    OUTPUT_DIR: Path = ROOT / "output"

    # ── 源码目录 ──
    ENGINE_DIR: Path = ROOT / "engine"
    PIPELINE_DIR: Path = ROOT / "pipeline"
    STUDIO_DIR: Path = ROOT / "studio"
    API_DIR: Path = ROOT / "api"
    ADAPTERS_DIR: Path = ROOT / "adapters"
    PROFILES_DIR: Path = ROOT / "profiles"
    RUN_PLANS_DIR: Path = DATA_DIR / "run_plans"
    RUN_EVENTS_DIR: Path = DATA_DIR / "run_events"

    # ── 配置文件 ──
    CONFIG_FILE: Path = ROOT / "config.env"
    ENV_FILE: Path = ROOT / ".env"

    # ── 旧路径（只读，用于兼容检查与 deprecation warning）──
    LEGACY_LOOP: Path = ROOT / "loop"
    LEGACY_CASES: Path = ROOT / "loop" / "cases"
    LEGACY_DATA: Path = ROOT / "loop" / "data"

    @classmethod
    def resolve(cls, relative: str | Path) -> Path:
        """将相对路径解析为绝对路径（基于 ROOT）。"""
        p = Path(relative)
        if p.is_absolute():
            return p
        return (cls.ROOT / p).resolve()

    @classmethod
    def guard_legacy(cls, path: Path) -> Path:
        """若路径指向旧 loop/ 目录，输出 DeprecationWarning 并建议新路径。"""
        resolved = path.resolve()
        legacy_root = cls.LEGACY_LOOP.resolve()
        if str(resolved).startswith(str(legacy_root) + os.sep):
            new_path = str(resolved).replace(
                str(legacy_root) + os.sep, str(cls.ROOT) + os.sep
            )
            warnings.warn(
                f"访问旧路径:{resolved}\n  → 请改用:{new_path}",
                DeprecationWarning,
                stacklevel=2,
            )
            # 如果新路径已存在（迁移完成），自动重定向
            if Path(new_path).exists():
                return Path(new_path)
        return resolved


# ── 统一配置加载 ──

def load_config() -> dict[str, str]:
    """统一配置加载，优先级：环境变量 > .env > config.env。

    返回 dict，可通过 os.environ 覆盖已导出的变量。
    """
    config: dict[str, str] = {}

    # 1. config.env（默认值，非机密开关）
    if PlatformPaths.CONFIG_FILE.is_file():
        _parse_env_file(PlatformPaths.CONFIG_FILE, config)

    # 2. .env（密钥与覆盖值）
    if PlatformPaths.ENV_FILE.is_file():
        _parse_env_file(PlatformPaths.ENV_FILE, config)

    # 3. 环境变量（最高优先级）
    config.update(os.environ)

    return config


def _parse_env_file(path: Path, target: dict[str, str]) -> None:
    """解析 export KEY=value 或 KEY=value 格式的 env 文件。"""
    export_re = re.compile(r'^\s*(?:export\s+)?([A-Za-z_]\w*)\s*=\s*["\']?(.*?)["\']?\s*$')
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                m = export_re.match(line)
                if m:
                    target[m.group(1)] = m.group(2)
    except OSError:
        pass
