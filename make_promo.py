# -*- coding: utf-8 -*-
"""
宣传片渲染器：1080x1920 / 30fps / ~15s
用现有截图做「手机框 + 扫描动效 + 文字」合成，ffmpeg 编码。
"""
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.abspath(__file__))
W, H = 1080, 1920
FPS = 30
DUR = 15.2

CY = (125, 246, 255)
WHITE = (234, 246, 249)
BG_TOP = (10, 18, 24)
BG_BOT = (3, 5, 8)

FONT_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"
FONT_REG = r"C:\Windows\Fonts\msyh.ttc"

PHONE_W = 640
PHONE_H = int(PHONE_W * 720 / 390)
PX = (W - PHONE_W) // 2
PY = (H - PHONE_H) // 2
RADIUS = 46


def font(path, size):
    return ImageFont.truetype(path, size)


def make_bg():
    img = Image.new("RGB", (W, H), BG_BOT)
    d = ImageDraw.Draw(img)
    for y in range(H):
        k = y / H
        c = tuple(int(BG_TOP[i] * (1 - k) + BG_BOT[i] * k) for i in range(3))
        d.line([(0, y), (W, y)], fill=c)
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([-W * 0.25, H * 0.12, W * 1.25, H * 0.92], fill=(9, 38, 50))
    glow = glow.filter(ImageFilter.GaussianBlur(220))
    return Image.blend(img, glow, 0.55)


def spaced_text(d, xy, text, f, fill, tracking=0):
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += d.textlength(ch, font=f) + tracking
    return x


def spaced_width(d, text, f, tracking=0):
    return sum(d.textlength(ch, font=f) + tracking for ch in text) - tracking


# ---------------- 手机 ----------------


def load_screen(name):
    im = Image.open(os.path.join(ROOT, name)).convert("RGB")
    return im.resize((PHONE_W, PHONE_H), Image.LANCZOS)


def phone_mask():
    m = Image.new("L", (PHONE_W, PHONE_H), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, PHONE_W - 1, PHONE_H - 1], radius=RADIUS, fill=255)
    return m


MASK = phone_mask()

BAND_H = 170
BAND = Image.new("RGBA", (PHONE_W, BAND_H), (0, 0, 0, 0))
_bd = ImageDraw.Draw(BAND)
for _y in range(BAND_H):
    _k = 1 - abs(_y - BAND_H / 2) / (BAND_H / 2)
    _bd.line([(0, _y), (PHONE_W, _y)], fill=CY + (int(80 * _k ** 2),))
BAND = BAND.filter(ImageFilter.GaussianBlur(6))


def make_phone(screen):
    """返回带边框与发光的手机图像（RGBA，带 padding）"""
    pad = 60
    canvas = Image.new("RGBA", (PHONE_W + pad * 2, PHONE_H + pad * 2), (0, 0, 0, 0))

    # 外发光
    glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.rounded_rectangle([pad - 10, pad - 10, pad + PHONE_W + 10, pad + PHONE_H + 10],
                         radius=RADIUS + 10, fill=(60, 200, 220, 90))
    glow = glow.filter(ImageFilter.GaussianBlur(28))
    canvas = Image.alpha_composite(canvas, glow)

    # 机身
    body = Image.new("RGBA", (PHONE_W + 24, PHONE_H + 24), (0, 0, 0, 0))
    ImageDraw.Draw(body).rounded_rectangle([0, 0, PHONE_W + 23, PHONE_H + 23],
                                           radius=RADIUS + 12, fill=(18, 24, 30, 255))
    canvas.alpha_composite(body, (pad - 12, pad - 12))

    # 屏幕
    scr = screen.convert("RGBA")
    scr.putalpha(MASK)
    canvas.alpha_composite(scr, (pad, pad))

    # 边框描边
    bd = ImageDraw.Draw(canvas)
    bd.rounded_rectangle([pad, pad, pad + PHONE_W - 1, pad + PHONE_H - 1],
                         radius=RADIUS, outline=(120, 230, 245, 200), width=2)
    return canvas


def paste_phone(frame, phone, cx, cy, alpha=1.0):
    ph = phone
    if alpha < 1.0:
        ph = phone.copy()
        a = ph.getchannel("A").point(lambda v: int(v * alpha))
        ph.putalpha(a)
    frame.paste(ph, (int(cx - ph.width / 2), int(cy - ph.height / 2)), ph)


# ---------------- 场景 ----------------


def build_text_layer(lines, y0):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    y = y0
    for text, f, fill, tracking, gap in lines:
        w = spaced_width(d, text, f, tracking)
        spaced_text(d, ((W - w) / 2, y), text, f, fill, tracking)
        y += f.size + gap
    return layer


def with_alpha(layer, a):
    out = layer.copy()
    out.putalpha(out.getchannel("A").point(lambda v: int(v * a)))
    return out


def ease_out(x):
    return 1 - (1 - x) ** 3


def clamp(v, a=0.0, b=1.0):
    return max(a, min(b, v))


def main():
    os.makedirs(os.path.join(ROOT, "video"), exist_ok=True)

    bgimg = make_bg()

    scr_hud = load_screen("shot-hud.png")
    scr_scan = load_screen("shot-scan.png")
    scr_res = load_screen("shot-result.png")

    ph_hud = make_phone(scr_hud)
    ph_scan = make_phone(scr_scan)
    ph_res = make_phone(scr_res)

    f_title = font(FONT_BOLD, 128)
    f_sub = font(FONT_REG, 38)
    f_mid = font(FONT_BOLD, 64)
    f_small = font(FONT_REG, 30)
    f_tiny = font(FONT_REG, 26)

    # 标题层
    title_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    td = ImageDraw.Draw(title_layer)
    tw = spaced_width(td, "AI 车扫", f_title, 12)
    spaced_text(td, ((W - tw) / 2, 810), "AI 车扫", f_title, WHITE + (255,), 12)
    # 青光
    glow_t = title_layer.filter(ImageFilter.GaussianBlur(24))
    title_layer = Image.alpha_composite(glow_t.point(lambda v: v // 2) if False else glow_t, title_layer)

    sub_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sub_layer)
    sw = spaced_width(sd, "现实版 GTA 扫描界面", f_sub, 6)
    spaced_text(sd, ((W - sw) / 2, 985), "现实版 GTA 扫描界面", f_sub, CY + (230,), 6)
    line_w = 380
    sd.line([((W - line_w) / 2, 1070), ((W + line_w) / 2, 1070)], fill=CY + (120,), width=2)

    slogan_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(slogan_layer)
    l1 = "扫一下"
    l2 = "就知道它是什么车"
    w1 = spaced_width(gd, l1, f_mid, 10)
    spaced_text(gd, ((W - w1) / 2, 860), l1, f_mid, WHITE + (255,), 10)
    w2 = spaced_width(gd, l2, f_sub, 4)
    spaced_text(gd, ((W - w2) / 2, 975), l2, f_sub, CY + (220,), 4)

    end_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ed = ImageDraw.Draw(end_layer)
    t1 = "github.com/nightdark-ui/ai-car-scan"
    w = spaced_width(ed, t1, f_tiny, 2)
    spaced_text(ed, ((W - w) / 2, 880), t1, f_tiny, CY + (235,), 2)
    t2 = "APK 已在 Releases 页开放下载"
    w2 = spaced_width(ed, t2, f_sub, 4)
    spaced_text(ed, ((W - w2) / 2, 940), t2, f_sub, WHITE + (230,), 4)
    t3 = "AI 生成 · 仅供娱乐"
    w3 = spaced_width(ed, t3, f_small, 6)
    spaced_text(ed, ((W - w3) / 2, 1040), t3, f_small, (150, 170, 180, 210), 6)

    # 底部常驻水印
    wm = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    wmd = ImageDraw.Draw(wm)
    wt = "AI 生成 · 仅供娱乐"
    ww = spaced_width(wmd, wt, f_tiny, 6)
    spaced_text(wmd, ((W - ww) / 2, 1830), wt, f_tiny, (255, 255, 255, 70), 6)

    def frame_at(t):
        img = bgimg.copy()

        # --- 场景时间轴 ---
        if t < 2.4:
            a = clamp((t - 0.15) / 0.7)
            img = Image.alpha_composite(img.convert("RGBA"), with_alpha(title_layer, a)).convert("RGB")
            img = Image.alpha_composite(img.convert("RGBA"), with_alpha(sub_layer, a)).convert("RGB")
            # 轻微放大
            s = 1 + 0.02 * (t / 2.4)
            return img

        if t < 3.4:
            # 手机滑入
            k = ease_out(clamp((t - 2.4) / 0.9))
            cy = PY + PHONE_H / 2 + (H - PY) * (1 - k)
            alpha = clamp((t - 2.4) / 0.5)
            paste_phone(img, ph_hud, W / 2, cy, alpha)
            return img

        if t < 7.4:
            # 扫描
            lt = t - 3.4
            paste_phone(img, ph_scan, W / 2, PY + PHONE_H / 2)
            # 扫描光带
            prog = (lt * 0.5) % 1.0
            sy = PY + int(PHONE_H * (0.24 + 0.5 * prog))
            rgba = img.convert("RGBA")
            rgba.alpha_composite(BAND, (PX, sy - BAND_H // 2))
            dd = ImageDraw.Draw(rgba)
            dd.line([(PX + 6, sy), (PX + PHONE_W - 6, sy)], fill=CY + (255,), width=2)
            img = rgba.convert("RGB")
            # 提示文字
            d2 = ImageDraw.Draw(img)
            f_hint = font(FONT_BOLD, 34)
            ht = "长 按 扫 描"
            hw = spaced_width(d2, ht, f_hint, 4)
            alpha = int(200 * (0.55 + 0.45 * math.sin(lt * 5)))
            d2.text(((W - hw) / 2, PY + PHONE_H + 70), ht, font=f_hint, fill=(200, 240, 250, alpha))
            return img

        if t < 7.8:
            # 白闪
            k = (t - 7.4) / 0.4
            img = Image.alpha_composite(img.convert("RGBA"),
                                        Image.new("RGBA", (W, H), (220, 250, 255, int(190 * (1 - k))))).convert("RGB")
            return img

        if t < 12.2:
            lt = t - 7.8
            # 结果卡：从偏移滑入 + 缓慢推近
            k = ease_out(clamp(lt / 0.7))
            zoom = 1.0 + 0.05 * clamp(lt / 4.4)
            cy = PY + PHONE_H / 2 + 80 * (1 - k)
            ph = ph_res
            if zoom > 1.001:
                nw, nh = int(ph.width * zoom), int(ph.height * zoom)
                ph = ph.resize((nw, nh), Image.LANCZOS)
            paste_phone(img, ph, W / 2, cy, clamp(lt / 0.5))
            return img

        if t < 13.8:
            a = clamp((t - 12.2) / 0.6)
            img = Image.alpha_composite(img.convert("RGBA"), with_alpha(slogan_layer, a)).convert("RGB")
            return img

        a = clamp((t - 13.8) / 0.6)
        img = Image.alpha_composite(img.convert("RGBA"), with_alpha(end_layer, a)).convert("RGB")
        return img

    # 预览模式
    if "--preview" in sys.argv:
        os.makedirs(os.path.join(ROOT, "video", "preview"), exist_ok=True)
        for t in [1.0, 2.9, 5.0, 7.6, 9.5, 13.0, 14.8]:
            frame_at(t).save(os.path.join(ROOT, "video", "preview", f"t{t:.1f}.png"))
            print("preview", t)
        return

    import subprocess

    ffmpeg = os.environ.get("FFMPEG_BIN", r"C:\Users\49338.NIGHT\AppData\Local\Temp\ffmi\package\ffmpeg.exe")
    out = os.path.join(ROOT, "video", "promo.mp4")
    n = int(DUR * FPS)
    proc = subprocess.Popen(
        [ffmpeg, "-y", "-loglevel", "error",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
         "-i", "-", "-c:v", "libx264", "-crf", "20", "-preset", "medium",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", out],
        stdin=subprocess.PIPE)
    for i in range(n):
        t = i / FPS
        img = frame_at(t)
        img = Image.alpha_composite(img.convert("RGBA"), wm).convert("RGB")
        proc.stdin.write(img.tobytes())
        if i % 90 == 0:
            print(f"{i}/{n}", flush=True)
    proc.stdin.close()
    proc.wait()
    print("done:", out, round(os.path.getsize(out) / 1e6, 2), "MB")


if __name__ == "__main__":
    main()
