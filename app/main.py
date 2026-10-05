# -*- coding: utf-8 -*-
"""WxapkgTool 主界面。

界面布局完全对照参考图：
  ─ 选择需要解包的包 ─
  [选择解包文件]        此小程序无分包        [刷新反编译包]
  ─ 选择反编译的包 ─
  [ 下拉框  v ]
           点我前往查看使用教程
  ┌ 信息区 ────────────────────────────────┐
  │ ...                                    │
  └────────────────────────────────────────┘
  ─ 操作区 ─
  [新版反编译] [打开源码目录] [修复源码]
  [旧版反编译] [清除源码目录] [转成uni-app]
"""

from __future__ import annotations

import os
import shutil
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, QThread, Signal
from PySide6.QtGui import QDesktopServices, QFont, QIcon
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QMessageBox, QPushButton, QSizePolicy, QTextEdit, QVBoxLayout,
    QWidget,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import engine, repair, uniapp  # noqa: E402
from core.paths import packages_root, resource_dir, wxpack_dir  # noqa: E402

TUTORIAL_URL = "https://github.com/Ackites/KillWxapkg"

HELP_TEXT = """如果反编译包有分包，请选择反编译的包为主包
反编译成功源码放在 wxpack 文件夹下对应的 AppID 目录
执行的命令为："""


# ---------------------------------------------------------------- 样式

QSS_TEMPLATE = """
QWidget#Root { background: #ffffff; }

QLabel { color: #333333; font-size: 13px; }

QLabel#SubTip {
    color: #e64340; font-size: 13px; font-weight: 600;
    qproperty-alignment: AlignCenter;
}

QLabel#DividerText { color: #8a8f99; font-size: 12px; }
QFrame#DividerLine { background: #dcdfe6; border: none; }

QPushButton#Primary {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #5ba0e2, stop:0.55 #4789d4, stop:1 #3b7ec8);
    color: #ffffff;
    border: 1px solid #3f83cb;
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 13px;
    font-weight: 600;
    min-height: 22px;
}
QPushButton#Primary:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #79b4ec, stop:0.55 #5fa3e2, stop:1 #4f95d8);
    border-color: #5599da;
}
QPushButton#Primary:pressed {
    background: #3574bb;
    border-color: #3574bb;
}
QPushButton#Primary:disabled {
    background: #a9c8e8; border-color: #a9c8e8; color: #f2f2f2;
}

QPushButton#Link {
    background: transparent; border: none;
    color: #e64340; font-size: 13px; font-weight: 600;
}
QPushButton#Link:hover { color: #ff6b68; }

QComboBox {
    background: #ffffff;
    border: 1px solid #dcdfe6;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 13px;
    color: #333333;
    min-height: 22px;
}
QComboBox:hover { border-color: #4a90d9; }
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border: none;
}
QComboBox::down-arrow {
    image: url(__RES__/arrow_down.png);
    width: 12px; height: 12px;
}
QComboBox QAbstractItemView {
    border: 1px solid #dcdfe6; background: #ffffff;
    selection-background-color: #4a90d9; selection-color: #ffffff;
    outline: none;
}

QTextEdit#Log {
    background: #ffffff;
    border: 1px solid #dcdfe6;
    border-radius: 3px;
    color: #333333;
    font-size: 12px;
    padding: 6px;
}
QScrollBar:vertical {
    background: #f5f6f7; width: 10px; margin: 0; border: none;
}
QScrollBar::handle:vertical { background: #c8ccd4; border-radius: 5px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #aab0ba; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""


def resource_path(*parts: str) -> Path:
    """资源目录：打包后在 _MEIPASS，源码运行在 app/ 下。"""
    base = resource_dir()
    p = base.joinpath(*parts)
    if p.exists():
        return p
    return Path(__file__).resolve().parent.joinpath(*parts)


def build_qss() -> str:
    res = resource_path("resources")
    return QSS_TEMPLATE.replace("__RES__", res.as_posix())


# ---------------------------------------------------------------- 小部件

class Divider(QWidget):
    """形如  ─── 标题 ───  的分隔行。"""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(8)

        left = QFrame()
        left.setObjectName("DividerLine")
        left.setFrameShape(QFrame.HLine)
        left.setFixedHeight(1)
        left.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        right = QFrame()
        right.setObjectName("DividerLine")
        right.setFrameShape(QFrame.HLine)
        right.setFixedHeight(1)
        right.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        label = QLabel(text)
        label.setObjectName("DividerText")

        lay.addWidget(left, 1)
        lay.addWidget(label, 0)
        lay.addWidget(right, 1)


def primary_button(text: str, width: int = 0, icon: str = "") -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("Primary")
    b.setCursor(Qt.PointingHandCursor)
    if icon:
        path = resource_path("resources", icon)
        if path.exists():
            b.setIcon(QIcon(str(path)))
            b.setIconSize(QSize(15, 15))
    if width:
        b.setFixedWidth(width)
    return b


# ---------------------------------------------------------------- 后台任务

class Worker(QObject):
    log = Signal(str)
    done = Signal(str, object)   # (任务名, 结果)
    failed = Signal(str, str)    # (任务名, 错误)

    def __init__(self, name: str, fn) -> None:
        super().__init__()
        self.name = name
        self.fn = fn

    def run(self) -> None:
        try:
            result = self.fn(self.log.emit)
        except Exception as exc:  # noqa: BLE001
            detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            self.failed.emit(self.name, detail)
            return
        self.done.emit(self.name, result)


# ---------------------------------------------------------------- 主窗口

class MainWindow(QWidget):

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Root")
        self.setWindowTitle("微信小程序反编译工具  ·  KillWxapkg")
        self.setMinimumWidth(620)
        self.resize(620, 680)

        self.packages: list[Path] = []
        self.appid: str | None = None
        self.has_subpackage = False
        self._busy = False
        self._thread: QThread | None = None
        self._worker: Worker | None = None

        self._build_ui()
        self._append(HELP_TEXT)
        engine.migrate_flat_packages(self._append)
        self.refresh_packages(silent=True)

    # ------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 14)
        root.setSpacing(6)

        # ---- 选择需要解包的包
        root.addWidget(Divider("选择需要解包的包"))

        row = QHBoxLayout()
        row.setSpacing(10)
        self.btn_choose = primary_button("选择解包文件", 132, "ic_choose.png")
        self.lbl_subtip = QLabel("此小程序无分包")
        self.lbl_subtip.setObjectName("SubTip")
        self.btn_refresh = primary_button("刷新反编译包", 132, "ic_refresh.png")

        row.addWidget(self.btn_choose, 0)
        row.addStretch(1)
        row.addWidget(self.lbl_subtip, 0)
        row.addStretch(1)
        row.addWidget(self.btn_refresh, 0)
        root.addLayout(row)

        root.addSpacing(6)

        # ---- 选择反编译的包
        root.addWidget(Divider("选择反编译的包"))
        self.combo = QComboBox()
        self.combo.setMinimumHeight(32)
        self.combo.setPlaceholderText("请先选择解包文件并刷新")
        root.addWidget(self.combo)

        self.btn_tutorial = QPushButton("点我前往查看使用教程")
        self.btn_tutorial.setObjectName("Link")
        self.btn_tutorial.setCursor(Qt.PointingHandCursor)
        tip_row = QHBoxLayout()
        tip_row.addStretch(1)
        tip_row.addWidget(self.btn_tutorial)
        tip_row.addStretch(1)
        root.addLayout(tip_row)

        # ---- 信息 / 日志
        self.log = QTextEdit()
        self.log.setObjectName("Log")
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(190)
        root.addWidget(self.log, 1)

        # ---- 操作区
        root.addWidget(Divider("操作区"))

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        self.btn_new = primary_button("新版反编译", 0, "ic_new.png")
        self.btn_open = primary_button("打开源码目录", 0, "ic_open.png")
        self.btn_fix = primary_button("修复源码", 0, "ic_fix.png")
        self.btn_clear = primary_button("清除源码目录", 0, "ic_clear.png")
        self.btn_uni = primary_button("转成uni-app", 0, "ic_uni.png")

        grid.addWidget(self.btn_new, 0, 0)
        grid.addWidget(self.btn_open, 0, 1)
        grid.addWidget(self.btn_fix, 0, 2)
        grid.addWidget(self.btn_clear, 1, 0)
        grid.addWidget(self.btn_uni, 1, 1, 1, 2)
        for col in range(3):
            grid.setColumnStretch(col, 1)
        root.addLayout(grid)

        # ---- 信号
        self.btn_choose.clicked.connect(self.on_choose)
        self.btn_refresh.clicked.connect(lambda: self.refresh_packages())
        self.btn_tutorial.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(TUTORIAL_URL)))
        self.combo.currentIndexChanged.connect(self.on_combo_changed)
        self.btn_new.clicked.connect(self.on_new_decompile)
        self.btn_open.clicked.connect(self.on_open_src)
        self.btn_fix.clicked.connect(self.on_fix)
        self.btn_clear.clicked.connect(self.on_clear)
        self.btn_uni.clicked.connect(self.on_uniapp)

    # ------------------------------------------------------------ 日志

    def _append(self, text: str) -> None:
        self.log.append(text)
        self.log.verticalScrollBar().setValue(
            self.log.verticalScrollBar().maximum())

    # ------------------------------------------------------------ 状态

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        for b in (self.btn_choose, self.btn_refresh, self.btn_new,
                  self.btn_open, self.btn_fix, self.btn_clear, self.btn_uni):
            b.setEnabled(not busy)
        QApplication.setOverrideCursor(Qt.WaitCursor) if busy else \
            QApplication.restoreOverrideCursor()

    def _selected_package(self) -> Path | None:
        if self.combo.currentIndex() < 0:
            return None
        return self.combo.currentData()

    def _run_task(self, name: str, fn) -> None:
        if self._busy:
            return
        self._set_busy(True)
        thread = QThread(self)
        worker = Worker(name, fn)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.log.connect(self._append)
        worker.done.connect(self._on_task_done)
        worker.failed.connect(self._on_task_failed)
        worker.done.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _on_task_done(self, name: str, result: object) -> None:
        self._set_busy(False)
        if name == "unpack":
            res = result  # UnpackResult
            self.appid = res.appid or self.appid
            self.has_subpackage = bool(res.sub_packages)
            self._update_subtip()
            self.refresh_packages(silent=True)
            self._select_package(res.main_package)
        elif name == "new":
            self._append("反编译成功！")
            src = self._src_dir()
            if src is not None and (src / "敏感信息报告.txt").exists():
                self._append("敏感信息报告已生成：sensitive_data.json（原始）+ 敏感信息报告.txt（可读）")
                self._append("点【打开源码目录】就能看到，都在源码目录根下。")
            self._update_subtip()
        self._thread = None
        self._worker = None

    def _on_task_failed(self, name: str, detail: str) -> None:
        self._set_busy(False)
        label = {"unpack": "解包", "new": "新版反编译",
                 "fix": "修复源码", "clear": "清除源码目录", "uni": "转 uni-app"}.get(name, name)
        self._append(f"{label}失败：{detail}")
        QMessageBox.warning(self, "操作失败", f"{label}失败：\n{detail}")
        self._thread = None
        self._worker = None

    def _update_subtip(self) -> None:
        if self.has_subpackage:
            self.lbl_subtip.setText("此小程序有分包")
        else:
            self.lbl_subtip.setText("此小程序无分包")

    # ------------------------------------------------------------ 刷新

    def refresh_packages(self, silent: bool = False) -> None:
        current_path = self._selected_package()
        # 扫描 _packages/<AppID>/*.wxapkg。只扫一层子目录：
        # _decrypt_tmp 之类的临时目录不在 _packages 下，天然被排除。
        self.packages = sorted(
            (p for p in packages_root().glob("*/*.wxapkg") if p.is_file()),
            key=lambda p: (p.parent.name, p.name.startswith("_"), p.name),
        )
        self.combo.blockSignals(True)
        self.combo.clear()
        for p in self.packages:
            self.combo.addItem(p.name, p)
        self.combo.blockSignals(False)

        if self.packages:
            if current_path in self.packages:
                self._select_package(current_path)
            if not silent:
                apps = sorted({engine.package_appid(p) for p in self.packages})
                self._append(f"共发现 {len(self.packages)} 个反编译包，"
                             f"涉及 {len(apps)} 个小程序。")
        else:
            if not silent:
                self._append("暂无可反编译的包，请先「选择解包文件」。")
        self._sync_appid_from_combo()

    def _select_package(self, target) -> None:
        """按完整路径（Path）或文件名选中下拉项。"""
        by_path = isinstance(target, Path)
        for i in range(self.combo.count()):
            if by_path:
                if self.combo.itemData(i) == target:
                    self.combo.setCurrentIndex(i)
                    return
            elif self.combo.itemText(i) == target:
                self.combo.setCurrentIndex(i)
                return

    def _sync_appid_from_combo(self) -> None:
        p = self._selected_package()
        if p is None:
            self.has_subpackage = False
            self._update_subtip()
            return
        # 包放在 _packages/<AppID>/ 下，父目录名就是 AppID，最可靠
        self.appid = engine.package_appid(p)
        self.has_subpackage = engine.subpackage_present(p)
        self._update_subtip()

    def on_combo_changed(self, _idx: int) -> None:
        self._sync_appid_from_combo()

    # ------------------------------------------------------------ 选择解包文件

    def _default_dir(self) -> str:
        candidates = [
            Path(os.environ.get("APPDATA", "")) / "Tencent" / "xwechat" / "radium" / "Applet" / "packages",
            Path(os.environ.get("APPDATA", "")) / "Tencent" / "WeChat" / "radium" / "Applet" / "packages",
            Path(os.path.expanduser("~")) / "Documents" / "WeChat Files" / "Applet",
            wxpack_dir(),
        ]
        for c in candidates:
            if c.exists():
                return str(c)
        return str(Path.home())

    def on_choose(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择需要解包的小程序包（一般选 __APP__.wxapkg）",
            self._default_dir(),
            "微信小程序包 (*.wxapkg);;所有文件 (*.*)",
        )
        if not path:
            return
        chosen = Path(path)

        appid, pkgs = engine.collect_sources(chosen)
        if appid is None:
            appid = self.appid
        if appid is None:
            QMessageBox.warning(
                self, "无法识别 AppID",
                "没有从所选路径推断出 AppID（wx + 16 位十六进制）。\n"
                "请选择微信缓存目录 Applet\\packages\\<AppID>\\<版本>\\ 下的\n"
                "__APP__.wxapkg，或直接选择该 AppID 目录。")
            return

        subs = [p for p in pkgs if p.name.startswith("_")]
        self._append("")
        self._append(f"已选择：{chosen}")
        self._append(f"AppID：{appid}")
        if subs:
            self._append(f"同目录下发现 {len(subs)} 个分包，将一并解包。")

        self._run_task("unpack", lambda log: engine.unpack(chosen, log))

    # ------------------------------------------------------------ 反编译

    def on_new_decompile(self) -> None:
        pkg = self._selected_package()
        if pkg is None:
            QMessageBox.information(self, "提示", "请先「选择解包文件」并刷新反编译包。")
            return
        self._sync_appid_from_combo()
        appid = self.appid or pkg.stem
        # 有分包时必须用目录模式，且 -in 指向该 AppID 专属的包目录，
        # 否则分包内容会缺，或者把别的小程序的包也一起反编译进来
        use_dir = engine.subpackage_present(pkg)

        if use_dir:
            subs = sorted(q.name for q in pkg.parent.glob("_*.wxapkg"))
            self._append(f"检测到 {len(subs)} 个分包：{'、'.join(subs)}")
            self._append("将以目录模式反编译，主包 + 分包一起还原。")
        self._append("")
        self._append(f"【新版反编译】目标：{pkg.name}")

        def task(log):
            res, src = engine.decompile(pkg, appid, use_dir, log)
            if not res.ok:
                raise RuntimeError(f"KillWxapkg 返回码 {res.returncode}")
            log(f"源码目录：{src}")
            return src

        self._run_task("new", task)

    def on_old_decompile(self) -> None:
        """旧版反编译已下线，保留占位以便旧配置不报错。"""
        QMessageBox.information(self, "提示", "旧版反编译已下线，请使用「新版反编译」。")

    # ------------------------------------------------------------ 源码目录

    def _src_dir(self) -> Path | None:
        pkg = self._selected_package()
        appid = self.appid or (engine.guess_appid(pkg) if pkg else None)
        if not appid:
            return None
        return wxpack_dir() / appid

    def on_open_src(self) -> None:
        d = self._src_dir()
        if d is None:
            QMessageBox.information(self, "提示", "尚未确定 AppID，请先选择包。")
            return
        if not d.exists():
            QMessageBox.information(self, "提示", f"源码目录还不存在：\n{d}\n请先执行反编译。")
            return
        os.startfile(str(d))  # noqa: S606  (Windows 打开资源管理器)

    def on_clear(self) -> None:
        d = self._src_dir()
        if d is None:
            QMessageBox.information(self, "提示", "尚未确定 AppID，请先选择包。")
            return
        if not d.exists():
            QMessageBox.information(self, "提示", f"源码目录不存在：\n{d}")
            return
        ret = QMessageBox.question(
            self, "确认清除",
            f"将删除整个源码目录（含反编译源码）：\n{d}\n\n此操作不可撤销，确定继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        self._append("")
        self._append(f"【清除源码目录】{d}")

        def task(log):
            shutil.rmtree(d, ignore_errors=True)
            log("已清除。")
            return True

        self._run_task("clear", task)

    # ------------------------------------------------------------ 修复源码

    def on_fix(self) -> None:
        d = self._src_dir()
        if d is None or not d.exists():
            QMessageBox.information(self, "提示", "源码目录不存在，请先执行反编译。")
            return
        appid = self.appid or d.name
        self._append("")
        self._append(f"【修复源码】{d}")

        def task(log):
            stats = repair.repair(d, appid, log)
            ok, problems = repair.health_check(d)
            if ok:
                log("体检通过：app.json 页面四件套齐全。")
            else:
                log("体检发现待处理项：")
                for p in problems:
                    log("  · " + p)
            return stats

        self._run_task("fix", task)

    # ------------------------------------------------------------ 转 uni-app

    def on_uniapp(self) -> None:
        d = self._src_dir()
        if d is None or not d.exists():
            QMessageBox.information(self, "提示", "源码目录不存在，请先执行反编译。")
            return
        out = wxpack_dir() / f"{d.name}_uniapp"
        self._append("")
        self._append(f"【转成 uni-app】{d}  →  {out}")

        def task(log):
            return uniapp.convert(d, out, log)

        self._run_task("uni", task)


# ---------------------------------------------------------------- 环境自检

def run_doctor(argv: list[str]) -> int:
    """命令行自检：`WxapkgTool.exe --doctor [--in=<包路径>]`。

    结果写到 <工作目录>/doctor.txt，方便在无控制台的 windowed 版本里排查问题。
    """
    from core.paths import tools_dir, work_root

    lines: list[str] = []

    def add(msg: str) -> None:
        lines.append(msg)

    add("WxapkgTool 环境自检")
    add("=" * 60)
    add(f"frozen          : {bool(getattr(sys, 'frozen', False))}")
    add(f"工作目录        : {work_root()}")
    add(f"wxpack 目录     : {wxpack_dir()}")
    add(f"工具目录        : {tools_dir()}")

    exe_path = None
    try:
        exe_path = engine.ensure_engine(add)
        add(f"内核路径        : {exe_path}")
        add(f"内核体积        : {exe_path.stat().st_size / 1024 / 1024:.1f} MB")
        add(f"内核 MD5        : {engine._md5(exe_path)}")
        add(f"内核 MD5 校验   : {'通过' if engine._md5(exe_path) == engine.ENGINE_MD5 else '不一致！'}")
    except Exception as exc:  # noqa: BLE001
        add(f"内核释放失败    : {exc}")

    add(f"Python 运行时   : {sys.version.split()[0]}")

    existing = sorted(p.name for p in packages_root().glob("*/*.wxapkg"))
    add(f"已解包包数量    : {len(existing)}" + (f"（{', '.join(existing[:5])}…）" if existing else ""))
    appids = sorted({engine.package_appid(p) for p in packages_root().glob("*/*.wxapkg")})
    add(f"涉及 AppID      : {len(appids)} 个" + (f"（{', '.join(appids[:5])}…）" if appids else ""))

    target = None
    for a in argv:
        if a.startswith("--in="):
            target = Path(a[5:].strip('"'))

    if target and target.exists() and exe_path:
        add("")
        add("=" * 60)
        add(f"真实流程测试    : {target}")
        add("（解包 → 反编译 → 工程体检，全流程）")
        try:
            res_unpack = engine.unpack(target, add)
            add(f"识别 AppID      : {res_unpack.appid}")
            add(f"主包            : {res_unpack.main_package.name}")
            subs = [p.name for p in res_unpack.sub_packages]
            add(f"分包            : {', '.join(subs) if subs else '无'}")
            run_res, src = engine.decompile(res_unpack.main_package,
                                            res_unpack.appid,
                                            bool(subs), add)
            add(f"返回码          : {run_res.returncode}")
            add(f"源码目录        : {src}")
            ok2, probs = repair.health_check(src)
            add(f"工程体检        : {'通过' if ok2 else '待处理 ' + str(probs[:5])}")
        except Exception as exc:  # noqa: BLE001
            add(f"流程失败        : {exc}")
            add(traceback.format_exc())
    elif target:
        add(f"指定路径不存在或内核不可用：{target}")

    report = "\n".join(lines)
    try:
        report_file = work_root() / "doctor.txt"
    except Exception:
        report_file = Path(os.environ.get("TEMP", ".")) / "WxapkgTool_doctor.txt"
    try:
        report_file.write_text(report, encoding="utf-8")
    except OSError:
        report_file = Path(os.environ.get("TEMP", ".")) / "WxapkgTool_doctor.txt"
        report_file.write_text(report, encoding="utf-8")

    # windowed 模式下没有控制台，sys.stdout 可能为 None
    try:
        if sys.stdout is not None:
            print(report)
            print(f"\n报告已写入：{report_file}")
    except Exception:
        pass
    return 0


# ---------------------------------------------------------------- 入口

def main() -> int:
    if "--doctor" in sys.argv or "--selfcheck" in sys.argv:
        return run_doctor(sys.argv)

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("WxapkgTool")
    app.setStyleSheet(build_qss())

    font = QFont("Microsoft YaHei UI", 9)
    font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(font)

    icon_file = resource_path("resources", "app.ico")
    if icon_file.exists():
        app.setWindowIcon(QIcon(str(icon_file)))

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
