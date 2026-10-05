# -*- coding: utf-8 -*-
"""「转成 uni-app」：把已还原的小程序工程转换为 uni-app(HBuilderX) 项目骨架。

覆盖常见写法：
  页面     pages/x/x.{wxml,wxss,js,json} -> pages/x/x.vue
  组件     components/y/y.*             -> components/y/y.vue
  配置     app.json                     -> pages.json + App.vue + main.js
  资源     图片/字体等                    -> static/

模板转换：wx:if/elif/else、wx:for(+item/index/key)、bind*/catch* 事件、
        属性插值 {{}} -> :attr、block -> template、组件引用注册。
脚本转换：Page/Component -> export default、properties -> props、
        methods 提升为顶层、wx.* -> uni.*。

说明：这是尽力而为的静态转换，非 100% 还原；复杂模板、wxs、原生插件需人工调整。
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Callable, Iterable

Logger = Callable[[str], None]

# 小程序基础组件 -> uni-app / HTML 标签
TAG_MAP = {
    "block": "template",
    "wxs": "template",
}

EVENT_MAP = {
    "tap": "tap", "longtap": "longpress", "longpress": "longpress",
    "touchstart": "touchstart", "touchmove": "touchmove",
    "touchend": "touchend", "touchcancel": "touchcancel",
    "input": "input", "change": "change", "confirm": "confirm",
    "submit": "submit", "reset": "reset", "blur": "blur",
    "focus": "focus", "load": "load", "error": "error",
    "scroll": "scroll", "scrolltoupper": "scrolltoupper",
    "scrolltolower": "scrolltolower", "getuserinfo": "getuserinfo",
    "getphonenumber": "getphonenumber", "opensetting": "opensetting",
    "columnchange": "columnchange", "changing": "changing",
}

# 形如  <tag attr="v" attr2>  或  </tag>
TAG_RE = re.compile(
    r"<\s*(/?)\s*([a-zA-Z][\w\-]*)((?:\s+[^<>]*?)?)(/?)\s*>", re.S)
ATTR_RE = re.compile(r'([\w:.\-@]+)(?:\s*=\s*"([^"]*)")?', re.S)
INTERP_ONLY_RE = re.compile(r"^\{\{\s*(.*?)\s*\}\}$", re.S)


def _log(log: Logger, msg: str) -> None:
    log(msg)


# ---------------------------------------------------------------- 属性输出

def _attr(name: str, value: str | None) -> str:
    """输出一个属性；值中含双引号时改用单引号包裹，避免嵌套冲突。"""
    if value is None:
        return name
    if '"' in value:
        return f"{name}='{value}'"
    return f'{name}="{value}"'


def _interp(value: str) -> str | None:
    m = INTERP_ONLY_RE.match(value)
    return m.group(1) if m else None


# ---------------------------------------------------------------- wxml -> vue

def _conv_attrs(raw: str, attrs: dict[str, str | None]) -> list[str]:
    out: list[str] = []
    handled = set()
    keys_lower = {k.lower(): k for k in attrs}

    def has(*names: str) -> str | None:
        for n in names:
            if n in keys_lower:
                return keys_lower[n]
        return None

    # ---- wx:for 组合成 v-for="(item, index) in expr"
    k_for = has("wx:for")
    k_item = has("wx:for-item")
    k_index = has("wx:for-index")
    k_key = has("wx:key")
    if k_for is not None:
        expr = _interp(attrs[k_for] or "") or (attrs[k_for] or "")
        item = (_interp(attrs[k_item] or "") or attrs[k_item] or "item") if k_item else "item"
        index = (_interp(attrs[k_index] or "") or attrs[k_index] or "index") if k_index else "index"
        out.append(_attr("v-for", f"({item}, {index}) in {expr}"))
        handled.update(x for x in (k_for, k_item, k_index) if x)

    if k_key is not None:
        raw_key = _interp(attrs[k_key] or "") or (attrs[k_key] or "").strip()
        if raw_key and raw_key != "*this":
            out.append(_attr(":key", raw_key))
        handled.add(k_key)

    # ---- 条件渲染
    for name, direct in (("wx:if", "v-if"), ("wx:elif", "v-else-if")):
        k = has(name)
        if k is not None:
            expr = _interp(attrs[k] or "") or (attrs[k] or "")
            out.append(_attr(direct, expr))
            handled.add(k)
    k_else = has("wx:else")
    if k_else is not None:
        out.append("v-else")
        handled.add(k_else)

    # ---- 其余属性
    for name, value in attrs.items():
        if name in handled:
            continue
        low = name.lower()

        # 事件：bindtap / catchtap / bind:tap / capture-bind:tap
        ev = re.match(r"^(capture-)?(bind|catch):?([\w\-]+)$", name)
        if ev:
            capture, kind, evname = ev.groups()
            uni_ev = EVENT_MAP.get(evname.lower(), evname.lower())
            mods = ""
            if capture:
                mods += ".capture"
            if kind == "catch":
                mods += ".stop"
            out.append(_attr(f"@{uni_ev}{mods}", value or ""))
            continue

        if low in ("wx:for-items", "wx:key"):
            continue

        if value is None:
            out.append(name)
            continue

        if name.startswith("data-"):
            expr = _interp(value)
            out.append(_attr(f":{name}", expr if expr is not None else value))
            continue

        expr = _interp(value)
        if expr is not None:
            out.append(_attr(f":{name}", expr))
            continue

        if "{{" in value:
            parts = re.split(r"(\{\{[^}]*\}\})", value)
            pieces = []
            for seg in parts:
                m2 = INTERP_ONLY_RE.match(seg)
                if m2:
                    pieces.append(f"({m2.group(1)})")
                elif seg:
                    pieces.append(json.dumps(seg, ensure_ascii=False))
            if pieces:
                out.append(_attr(f":{name}", " + ".join(pieces)))
                continue

        out.append(_attr(name, value))

    return out


def wxml_to_template(src: str, in_component: bool = False) -> str:
    def repl(match: re.Match) -> str:
        closing, raw_tag, attrs_raw, self_close = match.groups()
        tag = TAG_MAP.get(raw_tag, raw_tag)

        if raw_tag == "wxs" or raw_tag == "import" or raw_tag == "include":
            return ""  # 小程序内部机制，uni-app 无对应，丢弃

        if closing:
            return f"</{tag}>"

        attrs: dict[str, str | None] = {}
        for am in ATTR_RE.finditer(attrs_raw or ""):
            attrs[am.group(1)] = am.group(2)

        # <template is="x" data="{{...}}"/> 动态模板，改写为 :is
        if raw_tag == "template" and "is" in attrs:
            parts = []
            for k, v in attrs.items():
                expr = _interp(v or "")
                if k == "is":
                    parts.append(_attr(":is", expr or v or ""))
                elif k == "data":
                    parts.append(_attr("v-bind", expr or "{}"))
                else:
                    parts.append(_attr(k, v))
            return f"<component {' '.join(parts)}{'/' if self_close else ''}>"

        parts = _conv_attrs(attrs_raw or "", attrs)
        attr_str = (" " + " ".join(parts)) if parts else ""
        return f"<{tag}{attr_str}{'/' if self_close else ''}>"

    return TAG_RE.sub(repl, src)


# ---------------------------------------------------------------- js 解析

IJS_KEY_RE = re.compile(r"[A-Za-z_$][\w$]*")


def _skip_js_value(s: str, i: int) -> int:
    """从 i 开始跳过一段 JS 值，返回结束位置。"""
    n = len(s)
    stack: list[str] = []
    pairs = {"{": "}", "[": "]", "(": ")"}
    while i < n:
        c = s[i]
        if c in "\"'`":
            quote = c
            i += 1
            while i < n:
                if s[i] == "\\":
                    i += 2
                    continue
                if s[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        if c in "{[(":
            stack.append(pairs[c])
            i += 1
            continue
        if c in "}])":
            if stack and stack[-1] == c:
                stack.pop()
                i += 1
                if not stack:
                    return i
                continue
            if not stack:
                return i
            stack.pop()
            i += 1
            continue
        if c == "," and not stack:
            return i
        i += 1
    return i


def _split_entries(body: str) -> list[tuple[str, str | None]]:
    """把对象字面量的顶层键值对拆开。返回 [(key, raw_value|None)]。"""
    out: list[tuple[str, str | None]] = []
    i, n = 0, len(body)
    while i < n:
        while i < n and body[i] in " \t\r\n,":
            i += 1
        if i >= n:
            break

        if body[i] in "\"'":
            q = body[i]
            j = i + 1
            while j < n and body[j] != q:
                j += 1
            key = body[i + 1:j]
            i = j + 1
        else:
            m = IJS_KEY_RE.match(body, i)
            if not m:
                i += 1
                continue
            key = m.group(0)
            i = m.end()

        while i < n and body[i] in " \t\r\n":
            i += 1

        if i < n and body[i] == ":":
            i += 1
            while i < n and body[i] in " \t\r\n":
                i += 1
            vstart = i
            i = _skip_js_value(body, i)
            out.append((key, body[vstart:i].strip()))
        elif i < n and body[i] == "(":
            # 简写方法 onLoad() {...} —— 原样保留 "(...){...}"，重建时识别
            pstart = i
            params_end = _skip_js_value(body, i)
            i = params_end
            while i < n and body[i] in " \t\r\n":
                i += 1
            if i < n and body[i] == "{":
                end = _skip_js_value(body, i)
                out.append((key, body[pstart:end].strip()))
                i = end
            else:
                out.append((key, None))
        else:
            out.append((key, None))
    return out


def _find_object_body(text: str, ctor: str) -> tuple[str | None, str]:
    """取出 Ctor({ ... }) 中的对象体。返回 (body, 前置代码)。"""
    m = re.search(rf"\b{ctor}\s*\(\s*\{{", text)
    if not m:
        return None, text
    # text 中匹配位置是 '{'
    m2 = re.search(r"\{", text[m.start():])
    open_idx = m.start() + m2.start()
    end = _skip_js_value(text, open_idx)
    # end 指向与 { 配对的 } 之后
    body = text[open_idx + 1:end - 1]
    return body, text[:m.start()].strip()


def _entries_to_src(entries: Iterable[tuple[str, str | None]]) -> str:
    parts = []
    for k, v in entries:
        if v is None:
            continue
        name = k if IJS_KEY_RE.fullmatch(k) else f'"{k}"'
        if v.startswith("("):
            # 简写方法：onLoad() { ... }
            parts.append(f"  {name}{v}")
        else:
            parts.append(f"  {name}: {v}")
    return ",\n".join(parts)


def js_to_script(src: str, is_component: bool) -> str:
    text = src.strip()
    if text.startswith("\ufeff"):
        text = text[1:]

    body, prefix = _find_object_body(text, "Component" if is_component else "Page")
    if body is None:
        # 已是模块化写法，仅做 API 替换
        return re.sub(r"\bwx\.", "uni.", text)

    entries = _split_entries(body)
    if not entries:
        return re.sub(r"\bwx\.", "uni.", text)

    if is_component:
        drop = {"externalClasses", "options", "behaviors", "relations",
                "definitionFilter", "generics", "observers"}
        lowered = {k: k for k in drop}
        new_entries: list[tuple[str, str | None]] = []
        for k, v in entries:
            if k in lowered:
                continue
            if k == "properties" and v:
                props_inner = v.strip()
                if props_inner.startswith("{"):
                    props_inner = props_inner[1:].rsplit("}", 1)[0]
                props_inner = re.sub(r"\bvalue\s*:", "default:", props_inner)
                props_inner = re.sub(r",?\s*observer\s*:\s*\([^)]*\)\s*=>\s*\{",
                                     ", _observer: () => {", props_inner)
                new_entries.append(("props", "{ " + props_inner.strip().rstrip(",") + " }"))
                continue
            if k == "methods" and v and v.strip().startswith("{"):
                inner = v.strip()[1:].rsplit("}", 1)[0]
                new_entries.extend(_split_entries(inner))
                continue
            new_entries.append((k, v))
        entries = new_entries

    script = _entries_to_src(entries)
    script = re.sub(r"\bwx\.", "uni.", script)
    head = prefix + ("\n\n" if prefix else "")
    return f"{head}export default {{\n{script}\n}};\n"


# ---------------------------------------------------------------- 单文件组件

def _component_registry(src_root: Path, rel_file: Path) -> list[str]:
    cfg_path = rel_file.with_suffix(".json")
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8", errors="ignore") or "{}")
    except Exception:
        return []
    out: list[str] = []
    for name, path in (cfg.get("usingComponents") or {}).items():
        p = str(path)
        if p.startswith("plugin://") or p.startswith("weui-miniprogram"):
            continue
        base = p.lstrip("/")
        if base.startswith("."):
            target = (rel_file.parent / base).resolve()
            try:
                base = target.relative_to(src_root.resolve()).as_posix()
            except ValueError:
                continue
        out.append(f'    "{name}": "/{base}.vue",')
    return out


def build_vue(src_root: Path, rel: str, is_component: bool) -> str:
    base = src_root / rel
    wxml = (base.with_suffix(".wxml")).read_text(encoding="utf-8", errors="ignore")
    wxss = (base.with_suffix(".wxss")).read_text(encoding="utf-8", errors="ignore")
    js = (base.with_suffix(".js")).read_text(encoding="utf-8", errors="ignore")

    template = wxml_to_template(wxml, is_component)
    script = js_to_script(js, is_component)

    comps = _component_registry(src_root, base)
    if comps:
        script = script.replace(
            "export default {",
            "export default {\n  components: {\n" + "\n".join(comps) + "\n  },",
            1,
        )

    return (
        "<template>\n"
        f"  <view>{template.strip()}</view>\n"
        "</template>\n\n"
        "<script>\n"
        f"{script}"
        "</script>\n\n"
        "<style>\n"
        f"{wxss}\n"
        "</style>\n"
    )


# ---------------------------------------------------------------- 工程转换

SKIP_DIRS = {"pages", "components", "@babel", "miniprogram_npm",
             "subpackages", "runtime", "common", "node_modules"}
CODE_EXT = {".wxml", ".wxss", ".js", ".json", ".wxs"}


def _copy_static(src_dir: Path, static_out: Path) -> int:
    moved = 0
    for entry in os.scandir(src_dir):
        name = entry.name
        if name in SKIP_DIRS or name.startswith("."):
            continue
        if entry.is_file():
            if Path(name).suffix.lower() in CODE_EXT:
                continue
            try:
                shutil.copy2(entry.path, static_out / name)
                moved += 1
            except OSError:
                pass
            continue
        # 目录：递归但跳过代码目录
        for root, dirs, files in os.walk(entry.path):
            dirs[:] = [d for d in dirs
                       if d not in SKIP_DIRS and not d.startswith(".")]
            rel = Path(root).relative_to(src_dir)
            for f in files:
                if Path(f).suffix.lower() in CODE_EXT:
                    continue
                target = static_out / rel / f
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(Path(root) / f, target)
                    moved += 1
                except OSError:
                    pass
    return moved


def _collect_pages(app_json: dict) -> tuple[list[str], list[dict]]:
    pages = [str(p) for p in (app_json.get("pages") or [])]
    subs = []
    for sub in (app_json.get("subPackages") or app_json.get("subpackages") or []):
        root = str(sub.get("root", "")).strip("/")
        plist = [f"{root}/{p}".strip("/") for p in (sub.get("pages") or [])]
        subs.append({"root": root, "pages": plist})
    return pages, subs


def _convert_unit(src_dir: Path, rel: str, out_dir: Path, is_component: bool) -> bool:
    base = src_dir / rel
    if not base.with_suffix(".wxml").exists() and not base.with_suffix(".js").exists():
        return False
    out = out_dir / (rel + ".vue")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_vue(src_dir, rel, is_component), encoding="utf-8")
    return True


def convert(src_dir: Path, out_dir: Path, log: Logger) -> dict:
    """把 src_dir（小程序工程）转换成 out_dir（uni-app 工程）。"""
    app_json_path = src_dir / "app.json"
    if not app_json_path.exists():
        raise FileNotFoundError(
            "源目录缺少 app.json，请先执行「新版反编译」并「修复源码」。")

    try:
        app_json = json.loads(
            app_json_path.read_text(encoding="utf-8", errors="ignore") or "{}")
    except Exception as exc:
        raise ValueError(f"app.json 解析失败：{exc}")

    out_dir.mkdir(parents=True, exist_ok=True)
    pages, subs = _collect_pages(app_json)
    _log(log, f"开始转换为 uni-app：主包 {len(pages)} 页，分包 {len(subs)} 个")

    page_entries: list[dict] = []
    ok = 0
    for p in pages:
        if _convert_unit(src_dir, p, out_dir, False):
            ok += 1
        cfg = (src_dir / p).with_suffix(".json")
        style: dict = {}
        if cfg.exists():
            try:
                style = json.loads(cfg.read_text(encoding="utf-8", errors="ignore") or "{}")
                if not isinstance(style, dict):
                    style = {}
                style.pop("usingComponents", None)
            except Exception:
                style = {}
        entry: dict = {"path": p}
        if style:
            entry["style"] = style
        page_entries.append(entry)

    sub_entries = []
    for sub in subs:
        conv_pages = []
        for p in sub["pages"]:
            if _convert_unit(src_dir, p, out_dir, False):
                ok += 1
            conv_pages.append({"path": p})
        sub_entries.append({"root": sub["root"], "pages": conv_pages})

    comp_count = 0
    comp_root = src_dir / "components"
    if comp_root.exists():
        for wxml in sorted(comp_root.rglob("*.wxml")):
            rel = wxml.relative_to(src_dir).with_suffix("").as_posix()
            if _convert_unit(src_dir, rel, out_dir, True):
                comp_count += 1

    static_out = out_dir / "static"
    static_out.mkdir(parents=True, exist_ok=True)
    moved = _copy_static(src_dir, static_out)

    pages_json: dict = {"pages": page_entries}
    if sub_entries:
        pages_json["subPackages"] = sub_entries
    win = app_json.get("window") or {}
    if win:
        style = {k: v for k, v in win.items() if k != "navigationStyle"}
        if style:
            pages_json["globalStyle"] = style
    if app_json.get("tabBar"):
        pages_json["tabBar"] = app_json["tabBar"]
    (out_dir / "pages.json").write_text(
        json.dumps(pages_json, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = {
        "name": src_dir.name,
        "appid": "",
        "description": "由 wxapkg 反编译工程自动转换生成",
        "versionName": "1.0.0",
        "versionCode": "100",
        "transformPx": False,
        "app-plus": {"usingComponents": True, "nvueStyleCompiler": "uni-app",
                     "compilerVersion": 3,
                     "splashscreen": {"alwaysShowBeforeRender": True,
                                      "waiting": True, "autoclose": True}},
        "quickapp": {},
        "mp-weixin": {"appid": "", "setting": {"urlCheck": False},
                      "usingComponents": True},
        "vueVersion": "2",
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    app_js = (src_dir / "app.js").read_text(encoding="utf-8", errors="ignore") \
        if (src_dir / "app.js").exists() else ""
    app_wxss = (src_dir / "app.wxss").read_text(encoding="utf-8", errors="ignore") \
        if (src_dir / "app.wxss").exists() else ""

    body, _ = _find_object_body(app_js, "App")
    on_launch = ""
    if body:
        for k, v in _split_entries(body):
            if k == "onLaunch" and v is not None:
                v = v.strip()
                if v.startswith("("):
                    idx = v.find("{")
                    v = v[idx:] if idx >= 0 else ""
                on_launch = re.sub(r"\bwx\.", "uni.", v)
                break
    on_launch = on_launch.strip()
    if on_launch:
        on_launch = "\n".join("    " + line for line in on_launch.splitlines())

    (out_dir / "App.vue").write_text(
        "<script>\n"
        "export default {\n"
        "  onLaunch() {\n" + (on_launch + "\n" if on_launch else "") +
        "  }\n"
        "};\n"
        "</script>\n\n"
        "<style>\n"
        f"{app_wxss}\n"
        "</style>\n",
        encoding="utf-8")

    (out_dir / "main.js").write_text(
        "import Vue from 'vue';\n"
        "import App from './App.vue';\n\n"
        "Vue.config.productionTip = false;\n"
        "App.mpType = 'app';\n\n"
        "const app = new Vue({ ...App });\n"
        "app.$mount();\n",
        encoding="utf-8")

    (out_dir / "uni.scss").write_text(
        "/* uni-app 全局 SCSS 变量（可留空） */\n", encoding="utf-8")

    (out_dir / "README.md").write_text(
        "# uni-app 工程（由 WxapkgTool 自动转换）\n\n"
        "用 HBuilderX 直接「打开目录」即可运行。\n\n"
        "## 转换范围\n"
        "- `pages/**/*.vue`：模板 + 样式 + 脚本\n"
        "- `components/**/*.vue`：自定义组件，JSON 里的 `usingComponents` 已注册到 `components` 选项\n"
        "- `pages.json` / `manifest.json` / `App.vue` / `main.js` 骨架\n"
        "- 图片、字体等静态资源复制到 `static/`\n\n"
        "## 需要人工处理的地方\n"
        "- 反编译产物的**事件处理器名可能是混淆后的地址**（如 `0x7654a0`），需从 JS 中找回真实函数\n"
        "- `wxs`、动态 `<template is>`、原生插件无对应实现，已丢弃或改写\n"
        "- `style` 中的 `undefined`、`class` 中的 `<nil>` 等还原噪声需手工清理\n"
        "- 组件间 `triggerEvent` / `selectComponent` 通信未做改写\n",
        encoding="utf-8")

    stats = {"pages": ok, "components": comp_count, "static": moved}
    _log(log, f"转换完成：页面 {ok} 个、组件 {comp_count} 个、静态资源 {moved} 个")
    _log(log, f"uni-app 工程目录：{out_dir}")
    return stats
