# -*- coding: utf-8 -*-
"""生成界面用的小图标与下拉箭头（白色 16x16 PNG，2x 超采样抗锯齿）。

运行： <venv-python> make_icons.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent / "app" / "resources"
OUT.mkdir(parents=True, exist_ok=True)

S = 128           # 超采样画布
FINAL = 16
WHITE = (255, 255, 255, 255)


def _canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def _save(im: Image.Image, name: str) -> None:
    im = im.resize((FINAL, FINAL), Image.LANCZOS)
    im.save(OUT / name)
    print("icon ->", name, im.size)


def folder(opened: bool) -> Image.Image:
    im, d = _canvas()
    w = 9
    d.line([(14, 40), (44, 40), (56, 30), (86, 30), (92, 58)],
           fill=WHITE, width=w, joint="curve")
    if opened:
        d.polygon([(10, 46), (118, 46), (104, 100), (2, 100)], fill=WHITE)
    else:
        d.rounded_rectangle([10, 40, 118, 100], radius=8, fill=WHITE)
    return im


def folder_open() -> Image.Image:
    im, d = _canvas()
    d.line([(14, 44), (50, 44), (62, 32), (88, 32), (92, 60)],
           fill=WHITE, width=9, joint="curve")
    d.polygon([(12, 50), (116, 50), (100, 102), (0, 102)], fill=WHITE)
    return im


def refresh() -> Image.Image:
    im, d = _canvas()
    d.arc([16, 16, 112, 112], start=40, end=330, fill=WHITE, width=13)
    d.polygon([(96, 8), (126, 44), (84, 46)], fill=WHITE)
    return im


def lightning(filled: bool) -> Image.Image:
    im, d = _canvas()
    pts = [(74, 6), (26, 72), (58, 72), (48, 122), (102, 52), (66, 52)]
    if filled:
        d.polygon(pts, fill=WHITE)
    else:
        d.polygon(pts, outline=WHITE, width=9, fill=None)
    return im


def magnifier() -> Image.Image:
    im, d = _canvas()
    d.ellipse([12, 12, 86, 86], outline=WHITE, width=13)
    d.line([(80, 80), (116, 116)], fill=WHITE, width=15)
    return im


def trash() -> Image.Image:
    im, d = _canvas()
    d.rounded_rectangle([16, 24, 112, 34], radius=5, fill=WHITE)
    d.rounded_rectangle([48, 10, 80, 24], radius=5, fill=WHITE)
    d.polygon([(26, 40), (102, 40), (94, 118), (34, 118)], fill=WHITE)
    return im


def letter_h() -> Image.Image:
    im, d = _canvas()
    try:
        f = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 118)
    except OSError:
        f = ImageFont.load_default()
    bb = d.textbbox((0, 0), "H", font=f)
    d.text(((S - bb[2] - bb[0]) / 2, (S - bb[3] - bb[1]) / 2 - 6),
           "H", font=f, fill=WHITE)
    return im


def arrow_down() -> None:
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.polygon([(28, 48), (100, 48), (64, 88)], fill=(140, 147, 158, 255))
    im = im.resize((12, 12), Image.LANCZOS)
    im.save(OUT / "arrow_down.png")
    print("icon -> arrow_down.png", im.size)


def main() -> None:
    _save(folder(True), "ic_choose.png")
    _save(refresh(), "ic_refresh.png")
    _save(lightning(True), "ic_new.png")
    _save(folder_open(), "ic_open.png")
    _save(magnifier(), "ic_fix.png")
    _save(trash(), "ic_clear.png")
    _save(letter_h(), "ic_uni.png")
    arrow_down()


if __name__ == "__main__":
    main()
