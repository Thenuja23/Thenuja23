"""Render the portrait's decryption as a green-on-black terminal animation.

Frames are built from the *same* art (182 x 136 cells) and the *same* render,
so every bit sits in exactly the cell it occupies in the static image.

  phase 1  boot      prompt types, field is noise
  phase 2  scan      a decode line sweeps down; rows behind it lock to real bits
  phase 3  hold      full portrait, ACCESS GRANTED, refresh sweep, blinking cursor
  phase 4  power-off fade, so the loop restarts cleanly

Run:  python3 make_decrypt_gif.py
Out:  decrypt.gif
"""
import random

from PIL import Image, ImageDraw, ImageFont

ART = "portrait_binary.txt"
RENDER = "portrait_dark.png"
OUT = "decrypt.gif"

COLS, ROWS = 182, 136
CW, CH = 3, 6                 # one bit = 3 x 6 px
MARGIN, TOP = 24, 60
W, H = COLS * CW + MARGIN * 2, ROWS * CH + TOP + 24
FIELD_W, FIELD_H = COLS * CW, ROWS * CH

BG = (5, 8, 10)
CHROME = (9, 13, 16)
RULE = (22, 34, 40)
INK = (16, 210, 138)          # a 1 in the real portrait
DIM = (0, 104, 68)            # a 0 in the real portrait
HOT = (186, 255, 224)         # scan line / fresh lock
TEXT = (150, 168, 178)
TEXT_DIM = (78, 92, 100)
ACCENT = (16, 185, 129)
BRIGHT = (226, 240, 236)
RED, AMBER = (255, 95, 86), (255, 189, 46)
FONTS = ["/System/Library/Fonts/Menlo.ttc", "/System/Library/Fonts/SFNSMono.ttf"]

COMMAND = "./decrypt --portrait"
FINGERPRINT = "d97378e23e78681e"


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
    """Per-cell brightness taken from the static render, so shading matches.

    The static render uses its own layout (10 px pad, 20 px caption, 6x12 cells),
    which is not the GIF layout -- sample it on its own terms.
    """
    pad, title, s_cw, s_ch = 10, 20, 6, 12
    small = Image.open(RENDER).convert("L").crop(
        (pad, pad + title, pad + s_cw * COLS, pad + title + s_ch * ROWS)).resize(
        (COLS, ROWS), Image.BOX)
    px = small.load()
    return [[px[c, r] / 255 for c in range(COLS)] for r in range(ROWS)]


def palette_image():
    """A fixed palette with lots of dark green steps, so the black stays black."""
    colors = [BG, CHROME, RULE, RED, AMBER, ACCENT, TEXT, TEXT_DIM, BRIGHT]
    for i in range(56):                       # black -> ink
        f = i / 55
        colors.append((int(16 * f), int(210 * f), int(138 * f)))
    for i in range(20):                       # ink -> hot
        f = i / 19
        colors.append((int(16 + 170 * f), int(210 + 45 * f), int(138 + 86 * f)))
    for i in range(14):                       # greys
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


def shade(rgb, level):
    return tuple(max(0, min(255, int(v * level))) for v in rgb)


def field_image(locked_rows, scan_row, tone, noise, boot):
    """3x6 block per cell: real bit above the scan, drifting noise below."""
    img = Image.new("RGB", (COLS, ROWS), BG)
    px = img.load()
    for r in range(ROWS):
        locked = (not boot) and r < locked_rows
        for c in range(COLS):
            t = tone[r][c]
            if locked:
                b = GRID[r][c]
                if b == " ":
                    px[c, r] = BG
                else:
                    level = 0.45 + 0.55 * t
                    px[c, r] = shade(INK if b == "1" else DIM, level)
            else:
                b, level = noise[r][c]
                if t < 0.04 and level < 0.35:
                    px[c, r] = BG
                else:
                    px[c, r] = shade(HOT if b == "1" else INK, level * (0.45 + 0.55 * t))
        if (not boot) and r == scan_row:
            for c in range(COLS):
                px[c, r] = HOT
    return img.resize((FIELD_W, FIELD_H), Image.NEAREST)


def chrome():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 58], fill=CHROME)
    d.line([0, 58, W, 58], fill=RULE)
    for i, col in enumerate((RED, AMBER, ACCENT)):
        d.ellipse([14 + i * 14, 10, 22 + i * 14, 18], fill=col)
    d.text((58, 10), "thenuja@ceylonforce: ~/binary-portrait", font=font(9), fill=TEXT_DIM)
    d.rectangle([0, H - 22, W, H], fill=CHROME)
    d.text((MARGIN, H - 18), f"sha256 {FINGERPRINT}", font=font(8), fill=TEXT_DIM)
    d.text((W - MARGIN - 122, H - 18), "182x136  ·  1 bit/cell", font=font(8), fill=TEXT_DIM)
    return img


def bar(p, width=26):
    n = int(round(p * width))
    return "[" + "#" * n + "." * (width - n) + "]"


def overlay(img, typed, progress, status, cursor_on, log):
    d = ImageDraw.Draw(img)
    d.text((MARGIN, 28), "root@thenuja:~$", font=font(10), fill=ACCENT)
    d.text((MARGIN + 104, 28), typed, font=font(10), fill=BRIGHT)
    if cursor_on:
        x = MARGIN + 104 + len(typed) * 6
        d.rectangle([x + 1, 27, x + 7, 39], fill=INK)
    colour = ACCENT if progress >= 1 else INK
    d.text((MARGIN, 44), f"{bar(progress)} {int(progress * 100):3d}%  {status}",
           font=font(9), fill=colour)
    if log:
        d.text((W - MARGIN - len(log) * 7, 44), log, font=font(9), fill=ACCENT)


def main():
    global GRID
    GRID = load_art()
    tone = cell_tone()
    rng = random.Random(11)

    noise = [[("1" if rng.random() < 0.5 else "0", rng.uniform(0.12, 1.0))
              for _ in range(COLS)] for _ in range(ROWS)]

    def drift(amount=0.10):
        for _ in range(int(COLS * ROWS * amount)):
            c, r = rng.randrange(COLS), rng.randrange(ROWS)
            noise[r][c] = ("1" if rng.random() < 0.5 else "0", rng.uniform(0.12, 1.0))

    base = chrome()
    pal = palette_image()

    frames = []
    boot, scan, hold, off = 5, 26, 8, 3
    total = boot + scan + hold + off

    for i in range(total):
        img = base.copy()
        drift()

        if i < boot:                                     # boot / typing
            field = field_image(0, -1, tone, noise, boot=True)
            overlay(img, COMMAND[: (i + 1) * 5], 0.0, "mount /dev/bio", i % 2 == 0, "")
        elif i < boot + scan:                            # scan
            p = (i - boot) / (scan - 1)
            rows = int(p * ROWS)
            field = field_image(rows, min(rows, ROWS - 1), tone, noise, boot=False)
            overlay(img, COMMAND, p, f"decrypting {rows * COLS:>6}/24752 cells", True, "")
        elif i < boot + scan + hold:                     # portrait + refresh sweep
            k = i - (boot + scan)
            field = field_image(ROWS, -1, tone, noise, boot=False)
            if k < 4:                                    # sweep highlight
                y = int((k / 4) * FIELD_H)
                d = ImageDraw.Draw(field)
                d.rectangle([0, y, FIELD_W, y + 3], fill=shade(HOT, 0.35))
            overlay(img, COMMAND, 1.0, "12720 bits placed",
                    k % 2 == 0, "ACCESS GRANTED" if k else "")
        else:                                            # power down
            k = i - (boot + scan + hold)
            field = field_image(ROWS, -1, tone, noise, boot=False)
            field = Image.blend(field, Image.new("RGB", field.size, BG), 0.4 + 0.28 * k)
            overlay(img, COMMAND, 1.0, "", False, "")

        img.paste(field, (MARGIN, TOP))
        frames.append(img.quantize(palette=pal, dither=Image.NONE))

    frames[0].save(OUT, save_all=True, append_images=frames[1:], duration=80,
                   loop=0, optimize=True, disposal=1)
    print(f"{OUT}: {W}x{H}, {total} frames, "
          f"{__import__('os').path.getsize(OUT) / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    main()
