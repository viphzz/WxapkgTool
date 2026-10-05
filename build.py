# -*- coding: utf-8 -*-
"""打包脚本：把 WxapkgTool 打成单文件 Windows exe。

用法：
    <venv-python> build.py            # 单文件（推荐分发）
    <venv-python> build.py --onedir   # 目录版（启动更快、便于排查）

产物在 dist/ 下。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT / "app"
DIST = ROOT / "dist"
BUILD = ROOT / "build"
NAME = "WxapkgTool"

# 需要一起打进 exe 的资源：(源路径, exe 内目录)
DATA = [
    (APP / "tools" / "KillWxapkg.exe", "tools"),
    (APP / "resources", "resources"),
]

HIDDEN = [
    "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
]

EXCLUDES = [
    "PySide6.Qt3DAnimation", "PySide6.Qt3DCore", "PySide6.QtBluetooth",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtMultimedia",
    "PySide6.QtNetworkAuth", "PySide6.QtNfc", "PySide6.QtOpenGL",
    "PySide6.QtPdf", "PySide6.QtPositioning", "PySide6.QtQml",
    "PySide6.QtQuick", "PySide6.QtRemoteObjects", "PySide6.QtSensors",
    "PySide6.QtSerialPort", "PySide6.QtSql", "PySide6.QtStateMachine",
    "PySide6.QtSvg", "PySide6.QtTest", "PySide6.QtTextToSpeech",
    "PySide6.QtWebChannel", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSockets", "PySide6.QtXml", "PySide6.QtDesigner",
    "PySide6.QtHelp", "PySide6.QtUiTools", "PySide6.QtScxml",
    "tkinter", "matplotlib", "numpy", "PIL", "pandas",
]


def main() -> int:
    onedir = "--onedir" in sys.argv

    # 仓库里不带 37MB 的反编译内核，缺了就先拉一次
    engine_exe = APP / "tools" / "KillWxapkg.exe"
    if not engine_exe.exists():
        try:
            import fetch_engine
        except ImportError:
            sys.path.insert(0, str(ROOT))
            import fetch_engine
        print("未找到反编译内核，开始下载 ...")
        if not fetch_engine.ensure():
            return 1

    missing = [str(p) for p, _ in DATA if not p.exists()]
    if missing:
        print("缺少必要资源：\n  " + "\n  ".join(missing))
        return 1

    # 注：不在脚本里预删旧产物——批量删除会被系统安全钩子拦下（超过 50 个文件的
    # 删除需要确认）。PyInstaller 的 --noconfirm 会直接覆盖同名输出。
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir" if onedir else "--onefile",
        "--windowed",
        "--name", NAME,
        "--workpath", str(BUILD),
        "--distpath", str(DIST),
        "--specpath", str(BUILD),
        "--icon", str(APP / "resources" / "app.ico"),
    ]
    for src, dst in DATA:
        cmd += ["--add-data", f"{src}{__import__('os').pathsep}{dst}"]
    for mod in HIDDEN:
        cmd += ["--hidden-import", mod]
    for mod in EXCLUDES:
        cmd += ["--exclude-module", mod]
    cmd.append(str(APP / "main.py"))

    print("执行：", " ".join(cmd))
    rc = subprocess.call(cmd)
    if rc != 0:
        return rc

    target = DIST / (NAME + ".exe") if not onedir else DIST / NAME / (NAME + ".exe")
    print("\n打包完成：", target)
    if target.exists():
        print(f"体积：{target.stat().st_size / 1024 / 1024:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
