# -*- coding: utf-8 -*-
"""生成视频封面：竖版 1080x1920 + 横版 1920x1080"""
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.abspath(__file__))
CY = (125, 246, 255)
WHITE = (240, 250, 253)
DIM = (150, 172, 184)
FONT_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"
FONT_REG = r"C:\Windows\Fonts\msyh.ttc"


def font(p, s):
    return ImageFont.truetype(p, s)


def spaced(d, xy, text, f, fill, tracking=0):
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += d.textlength(ch, font=f) + tracking


def swidth(d, text, f, tracking=0):
    return sum(d.textlength(ch, font=f) + tracking for ch in text) - tracking


def load_car():
    return Image.open(os.path.join(ROOT, "test-car.jpg")).convert("RGB")


def vignette(img, strength=0.75):
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse([-w * 0.25, -h * 0.35, w * 1.25, h * 1.35], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(int(min(w, h) * 0.15)))
    dark = Image.new("RGB", (w, h), (0, 0, 0))
    return Image.composite(img, Image.blend(img, dark, strength), mask)


def brackets(d, box, color, w=6, L=70):
    x0, y0, x1, y1 = box
    for (x, y, dx, dy) in [(x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)]:
        d.line([(x, y), (x + dx * L, y)], fill=color, width=w)
        d.line([(x, y), (x, y + dy * L)], fill=color, width=w)


def glow_text(img, xy, text, f, fill, tracking=0, blur=18, alpha=150):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    spaced(d, xy, text, f, fill + (255,), tracking)
    g = layer.filter(ImageFilter.GaussianBlur(blur))
    g.putalpha(g.getchannel("A").point(lambda v: min(255, int(v * alpha / 255))))
    img.alpha_composite(g)
    img.alpha_composite(layer)


def scan_overlay(img, box, y):
    """在 box 范围内画一条扫描光带"""
    x0, y0, x1, y1 = box
    band_h = 150
    band = Image.new("RGBA", (x1 - x0, band_h), (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    for yy in range(band_h):
        k = 1 - abs(yy - band_h / 2) / (band_h / 2)
        bd.line([(0, yy), (x1 - x0, yy)], fill=CY + (int(70 * k ** 2),))
    band = band.filter(ImageFilter.GaussianBlur(4))
    img.alpha_composite(band, (x0, int(y - band_h / 2)))
    d = ImageDraw.Draw(img)
    d.line([(x0, y), (x1, y)], fill=CY + (255,), width=2)


def make_vertical():
    W, H = 1080, 1920
    canvas = Image.new("RGB", (W, H), (5, 8, 11))

    # 上部：车图
    car = load_car()
    cw, ch = car.size
    target_h = 1180
    target_w = W
    scale = max(target_w / cw, target_h / ch)
    car2 = car.resize((int(cw * scale), int(ch * scale)), Image.LANCZOS)
    left = (car2.width - W) // 2
    top = int((car2.height - target_h) * 0.42)
    car2 = car2.crop((left, top, left + W, top + target_h))
    car2 = vignette(car2, 0.6)
    # 冷色调
    tint = Image.new("RGB", car2.size, (10, 40, 60))
    car2 = Image.blend(car2, tint, 0.18)
    canvas.paste(car2, (0, 0))

    img = canvas.convert("RGBA")

    # 扫描框
    box = (158, 392, 872, 812)
    scan_overlay(img, box, 500)
    d = ImageDraw.Draw(img)
    brackets(d, box, CY + (230,), 5, 72)
    # 准星
    cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
    d.ellipse([cx - 46, cy - 46, cx + 46, cy + 46], outline=CY + (110,), width=3)
    d.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill=(255, 255, 255, 240))

    # 顶部角标
    f_tag = font(FONT_BOLD, 30)
    tw = swidth(d, "OPEN SOURCE", f_tag, 6)
    d.rectangle([56, 64, 56 + tw + 44, 64 + 62], fill=(8, 20, 26, 220), outline=CY + (160,), width=2)
    spaced(d, (78, 78), "OPEN SOURCE", f_tag, CY + (240,), 6)

    # 渐变过渡到下方
    grad = Image.new("RGBA", (W, 420), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for y in range(420):
        a = int(255 * (y / 420) ** 1.5)
        gd.line([(0, y), (W, y)], fill=(5, 8, 11, a))
    img.alpha_composite(grad, (0, 900))

    # 文字
    f_kicker = font(FONT_BOLD, 54)
    f_title = font(FONT_BOLD, 150)
    f_sub = font(FONT_REG, 40)

    spaced(d, (110, 1235), "现 实 版", f_kicker, CY + (235,), 4)
    glow_text(img, (104, 1300), "GTA 扫描", f_title, WHITE, 6, 26, 130)
    d = ImageDraw.Draw(img)
    spaced(d, (112, 1492), "手机对着车，弹出游戏卡片", f_sub, DIM + (240,), 2)

    # 底部信息
    f_small = font(FONT_REG, 30)
    d.line([(110, 1600), (W - 110, 1600)], fill=CY + (70,), width=1)
    spaced(d, (110, 1628), "端侧 AI · 不联网 · 不上传", f_small, (110, 130, 145, 235), 2)
    wm = "AI 生成 · 仅供娱乐"
    ww = swidth(d, wm, f_small, 2)
    spaced(d, ((W - ww) / 2, 1830), wm, f_small, (255, 255, 255, 80), 2)

    return img.convert("RGB")


def make_wide():
    W, H = 1920, 1080
    canvas = Image.new("RGB", (W, H), (5, 8, 11))

    # 右侧车图
    car = load_car()
    cw, ch = car.size
    tw, th = 1080, 1080
    scale = max(tw / cw, th / ch)
    car2 = car.resize((int(cw * scale), int(ch * scale)), Image.LANCZOS)
    left = int((car2.width - tw) * 0.62)
    top = int((car2.height - th) * 0.45)
    car2 = car2.crop((left, top, left + tw, top + th))
    car2 = vignette(car2, 0.55)
    car2 = Image.blend(car2, Image.new("RGB", car2.size, (10, 40, 60)), 0.18)

    # 左侧渐隐到黑
    mask = Image.new("L", (tw, th), 255)
    md = ImageDraw.Draw(mask)
    for x in range(420):
        md.line([(x, 0), (x, th)], fill=int(255 * (x / 420) ** 1.2))
    canvas.paste(car2, (W - tw, 0), mask)

    img = canvas.convert("RGBA")
    d = ImageDraw.Draw(img)

    box = (1180, 300, 1712, 742)
    scan_overlay(img, box, 470)
    brackets(d, box, CY + (220,), 5, 64)
    cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
    d.ellipse([cx - 40, cy - 40, cx + 40, cy + 40], outline=CY + (110,), width=3)
    d.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill=(255, 255, 255, 240))

    f_kicker = font(FONT_BOLD, 44)
    f_title = font(FONT_BOLD, 132)
    f_sub = font(FONT_REG, 38)
    f_tag = font(FONT_BOLD, 26)
    f_small = font(FONT_REG, 28)

    tw2 = swidth(d, "OPEN SOURCE", f_tag, 5)
    d.rectangle([96, 96, 96 + tw2 + 40, 96 + 56], fill=(8, 20, 26, 220), outline=CY + (160,), width=2)
    spaced(d, (116, 108), "OPEN SOURCE", f_tag, CY + (240,), 5)

    spaced(d, (96, 300), "现 实 版", f_kicker, CY + (235,), 4)
    glow_text(img, (92, 368), "GTA 扫描", f_title, WHITE, 5, 24, 120)
    d = ImageDraw.Draw(img)
    spaced(d, (98, 560), "手机对着车，弹出游戏卡片", f_sub, DIM + (240,), 2)

    d.line([(96, 680), (720, 680)], fill=CY + (70,), width=1)
    spaced(d, (96, 706), "端侧 AI · 不联网 · 不上传", f_small, (110, 130, 145, 235), 2)

    wm = "AI 生成 · 仅供娱乐"
    spaced(d, (96, 990), wm, f_small, (255, 255, 255, 80), 2)
    return img.convert("RGB")


if __name__ == "__main__":
    out = os.path.join(ROOT, "video")
    os.makedirs(out, exist_ok=True)
    v = make_vertical()
    v.save(os.path.join(out, "cover-vertical.png"))
    print("vertical", v.size)
    w = make_wide()
    w.save(os.path.join(out, "cover-wide.png"))
    print("wide", w.size)
