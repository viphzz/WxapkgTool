# -*- coding: utf-8 -*-
"""拉取 KillWxapkg 官方 release 到 app/tools/。

仓库里不带这个 37MB 的二进制，克隆后跑一次本脚本即可：

    python fetch_engine.py

GitHub 直连不通时自动回落到 gh-proxy 镜像。下载后校验 MD5。
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

VERSION = "2.4.1"
ASSET = f"KillWxapkg_{VERSION}_windows_amd64.exe"
MD5 = "5593a83f60f742bfb27c4fef756dfae7"

GH = f"https://github.com/Ackites/KillWxapkg/releases/download/v{VERSION}/{ASSET}"
MIRRORS = [
    GH,
    f"https://gh-proxy.com/{GH}",
    f"https://ghproxy.net/{GH}",
]

DEST = Path(__file__).resolve().parent / "app" / "tools" / "KillWxapkg.exe"


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def already_ok() -> bool:
    return DEST.exists() and md5_of(DEST) == MD5


def ensure() -> bool:
    """确保内核存在且校验通过。返回是否可用。"""
    if already_ok():
        print(f"内核已就绪：{DEST}")
        return True

    DEST.parent.mkdir(parents=True, exist_ok=True)
    for url in MIRRORS:
        print(f"尝试下载：{url}")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "WxapkgTool"})
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = resp.read()
        except Exception as exc:  # noqa: BLE001
            print(f"  失败：{exc}")
            continue

        if len(data) < 1_000_000:
            print(f"  内容异常（{len(data)} 字节），跳过")
            continue

        DEST.write_bytes(data)
        got = md5_of(DEST)
        if got == MD5:
            print(f"OK  MD5 = {got}")
            return True
        print(f"  MD5 不匹配：期望 {MD5}，实际 {got}")

    print("\n下载失败。可手动下载后放到：", DEST)
    print(f"  地址：{GH}")
    print(f"  要求 MD5 = {MD5}")
    return False


if __name__ == "__main__":
    sys.exit(0 if ensure() else 1)
