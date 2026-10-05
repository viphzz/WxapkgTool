# -*- coding: utf-8 -*-
"""KillWxapkg 引擎封装：定位可执行文件、解密/解包、调用反编译。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

from .paths import resource_dir, tools_dir

ENGINE_NAME = "KillWxapkg.exe"
# 官方 v2.4.1 windows/amd64 版本校验值
ENGINE_MD5 = "5593a83f60f742bfb27c4fef756dfae7"

# 创建进程时不弹出黑窗口
_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

Logger = Callable[[str], None]


def _noop(_msg: str) -> None:
    pass


# ---------------------------------------------------------------- 引擎定位

def ensure_engine(log: Logger = _noop) -> Path:
    """把内嵌的 KillWxapkg.exe 释放到工作目录并返回路径。

    优先使用 tools 目录中已经存在的同名校验正确的文件。
    """
    target = tools_dir() / ENGINE_NAME
    if target.exists() and _md5(target) == ENGINE_MD5:
        return target

    bundled = resource_dir() / "tools" / ENGINE_NAME
    if not bundled.exists():
        # 源码方式运行时的位置
        bundled = Path(__file__).resolve().parent.parent / "tools" / ENGINE_NAME
    if not bundled.exists():
        raise FileNotFoundError(
            "未找到内置的 KillWxapkg.exe，请确认 tools 目录完整。"
        )

    log("正在释放反编译引擎 KillWxapkg.exe ...")
    shutil.copy2(bundled, target)
    return target


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def engine_version() -> str:
    return "KillWxapkg v2.4.1"


# ---------------------------------------------------------------- wxapkg 解析

# wxapkg 文件头：0xBE 表示已解密；否则为微信加密包（V1MMWX）
def is_encrypted(path: Path) -> bool:
    try:
        with open(path, "rb") as fp:
            head = fp.read(1)
    except OSError:
        return False
    return not head or head[0] != 0xBE


def read_entries(path: Path) -> list[str]:
    """读取（已解密的）wxapkg 内的文件名列表。"""
    names: list[str] = []
    try:
        with open(path, "rb") as fp:
            data = fp.read()
    except OSError:
        return names
    if not data or data[0] != 0xBE or len(data) < 18:
        return names
    try:
        (info1,) = struct.unpack(">I", data[1:5])
        (index_len,) = struct.unpack(">I", data[5:9])
        (body_len,) = struct.unpack(">I", data[9:13])
        (count,) = struct.unpack(">I", data[14:18])
        start = 18 + index_len
        if start + count * 4 + info1 > len(data):
            return names
        off = start
        for _ in range(count):
            (name_len,) = struct.unpack(">I", data[off:off + 4])
            off += 4
            name = data[off:off + name_len].decode("utf-8", "ignore")
            off += name_len
            off += 8  # offset + size
            names.append(name)
        # index 结束后是 0xED 标记与 body
        _ = body_len
    except Exception:
        return names
    return names


# ---------------------------------------------------------------- AppID

APPID_RE = re.compile(r"^wx[0-9a-f]{16}$", re.I)


def guess_appid(path: Path) -> Optional[str]:
    """从文件/目录名推断 AppID。"""
    name = path.name
    if path.is_file():
        name = path.stem
    name = name.strip("_")
    if APPID_RE.match(name):
        return name.lower()

    # 从缓存路径 .../packages/<appid>/<version>/ 推断
    for part in reversed(path.parts):
        if APPID_RE.match(part):
            return part.lower()

    # 尝试从包内文件名推断
    if path.is_dir():
        for f in path.glob("*.wxapkg"):
            if APPID_RE.match(f.stem):
                return f.stem.lower()
    return None


# ---------------------------------------------------------------- 运行

@dataclass
class RunResult:
    returncode: int
    stdout: str
    command: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def run_killwxapkg(args: list[str], cwd: Optional[Path] = None,
                   log: Logger = _noop) -> RunResult:
    exe = ensure_engine(log)
    cmd = [str(exe)] + args
    quoted = " ".join(_q(a) for a in cmd)
    log("执行的命令为：")
    log(quoted)

    proc = subprocess.run(
        cmd,
        cwd=str(cwd or tools_dir()),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_CREATE_NO_WINDOW,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    for line in out.splitlines():
        if line.strip():
            log(line)
    return RunResult(proc.returncode, out, quoted)


def _q(arg: str) -> str:
    return f'"{arg}"' if " " in arg else arg


# ---------------------------------------------------------------- 解包（解密）

@dataclass
class UnpackResult:
    appid: str
    main_package: Path
    packages: list[Path]          # 已解密、已就位的全部包
    sub_packages: list[Path]      # 分包（不含主包）


def _looks_like_subpackage(name: str) -> bool:
    # 微信分包文件名形如 _pages_my_.wxapkg
    return name.startswith("_") and name.endswith(".wxapkg")


def package_appid(pkg: Path) -> str:
    """判断一个已就位的包属于哪个 AppID。

    新布局下包放在 _packages/<AppID>/ 里，父目录名就是答案，最可靠。
    这里原样返回目录名（不转小写），保证和 `wxpack/<AppID>` 源码目录严格对应。
    """
    if APPID_RE.match(pkg.parent.name):
        return pkg.parent.name
    return pkg.stem


def migrate_flat_packages(log: Logger = _noop) -> int:
    """把旧版平铺在 wxpack/ 顶层的包迁到 _packages/<AppID>/。

    分包文件名（_xxx_.wxapkg）里不含 AppID，所以只有在「顶层只有一个主包」时
    才能安全地把孤儿分包归给它；有多个主包时无法判断归属，统一挪到
    _packages/_unassigned/ 并提示用户重新解包。
    """
    from .paths import packages_root, wxpack_dir

    wx = wxpack_dir()
    flat = [p for p in wx.glob("*.wxapkg") if p.is_file()]
    if not flat:
        return 0

    mains = [p for p in flat if not _looks_like_subpackage(p.name)]
    subs = [p for p in flat if _looks_like_subpackage(p.name)]
    moved = 0

    for m in mains:
        dest = packages_root() / (guess_appid(m) or m.stem)
        dest.mkdir(parents=True, exist_ok=True)
        shutil.move(str(m), str(dest / m.name))
        moved += 1

    if subs:
        if len(mains) == 1:
            dest = packages_root() / (guess_appid(mains[0]) or mains[0].stem)
            dest.mkdir(parents=True, exist_ok=True)
            for s in subs:
                shutil.move(str(s), str(dest / s.name))
                moved += 1
        else:
            dest = packages_root() / "_unassigned"
            dest.mkdir(parents=True, exist_ok=True)
            for s in subs:
                shutil.move(str(s), str(dest / s.name))
                moved += 1
            log(f"注意：{len(subs)} 个分包无法判断属于哪个 AppID，已挪到 "
                f"{dest}，请重新「选择解包文件」以恢复归属。")

    if moved:
        log(f"已把 {moved} 个包整理到 _packages\\<AppID>\\ 下。")
    return moved


def collect_sources(chosen: Path) -> tuple[Optional[str], list[Path]]:
    """根据用户选择的文件/目录，找出所有相关 wxapkg。

    返回 (appid, 包文件列表)。
    """
    if chosen.is_dir():
        pkgs = sorted(chosen.glob("*.wxapkg"))
        appid = guess_appid(chosen)
    else:
        pkgs = [chosen]
        appid = guess_appid(chosen)
        # 同目录下的分包一起带上
        for f in chosen.parent.glob("*.wxapkg"):
            if f != chosen:
                pkgs.append(f)

    if appid is None and pkgs:
        appid = guess_appid(pkgs[0])
    return appid, pkgs


def unpack(chosen: Path, log: Logger = _noop) -> UnpackResult:
    """解密并把包按 AppID 归档到 wxpack/_packages/<AppID>/。

    对应界面上的「选择解包文件」这一步。
    """
    from .paths import decrypt_tmp_dir, packages_dir

    appid, pkgs = collect_sources(chosen)
    if not pkgs:
        raise FileNotFoundError("所选位置没有找到 .wxapkg 文件。")

    dest = packages_dir(appid or "unknown")
    # 同一个 AppID 重新解包时，先清掉旧包避免残留陈旧分包
    for old in dest.glob("*.wxapkg"):
        try:
            old.unlink()
        except OSError:
            pass

    log(f"包体归档目录：{dest}")

    out_pkgs: list[Path] = []
    main_pkg: Optional[Path] = None

    for src in pkgs:
        is_main = src.name == "__APP__.wxapkg" or not _looks_like_subpackage(src.name)
        target_name = f"{appid}.wxapkg" if (is_main and appid) else src.name
        target = dest / target_name

        if is_encrypted(src):
            log(f"检测到加密包：{src.name}，开始解密 ...")
            tmp = decrypt_tmp_dir()
            res = run_killwxapkg(
                [f"-id={appid or ''}", f'-in={src}', f"-out={tmp}", "-save"],
                log=log,
            )
            decrypted = _find_decrypted(tmp, appid)
            if decrypted is None:
                # 解密失败：退一步直接复制，反编译阶段仍可尝试
                log(f"解密输出未找到，直接复制原始包：{src.name}")
                shutil.copy2(src, target)
            else:
                shutil.move(str(decrypted), str(target))
            _rmtree(tmp)
        else:
            log(f"包已解密，直接复制：{src.name}")
            shutil.copy2(src, target)

        out_pkgs.append(target)
        if is_main and main_pkg is None:
            main_pkg = target

    if main_pkg is None:
        main_pkg = out_pkgs[0]

    subs = [p for p in out_pkgs if _looks_like_subpackage(p.name)]
    log("解包成功！")
    log(f"主包：{main_pkg.name}")
    if subs:
        log("检测到分包：" + "、".join(p.name for p in subs))
        log("反编译时会自动按目录模式把主包 + 分包一起还原。")
    else:
        log("此小程序无分包")

    return UnpackResult(appid or "", main_pkg, out_pkgs, subs)


def _find_decrypted(root: Path, appid: Optional[str]) -> Optional[Path]:
    cands = [p for p in root.rglob("*.wxapkg") if not is_encrypted(p)]
    if not cands:
        return None
    if appid:
        for p in cands:
            if appid.lower() in p.name.lower():
                return p
    return max(cands, key=lambda p: p.stat().st_size)


def _rmtree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


# ---------------------------------------------------------------- 反编译

def decompile(pkg_file: Path, appid: str, use_dir_mode: bool,
              log: Logger = _noop, sensitive: bool = True) -> tuple[RunResult, Path]:
    """新版反编译（KillWxapkg）。

    `use_dir_mode=True`（该小程序有分包）时，`-in` 必须指向**包目录**：
    分包与主包放在同一个 wxapkg 里各自独立，只有目录模式才能一起还原，
    并且分包内容才会落到正确的根目录下。

    注意 `-in` 用的是该 AppID 专属的 `_packages/<AppID>/`，不是整个 wxpack，
    否则会把其他小程序的包一起反编译进来。

    `sensitive=True` 会额外做敏感信息扫描（`-sensitive`），产出物由
    `harvest_sensitive()` 从内核的工作目录搬到源码目录下。

    返回 (运行结果, 源码目录)。
    """
    from .paths import packages_dir, wxpack_dir

    src_dir = wxpack_dir() / appid
    src_dir.mkdir(parents=True, exist_ok=True)

    if use_dir_mode:
        pkg_dir = pkg_file.parent if pkg_file.parent.name == appid \
            else packages_dir(appid)
        target = pkg_dir
    else:
        target = pkg_file

    args = [
        f"-id={appid}",
        f"-in={target}",
        f"-out={src_dir}",
        "-restore",
        "-pretty",
    ]
    if sensitive:
        args.append("-sensitive")
        # 先清掉上一轮可能残留的报告，避免把陈旧的命中误判成本次结果
        stale = tools_dir() / "sensitive_data.json"
        try:
            if stale.is_file():
                stale.unlink()
        except OSError:
            pass

    res = run_killwxapkg(args, log=log)
    if sensitive and res.ok:
        harvest_sensitive(src_dir, log)
    return res, src_dir


# ---------------------------------------------------------------- 敏感信息

def harvest_sensitive(src_dir: Path, log: Logger = _noop) -> Optional[Path]:
    """把敏感信息扫描结果收口到源码目录，并生成一份可读汇总。

    KillWxapkg 的 `-sensitive` 把 `sensitive_data.json` 写在**进程的当前工作目录**
    （这里就是 tools 目录），而不是 `-out` 目录；而且每次同名覆盖，
    换一个 AppID 就把上一次的冲掉了。所以每次反编译后都要把它搬过来。

    产出：
      <源码目录>/sensitive_data.json  原始结果，JSON Lines，每行一条
      <源码目录>/敏感信息报告.txt      按规则分组、去重后的可读汇总
    """
    candidates = [
        tools_dir() / "sensitive_data.json",
        Path.cwd() / "sensitive_data.json",
        src_dir / "sensitive_data.json",
    ]
    found = next((p for p in candidates if p.is_file()), None)
    if found is None:
        log("敏感信息扫描：未命中任何规则（内核没有生成 sensitive_data.json）。")
        return None

    dest = src_dir / "sensitive_data.json"
    try:
        if found.resolve() != dest.resolve():
            if dest.exists():
                dest.unlink()
            shutil.move(str(found), str(dest))
    except OSError:
        # 搬不动就原地保留，至少让用户知道在哪
        dest = found
        log("报告搬迁失败，仍在原位置。")

    # 解析 JSON Lines
    grouped: dict[str, list[str]] = {}
    total = 0
    try:
        raw = dest.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        raw = ""
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        total += 1
        try:
            obj = json.loads(line)
            rule = str(obj.get("rule_id", "unknown"))
            content = str(obj.get("content", ""))
        except Exception:
            rule, content = "unknown", line
        bucket = grouped.setdefault(rule, [])
        if content not in bucket:
            bucket.append(content)

    log(f"敏感信息报告：{dest}")
    if total == 0:
        log("报告为空：所有启用的规则都跑过，没有命中。")
        log("（想改规则：编辑 tools\\config\\rule.yaml，把 enabled 改成 true 或补上 pattern）")
        return dest

    log(f"共命中 {total} 条，按规则分布：")
    for rule, items in sorted(grouped.items(), key=lambda kv: -len(kv[1])):
        log(f"  · {rule}: {len(items)} 种")

    # 生成可读汇总
    lines = [
        "敏感信息扫描报告",
        "=" * 60,
        f"AppID    : {src_dir.name}",
        f"源码目录 : {src_dir}",
        f"命中总数 : {total} 条（去重后 {sum(len(v) for v in grouped.values())} 种）",
        "",
    ]
    for rule, items in sorted(grouped.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"[{rule}]  {len(items)} 种")
        for it in items:
            lines.append(f"    {it}")
        lines.append("")
    lines.append("规则来源：tools\\config\\rule.yaml（可自行增删、改 enabled）")
    txt = src_dir / "敏感信息报告.txt"
    try:
        txt.write_text("\n".join(lines), encoding="utf-8")
        log(f"可读汇总：{txt}")
    except OSError:
        pass
    return dest


def subpackage_present(main_pkg: Path) -> bool:
    """该 AppID 的包目录里是否有分包。"""
    return any(_looks_like_subpackage(p.name)
               for p in main_pkg.parent.glob("*.wxapkg"))


def subpackage_present(main_pkg: Path) -> bool:
    return any(_looks_like_subpackage(p.name)
               for p in main_pkg.parent.glob("*.wxapkg"))
