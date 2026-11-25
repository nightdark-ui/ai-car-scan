from PIL import Image, ImageDraw
import os

root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "android", "app", "src", "main", "res")
sizes = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}

CY = (125, 246, 255)
BG = (5, 8, 11)


def make(size):
    # 4x 超采样后缩小，边缘更干净
    k = 4
    s = size * k
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    # 圆角底
    pad = int(s * 0.02)
    r = int(s * 0.22)
    d.rounded_rectangle([pad, pad, s - pad, s - pad], radius=r, fill=BG + (255,))

    # 四角取景框
    m = int(s * 0.27)      # 内边距
    L = int(s * 0.17)      # 角长度
    w = max(2, int(s * 0.045))
    for (x, y, dx, dy) in [
        (m, m, 1, 1),
        (s - m, m, -1, 1),
        (m, s - m, 1, -1),
        (s - m, s - m, -1, -1),
    ]:
        d.line([(x, y), (x + dx * L, y)], fill=CY + (255,), width=w)
        d.line([(x, y), (x, y + dy * L)], fill=CY + (255,), width=w)

    # 中心点 + 外环
    cx = cy = s // 2
    rr = int(s * 0.115)
    d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=CY + (110,), width=max(1, int(s * 0.018)))
    dr = int(s * 0.045)
    d.ellipse([cx - dr, cy - dr, cx + dr, cy + dr], fill=(255, 255, 255, 255))

    return im.resize((size, size), Image.LANCZOS)


for dpi, px in sizes.items():
    folder = os.path.join(root, f"mipmap-{dpi}")
    os.makedirs(folder, exist_ok=True)
    img = make(px)
    img.save(os.path.join(folder, "ic_launcher.png"), "PNG")
    img.save(os.path.join(folder, "ic_launcher_round.png"), "PNG")
    print(f"mipmap-{dpi}: {px}x{px}")
