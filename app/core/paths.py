# -*- coding: utf-8 -*-
"""路径与工作目录解析。

工作目录（workdir）用于存放 wxpack 与各类缓存：
- 打包成单文件 exe 运行时，exe 所在目录可能只读（如放在 C:\\Program Files），
  因此优先使用 exe 同级的 `WxapkgToolData`，不可写时退回到「文档」目录。
- 开发（源码）运行时使用项目根目录。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "WxapkgTool"

# 打包后 PyInstaller 会把资源解压到 sys._MEIPASS
def resource_dir() -> Path:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base)
    return Path(__file__).resolve().parent.parent


def app_root() -> Path:
    """exe 或源码根目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except Exception:
        return False


def work_root() -> Path:
    """返回可写的工作根目录。"""
    if not getattr(sys, "frozen", False):
        return app_root()

    portable = app_root() / (APP_NAME + "Data")
    if _writable(portable):
        return portable

    docs = Path(os.path.expanduser("~")) / "Documents"
    fallback = docs / APP_NAME
    if _writable(fallback):
        return fallback

    tmp = Path(os.environ.get("TEMP", str(Path.home()))) / APP_NAME
    tmp.mkdir(parents=True, exist_ok=True)
    return tmp


def wxpack_dir() -> Path:
    """wxpack 目录：解包产出的 .wxapkg 与反编译源码都放在这里。"""
    d = work_root() / "wxpack"
    d.mkdir(parents=True, exist_ok=True)
    return d


# 包体统一放在 _packages/<AppID>/ 下，与源码目录（wxpack/<AppID>/）分开。
# 关键原因：反编译的「目录模式」要 -in 指向包目录，如果所有 AppID 的包平铺在一起，
# 反编译 B 时会把 A 的包也一起还原进 B 的源码目录（串包）。
PACKAGES_DIRNAME = "_packages"
DECRYPT_TMP_DIRNAME = "_decrypt_tmp"


def packages_root() -> Path:
    d = wxpack_dir() / PACKAGES_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def packages_dir(appid: str) -> Path:
    """某个 AppID 专属的包目录。"""
    d = packages_root() / appid
    d.mkdir(parents=True, exist_ok=True)
    return d


def decrypt_tmp_dir() -> Path:
    d = wxpack_dir() / DECRYPT_TMP_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def tools_dir() -> Path:
    """外部工具目录（内嵌的 KillWxapkg.exe 会释放到这里）。"""
    d = work_root() / "tools"
    d.mkdir(parents=True, exist_ok=True)
    return d
