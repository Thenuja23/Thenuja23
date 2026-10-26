"""Animate the portrait drawn with actual binary digits, not pixel blocks.

Two theme variants are produced so the existing <picture> element can stay and
just swap its sources:

  portrait_dark.gif    green digits on near-black   (GitHub dark mode)
  portrait_light.gif   dark green digits on white   (GitHub light mode)

Frames are built from the *same* art (182 x 136 cells) and the *same* static
render, so every bit stays in the cell it occupies in the still image. Each
cell is drawn with a 5x7 glyph for '0' or '1' -- never a filled rectangle --
so the portrait is literally made of binary code.

  phase 1  boot      prompt types, field is a wall of raw digits
  phase 2  scan      a decode line sweeps down; rows behind it lock to real bits
  phase 3  hold      full portrait, ACCESS GRANTED, refresh sweep, blinking cursor
  phase 4  power-off fade, so the loop restarts cleanly

Run:  python3 make_portrait_gifs.py
"""
import random

from PIL import Image, ImageDraw, ImageFont

ART = "portrait_binary.txt"
TONE_SOURCES = ("portrait_dark.png", "portrait_binary.png")   # same geometry as the still

COLS, ROWS = 182, 136
CW, CH = 6, 12                # one bit = one 6x12 cell, digit glyph is 5x7
MARGIN, TOP = 24, 60
W, H = COLS * CW + MARGIN * 2, ROWS * CH + TOP + 24
FIELD_W, FIELD_H = COLS * CW, ROWS * CH
GLYPH_DX, GLYPH_DY = 0, 2     # 5x7 digit inside its 6x12 cell

DARK = dict(
    bg=(5, 8, 10), chrome=(9, 13, 16), rule=(22, 34, 40),
    ink=(32, 240, 168), dim=(0, 132, 86), hot=(196, 255, 230),
    text=(150, 168, 178), text_dim=(78, 92, 100),
    accent=(16, 185, 129), bright=(226, 240, 236),
    red=(255, 95, 86), amber=(255, 189, 46), out="portrait_dark.gif",
)
LIGHT = dict(
    bg=(255, 255, 255), chrome=(242, 246, 244), rule=(206, 219, 213),
    ink=(0, 96, 60), dim=(128, 182, 158), hot=(0, 40, 26),
    text=(58, 72, 68), text_dim=(132, 148, 143),
    accent=(5, 145, 100), bright=(18, 38, 32),
    red=(255, 95, 86), amber=(230, 160, 20), out="portrait_light.gif",
)

FONTS = ["/System/Library/Fonts/Menlo.ttc", "/System/Library/Fonts/SFNSMono.ttf"]
COMMAND = "./decrypt --portrait"
FINGERPRINT = "d97378e23e78681e"

# 5x7 digits: a real '0' has a hole, a real '1' is a stem with a base serif.
GLYPH = {
    "0": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
}
GLYPH_BYTES = {
    ch: tuple(bytes(255 if b == "1" else 0 for b in row) for row in rows)
    for ch, rows in GLYPH.items()
}


def font(size):
    for path in FONTS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def load_art():
    lines = [l for l in open(ART).read().split("\n") if l != ""]
    assert len(lines) == ROWS and all(len(l) == COLS for l in lines)
    return lines


def cell_tone():
    """Per-cell ink level from the static render (its own 10/20/6x12 layout)."""
    pad, title, s_cw, s_ch = 10, 20, 6, 12
    src = next(p for p in TONE_SOURCES if __import__("os").path.exists(p))
    small = Image.open(src).convert("L").crop(
        (pad, pad + title, pad + s_cw * COLS, pad + title + s_ch * ROWS)).resize(
        (COLS, ROWS), Image.BOX)
    px = small.load()
    tone = [[px[c, r] / 255 for c in range(COLS)] for r in range(ROWS)]
    flat = sorted(v for row in tone for v in row)
    top = flat[int(len(flat) * 0.98)] or 1.0
    return [[min(1.0, v / top) for v in row] for row in tone]


def lerp(a, b, f):
    return tuple(int(x + (y - x) * f) for x, y in zip(a, b))


def palette(th):
    """Fixed palette: dense steps between paper and ink, so nothing washes out."""
    colors = [th["bg"], th["chrome"], th["rule"], th["red"], th["amber"],
              th["accent"], th["text"], th["text_dim"], th["bright"]]
    for i in range(56):
        colors.append(lerp(th["bg"], th["ink"], i / 55))
    for i in range(20):
        colors.append(lerp(th["ink"], th["hot"], i / 19))
    for i in range(14):
        v = int(255 * i / 13)
        colors.append((v, v, v))
    flat = []
    for c in colors[:256]:
        flat.extend(c)
    while len(flat) < 768:
        flat.extend(colors[-1])
    pal = Image.new("P", (1, 1))
    pal.putpalette(flat)
    return pal


def shade(rgb, level, th):
    if th is LIGHT:
        return lerp(th["bg"], rgb, level)
    return tuple(max(0, min(255, int(v * level))) for v in rgb)


def glyph_mask(chars):
    """One 5x7 digit per cell, written straight into a full-size L mask."""
    buf = bytearray(FIELD_W * FIELD_H)
    span = FIELD_W
    for r in range(ROWS):
        ybase = (r * CH + GLYPH_DY) * span
        for c in range(COLS):
            ch = chars[r][c]
            if ch == " ":
                continue
            x0 = ybase + c * CW + GLYPH_DX
            for gy, src in enumerate(GLYPH_BYTES[ch]):
                at = x0 + gy * span
                buf[at:at + 5] = src
    return Image.frombytes("L", (FIELD_W, FIELD_H), bytes(buf))


def field_image(locked_rows, scan_row, tone, noise, boot, th, sweep_row=None):
    """Digit grid -> glyph mask -> per-cell colour, keeping every bit in place."""
    chars = [[" "] * COLS for _ in range(ROWS)]
    colors = Image.new("RGB", (COLS, ROWS), th["bg"])
    cp = colors.load()

    for r in range(ROWS):
        locked = (not boot) and r < locked_rows
        for c in range(COLS):
            t = tone[r][c]
            if locked:
                b = GRID[r][c]
                if b == " ":
                    continue
                chars[r][c] = b
                cp[c, r] = shade(th["ink"] if b == "1" else th["dim"],
                                 0.68 + 0.32 * t, th)
            else:
                b, level = noise[r][c]
                chars[r][c] = b
                cp[c, r] = shade(th["hot"] if b == "1" else th["ink"],
                                 level * (0.50 + 0.50 * t), th)
        if ((not boot) and r == scan_row) or (sweep_row is not None and r == sweep_row):
            for c in range(COLS):
                if chars[r][c] == " ":
                    chars[r][c] = "0" if c % 2 else "1"
                cp[c, r] = th["hot"]

    mask = glyph_mask(chars)
    field = Image.new("RGB", (FIELD_W, FIELD_H), th["bg"])
    field.paste(colors.resize((FIELD_W, FIELD_H), Image.NEAREST), (0, 0), mask)

    if ((not boot) and scan_row >= 0) or sweep_row is not None:
        row = scan_row if (not boot) and scan_row >= 0 else sweep_row
        y = min(FIELD_H - 2, row * CH + 10)
        ImageDraw.Draw(field).rectangle([0, y, FIELD_W, y + 1], fill=th["hot"])
    return field


def chrome(th):
    img = Image.new("RGB", (W, H), th["bg"])
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 58], fill=th["chrome"])
    d.line([0, 58, W, 58], fill=th["rule"])
    for i, col in enumerate((th["red"], th["amber"], th["accent"])):
        d.ellipse([14 + i * 14, 10, 22 + i * 14, 18], fill=col)
    d.text((58, 10), "thenuja@ceylonforce: ~/binary-portrait", font=font(9),
           fill=th["text_dim"])
    d.rectangle([0, H - 22, W, H], fill=th["chrome"])
    d.text((MARGIN, H - 18), f"sha256 {FINGERPRINT}", font=font(8), fill=th["text_dim"])
    d.text((W - MARGIN - 122, H - 18), "182x136  ·  1 bit/cell", font=font(8),
           fill=th["text_dim"])
    return img


def bar(p, width=26):
    n = int(round(p * width))
    return "[" + "#" * n + "." * (width - n) + "]"


def overlay(img, typed, progress, status, cursor_on, log, th):
    d = ImageDraw.Draw(img)
    d.text((MARGIN, 28), "root@thenuja:~$", font=font(10), fill=th["accent"])
    d.text((MARGIN + 104, 28), typed, font=font(10), fill=th["bright"])
    if cursor_on:
        x = MARGIN + 104 + len(typed) * 6
        d.rectangle([x + 1, 27, x + 7, 39], fill=th["ink"])
    colour = th["accent"] if progress >= 1 else th["ink"]
    d.text((MARGIN, 44), f"{bar(progress)} {int(progress * 100):3d}%  {status}",
           font=font(9), fill=colour)
    if log:
        d.text((W - MARGIN - len(log) * 7, 44), log, font=font(9), fill=th["accent"])


def build(th, tone, seed=11):
    global GRID
    rng = random.Random(seed)
    noise = [[("1" if rng.random() < 0.5 else "0", rng.uniform(0.12, 1.0))
              for _ in range(COLS)] for _ in range(ROWS)]

    def drift(amount=0.10):
        for _ in range(int(COLS * ROWS * amount)):
            c, r = rng.randrange(COLS), rng.randrange(ROWS)
            noise[r][c] = ("1" if rng.random() < 0.5 else "0", rng.uniform(0.12, 1.0))

    base = chrome(th)
    pal = palette(th)
    frames = []
    boot, scan, hold, off = 5, 26, 8, 3

    for i in range(boot + scan + hold + off):
        img = base.copy()
        drift()

        if i < boot:
            field = field_image(0, -1, tone, noise, True, th)
            overlay(img, COMMAND[: (i + 1) * 5], 0.0, "mount /dev/bio",
                    i % 2 == 0, "", th)
        elif i < boot + scan:
            p = (i - boot) / (scan - 1)
            rows = int(p * ROWS)
            field = field_image(rows, min(rows, ROWS - 1), tone, noise, False, th)
            overlay(img, COMMAND, p, f"decrypting {rows * COLS:>6}/24752 cells",
                    True, "", th)
        elif i < boot + scan + hold:
            k = i - (boot + scan)
            sweep = int(k / 4 * ROWS) if k < 4 else None
            field = field_image(ROWS, -1, tone, noise, False, th, sweep_row=sweep)
            overlay(img, COMMAND, 1.0, "12720 bits placed", k % 2 == 0,
                    "ACCESS GRANTED" if k else "", th)
        else:
            k = i - (boot + scan + hold)
            field = field_image(ROWS, -1, tone, noise, False, th)
            field = Image.blend(field, Image.new("RGB", field.size, th["bg"]),
                                0.4 + 0.28 * k)
            overlay(img, COMMAND, 1.0, "", False, "", th)

        img.paste(field, (MARGIN, TOP))
        frames.append(img.quantize(palette=pal, dither=Image.NONE))

    frames[0].save(th["out"], save_all=True, append_images=frames[1:],
                   duration=80, loop=0, optimize=True, disposal=1)
    size = __import__("os").path.getsize(th["out"]) / 1024 / 1024
    print(f"{th['out']}: {W}x{H}, {len(frames)} frames, {size:.2f} MB")


def main():
    global GRID
    GRID = load_art()
    tone = cell_tone()
    build(DARK, tone)
    build(LIGHT, tone)


if __name__ == "__main__":
    main()
