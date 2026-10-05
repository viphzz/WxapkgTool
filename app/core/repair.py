# -*- coding: utf-8 -*-
"""「修复源码」：把 KillWxapkg 的还原产物整理成可直接导入微信开发者工具的工程。

做四件事（均可单独开关）：
1. 删除编译期运行时分片 chunk_N.appservice.js / chunk_N.webview.js
2. 补全 project.config.json 的 appid 等字段
3. 按 app.json 补全页面/组件的「四件套」缺失文件
4. 递归扫描 usingComponents，给解析不到的目标补占位组件
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable, Iterable

Logger = Callable[[str], None]

DEFAULT_LIB_VERSION = "3.5.7"

CHUNK_RE = re.compile(r"^chunk_\d+\.(appservice|webview)\.js$", re.I)

PLACEHOLDER_WXML = "<!-- placeholder: 该文件在原包中不存在，由修复工具补全 -->\n<view></view>\n"
PLACEHOLDER_WXSS = "/* placeholder */\n"
PLACEHOLDER_JSON = "{}\n"


def _page_js(is_component: bool) -> str:
    if is_component:
        return "Component({\n  properties: {},\n  data: {},\n  methods: {}\n});\n"
    return "Page({\n  data: {},\n  onLoad() {}\n});\n"


def _log(log: Logger, msg: str) -> None:
    log(msg)


# ---------------------------------------------------------------- 1. 清理分片

def clean_chunks(root: Path, log: Logger) -> int:
    removed = 0
    for f in root.iterdir():
        if f.is_file() and CHUNK_RE.match(f.name):
            try:
                f.unlink()
                removed += 1
            except OSError:
                pass
    if removed:
        _log(log, f"已删除 {removed} 个编译期运行时分片（chunk_*.js）")
    return removed


# ---------------------------------------------------------------- 2. 工程配置

def fix_project_config(root: Path, appid: str, lib_version: str, log: Logger) -> None:
    path = root / "project.config.json"
    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="ignore") or "{}")
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}

    data.setdefault("compileType", "miniprogram")
    data.setdefault("miniprogramRoot", "")
    data["appid"] = data.get("appid") or ("touristappid" if not appid else appid)
    if data["appid"] == "touristappid" and appid:
        data["appid"] = appid
    data.setdefault("projectname", appid or "wxapkg")
    data.setdefault("libVersion", lib_version)
    data.setdefault("setting", {
        "urlCheck": False,
        "es6": False,
        "enhance": False,
        "postcss": False,
        "minified": False,
    })

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    _log(log, f"已写入 project.config.json（appid={data['appid']}，libVersion={data['libVersion']}）")


# ---------------------------------------------------------------- 3. 页面四件套

def _iter_pages(app_json: dict) -> list[tuple[str, bool]]:
    """返回 [(页面路径, 是否分包页面)]。"""
    out: list[tuple[str, bool]] = []
    for p in app_json.get("pages", []) or []:
        out.append((str(p), False))
    for sub in app_json.get("subPackages", []) or app_json.get("subpackages", []) or []:
        root = str(sub.get("root", "")).strip("/")
        for p in sub.get("pages", []) or []:
            out.append((f"{root}/{p}".strip("/"), True))
    return out


def _iter_components(app_json: dict) -> list[str]:
    comps: list[str] = []
    for c in app_json.get("usingComponents", {}).values() if isinstance(
            app_json.get("usingComponents"), dict) else []:
        comps.append(str(c))
    return comps


def fix_pages(root: Path, log: Logger) -> int:
    app_json_path = root / "app.json"
    if not app_json_path.exists():
        _log(log, "未找到 app.json，跳过页面补全")
        return 0
    try:
        app_json = json.loads(app_json_path.read_text(encoding="utf-8", errors="ignore"))
    except Exception as exc:
        _log(log, f"app.json 解析失败：{exc}")
        return 0

    created = 0
    for page, _is_sub in _iter_pages(app_json):
        base = root / page
        base.parent.mkdir(parents=True, exist_ok=True)
        for ext, content in (
            (".wxml", PLACEHOLDER_WXML),
            (".js", _page_js(False)),
            (".json", PLACEHOLDER_JSON),
            (".wxss", PLACEHOLDER_WXSS),
        ):
            f = base.with_suffix(ext)
            if not f.exists():
                f.write_text(content, encoding="utf-8")
                created += 1
    if created:
        _log(log, f"已补全 {created} 个缺失的页面文件")
    else:
        _log(log, "页面文件完整，无需补全")
    return created


# ---------------------------------------------------------------- 4. 组件占位

USING_RE = re.compile(r'"usingComponents"\s*:\s*\{', re.S)


def _iter_json_files(root: Path) -> Iterable[Path]:
    for f in root.rglob("*.json"):
        if "node_modules" in f.parts:
            continue
        if f.name in ("project.config.json", "project.private.config.json",
                      "sitemap.json", "package.json"):
            continue
        yield f


def _resolve_component(root: Path, from_file: Path, ref: str) -> Path | None:
    r = ref.strip()
    if not r or r.startswith("plugin://") or r.startswith("weui-miniprogram"):
        return None
    if r.startswith("/"):
        base = root / r.lstrip("/")
    elif r.startswith("."):
        base = (from_file.parent / r).resolve()
    else:
        base = root / r
    return base


def fix_components(root: Path, log: Logger) -> int:
    created = 0
    for jf in list(_iter_json_files(root)):
        try:
            data = json.loads(jf.read_text(encoding="utf-8", errors="ignore") or "{}")
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        uc = data.get("usingComponents")
        if not isinstance(uc, dict):
            continue
        for ref in uc.values():
            base = _resolve_component(root, jf, str(ref))
            if base is None:
                continue
            try:
                base.relative_to(root)
            except ValueError:
                continue  # 指向工程外，忽略
            if base.with_suffix(".json").exists() or base.with_suffix(".js").exists():
                continue
            base.parent.mkdir(parents=True, exist_ok=True)
            comp_name = base.name
            base.with_suffix(".json").write_text(PLACEHOLDER_JSON, encoding="utf-8")
            base.with_suffix(".wxml").write_text(
                f'<!-- placeholder: 未在包中找到的组件 {comp_name} -->\n<view></view>\n',
                encoding="utf-8")
            base.with_suffix(".js").write_text(_page_js(True), encoding="utf-8")
            base.with_suffix(".wxss").write_text(PLACEHOLDER_WXSS, encoding="utf-8")
            created += 1
            _log(log, f"补占位组件：{base.relative_to(root).as_posix()}")

    if created:
        _log(log, f"共补全 {created} 个缺失组件")
    else:
        _log(log, "组件引用完整，无需补全")
    return created


# ---------------------------------------------------------------- 入口

def repair(src_dir: Path, appid: str, log: Logger,
           lib_version: str = DEFAULT_LIB_VERSION) -> dict:
    if not src_dir.exists():
        raise FileNotFoundError(f"源码目录不存在：{src_dir}")

    _log(log, f"开始修复源码：{src_dir}")
    stats = {
        "chunks": clean_chunks(src_dir, log),
        "pages": fix_pages(src_dir, log),
        "components": fix_components(src_dir, log),
    }
    fix_project_config(src_dir, appid, lib_version, log)
    _log(log, "修复完成！")
    return stats


def health_check(src_dir: Path) -> tuple[bool, list[str]]:
    """简单体检：app.json 存在、页面四件套齐全。"""
    problems: list[str] = []
    app_json_path = src_dir / "app.json"
    if not app_json_path.exists():
        return False, ["缺少 app.json"]
    try:
        app_json = json.loads(app_json_path.read_text(encoding="utf-8", errors="ignore"))
    except Exception as exc:
        return False, [f"app.json 解析失败：{exc}"]
    for page, _ in _iter_pages(app_json):
        for ext in (".wxml", ".js", ".json", ".wxss"):
            if not (src_dir / page).with_suffix(ext).exists():
                problems.append(f"缺少 {page}{ext}")
    return (not problems), problems[:20]
