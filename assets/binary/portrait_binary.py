"""Portrait built from a binary payload only -- and decodable back to ASCII.

The procedure
-------------
  1. build  : every glyph in the portrait is one bit of the payload.
  2. copy   : copy the whole art block out of portrait_binary.txt.
  3. decrypt: group the copied bits in 8s (MSB first) -> ASCII text.

No filler bits, no repetition, no characters: each of the 12,720 bits appears
exactly once, so the art is a complete, copyable copy of the payload.

Build  : python3 portrait_binary.py --bits payload.bits --image photo.png --width 190
Decode : python3 portrait_binary.py --decode portrait_binary.txt
Check  : python3 portrait_binary.py --bits payload.bits --verify-art portrait_binary.txt

Requires: pip install pillow
"""
import argparse
import hashlib
import sys

from PIL import Image, ImageDraw, ImageFont

FONTS = ["/System/Library/Fonts/Menlo.ttc", "/System/Library/Fonts/SFNSMono.ttf"]
CELL_W, CELL_H = 6, 12
FONT_SIZE = 10
CUTOFF = 236
BAYER = ([0, 8, 2, 10],
         [12, 4, 14, 6],
         [3, 11, 1, 9],
         [15, 7, 13, 5])


def font(size=FONT_SIZE):
    for path in FONTS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def read_bits(path):
    bits = "".join(ch for ch in open(path).read() if ch in "01")
    if not bits:
        sys.exit(f"no bits in {path}")
    if len(bits) % 8:
        sys.exit("payload is not a whole number of bytes")
    return bits


def decode_bits(bits):
    return bytes(int(bits[i:i + 8], 2) for i in range(0, len(bits), 8)).decode(
        "ascii", "replace")


def extract(text):
    """Bits as they are copied out of the art: whitespace ignored, order kept."""
    return "".join(ch for ch in text if ch in "01")


def photo_cells(path, cols):
    img = Image.open(path).convert("RGBA")
    flat = Image.new("RGBA", img.size, (255, 255, 255, 255))
    flat.alpha_composite(img)
    gray = flat.convert("L")
    rows = max(1, round(gray.height * cols / gray.width * 0.5))
    small = gray.resize((cols, rows), Image.LANCZOS)
    return [[small.getpixel((x, y)) for x in range(cols)] for y in range(rows)]


def choose_cells(cells, count):
    """Pick exactly `count` cells: darkest first, 4x4 Bayer break-up at the edges.

    Ranking instead of a fixed threshold is what guarantees the mask holds
    exactly as many cells as there are bits -- so the art is solid, no holes,
    and every bit is placed.
    """
    scored = []
    for y, row in enumerate(cells):
        for x, level in enumerate(row):
            if level >= CUTOFF:
                continue
            strength = (CUTOFF - level) / CUTOFF
            jitter = (BAYER[y % 4][x % 4] + 0.5) / 16 - 0.5
            scored.append((strength + 0.14 * jitter, y, x))
    scored.sort(reverse=True)
    if len(scored) < count:
        sys.exit(f"only {len(scored)} subject cells, need {count} bits "
                 "-- increase --width")
    return {(y, x) for _, y, x in scored[:count]}


def auto_width(path, count):
    """Smallest width whose subject holds every bit, so almost no cell is wasted."""
    lo, hi = 40, 400
    best = hi
    while lo <= hi:
        mid = (lo + hi) // 2
        cells = photo_cells(path, mid)
        have = sum(1 for row in cells for v in row if v < CUTOFF)
        if have >= count:
            best = mid
            hi = mid - 1
        else:
            lo = mid + 1
    return best


def paint(cells, bits, chosen):
    """One distinct bit per chosen cell, in reading order. Nothing else is added."""
    it = iter(bits)
    lines = []
    for y, row in enumerate(cells):
        line = []
        for x in range(len(row)):
            line.append(next(it) if (y, x) in chosen else " ")
        lines.append("".join(line))
    return lines


def shade(level, theme):
    if theme == "dark":
        v = max(0.0, min(1.0, 1 - level / 255)) ** 0.75
        return (0, int(60 + 195 * v), int(30 + 80 * v))
    t = max(0.0, min(1.0, level / 255)) ** 0.9
    return (0, int(115 * t), int(42 * t))


def render(cells, lines, path, title, theme):
    fnt = font()
    pad = 10
    w = CELL_W * len(lines[0]) + pad * 2
    h = CELL_H * len(lines) + pad * 2 + (20 if title else 0)
    img = Image.new("RGB", (w, h), (0, 0, 0) if theme == "dark" else (255, 255, 255))
    d = ImageDraw.Draw(img)
    if title:
        d.text((pad, 4), title, font=font(10),
               fill=(0, 170, 60) if theme == "dark" else (0, 110, 45))
    top = pad + (20 if title else 0)
    for y, line in enumerate(lines):
        for x, ch in enumerate(line):
            if ch == " ":
                continue
            col = shade(cells[y][x], theme)
            d.text((pad + x * CELL_W, top + y * CELL_H - 2), ch, font=fnt,
                   fill=col, stroke_width=1, stroke_fill=col)
    img.save(path)


def report(bits):
    text = decode_bits(bits)
    printable = sum(1 for b in text.encode("ascii", "replace") if 32 <= b < 127 or b in (9, 10, 13))
    return text, printable


def main():
    p = argparse.ArgumentParser(description="Portrait from bits, decodable to ASCII.")
    p.add_argument("--bits", default="payload.bits")
    p.add_argument("--image")
    p.add_argument("--width", type=int, default=0,
                   help="columns of the grid; 0 = auto-fit to the payload")
    p.add_argument("--decode", metavar="ART", help="decode a copied art file to ASCII")
    p.add_argument("--verify-art", metavar="ART", help="check a copied art file bit-for-bit")
    args = p.parse_args()

    if args.decode:
        bits = extract(open(args.decode).read())
        whole = bits[:len(bits) - len(bits) % 8]
        text = decode_bits(whole)
        print(f"copied bits : {len(bits)}")
        print(f"bytes       : {len(whole) // 8}")
        print(f"ascii       : {text[:80]!r}...")
        open("decoded_message.txt", "w").write(text + "\n")
        print("saved -> decoded_message.txt")
        return 0

    if args.verify_art:
        want = read_bits(args.bits)
        got = extract(open(args.verify_art).read())
        same = got == want
        print(f"payload bits: {len(want)}")
        print(f"art bits    : {len(got)}")
        print(f"identical   : {same}")
        print(f"fingerprint : {hashlib.sha256(got.encode()).hexdigest()[:16]}")
        if same:
            text = decode_bits(got)
            print(f"ascii       : {text[:80]!r}...")
        return 0 if same else 1

    if not args.image:
        sys.exit("--image is required (or use --decode / --verify-art)")

    bits = read_bits(args.bits)
    width = args.width or auto_width(args.image, len(bits))
    cells = photo_cells(args.image, width)
    chosen = choose_cells(cells, len(bits))
    lines = paint(cells, bits, chosen)

    art = "\n".join(lines) + "\n"
    open("portrait_binary.txt", "w").write(art)
    render(cells, lines, "portrait_binary.png",
           "BINARY ONLY // built from 12720 bits", "dark")
    render(cells, lines, "portrait_binary_print.png",
           "BINARY ONLY // built from 12720 bits", "light")

    recovered = extract(art)
    text, printable = report(bits)

    print(f"payload     : {len(bits)} bits = {len(bits) // 8} bytes")
    print(f"grid        : {len(lines[0])}x{len(lines)} cells (width {width})")
    print(f"dropped     : {sum(1 for row in cells for v in row if v < CUTOFF) - len(chosen)} faintest subject cells")
    print(f"filled      : {len(chosen)} cells = 1 bit each (all bits used once)")
    print(f"blank       : {len(lines[0]) * len(lines) - len(chosen)} cells")
    print(f"copy-out    : {len(recovered)} bits recovered")
    print(f"identical   : {recovered == bits}")
    print(f"decodes to  : {text[:60]!r}...")
    print(f"printable   : {printable}/{len(bits) // 8} bytes are ASCII text")
    print(f"fingerprint : {hashlib.sha256(bits.encode()).hexdigest()[:16]}")
    print("files       : portrait_binary.txt, portrait_binary.png, portrait_binary_print.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
