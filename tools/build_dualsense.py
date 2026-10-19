"""Repaint the Xbox button glyphs in the Shaolin Monks font atlases as DualSense prompts.

Input: the LanguagePack PT-BR fonts (XPR0, one DXT5 texture each).
Only the 4x4 DXT5 blocks that touch a repainted glyph are re-encoded; every other byte,
including the 0x800-byte XPR0 header, stays identical to the source file.
"""
from __future__ import annotations
import struct, sys, hashlib
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
from dxt import decode_dxt5

S = 8  # supersampling factor for shapes

# Palette: PS5-style light symbols on a dark button.
OUTLINE = (0, 0, 0, 255)
RIM = (92, 92, 100, 255)
BODY_TOP = (52, 52, 58)
BODY_BOT = (18, 18, 22)
SYMBOL = (236, 236, 236, 255)

# ---------------------------------------------------------------- bitmap labels
FONT5x9 = {
    'L': ["11000"] * 7 + ["11111", "11111"],
    'R': ["11110", "11011", "11011", "11011", "11110", "11100", "11110", "11011", "11011"],
    '1': ["00110", "01110", "11110", "00110", "00110", "00110", "00110", "00110", "00110"],
    '2': ["01110", "11011", "00011", "00011", "00110", "01100", "11000", "11111", "11111"],
    '3': ["11110", "11111", "00011", "00011", "01110", "00011", "00011", "11111", "11110"],
}
# 12-pixel face buttons are drawn pixel by pixel; filtered shapes blur at that size.
SMALL_SYMBOLS = {
    'cross':    ["1000001", "0100010", "0010100", "0001000", "0010100", "0100010", "1000001"],
    'circle':   ["0011100", "0100010", "1000001", "1000001", "1000001", "0100010", "0011100"],
    'square':   ["0000000", "0111110", "0100010", "0100010", "0100010", "0111110", "0000000"],
    'triangle': ["0001000", "0010100", "0010100", "0100010", "0100010", "1000001", "1111111"],
}
FONT5x7 = {
    'L': ["11000", "11000", "11000", "11000", "11000", "11111", "11111"],
    'R': ["11110", "11011", "11011", "11110", "11110", "11011", "11011"],
}
FONT3x5 = {
    'L': ["100", "100", "100", "100", "111"],
    'R': ["110", "101", "110", "101", "101"],
    '1': ["010", "110", "010", "010", "111"],
    '2': ["110", "001", "010", "100", "111"],
    '3': ["110", "001", "010", "001", "110"],
}


def blit_label(img: np.ndarray, text: str, cx: float, cy: float, font: dict) -> None:
    gw, gh = len(next(iter(font.values()))[0]), len(next(iter(font.values())))
    total = len(text) * gw + (len(text) - 1)
    x0 = int(round(cx - total / 2)); y0 = int(round(cy - gh / 2))
    for i, ch in enumerate(text):
        for r, row in enumerate(font[ch]):
            for c, bit in enumerate(row):
                if bit == '1':
                    img[y0 + r, x0 + i * (gw + 1) + c] = SYMBOL


# ---------------------------------------------------------------- shapes (hi-res)
def gradient_fill(layer: Image.Image, mask: Image.Image) -> Image.Image:
    w, h = layer.size
    t = np.linspace(0, 1, h)[:, None]
    rgb = (np.array(BODY_TOP) * (1 - t) + np.array(BODY_BOT) * t)[:, None, :].repeat(w, 1)
    grad = np.dstack([rgb, np.full((h, w), 255)]).astype(np.uint8)
    g = Image.fromarray(grad, 'RGBA')
    out = layer.copy()
    out.paste(g, (0, 0), mask)
    return out


def body(shape: str, w: int, h: int, *, radius_frac=0.5, top_round=False) -> Image.Image:
    """Dark button body with black outline and a light rim, at S-times resolution."""
    W, H = w * S, h * S
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    o = S * 1.0          # black outline width
    rim = S * 0.9        # rim width
    if shape == 'circle':
        dia = min(W, H); x0 = (W - dia) / 2; y0 = (H - dia) / 2
        boxes = [(x0, y0, x0 + dia - 1, y0 + dia - 1)]
        def draw(dd, inset, fill):
            b = boxes[0]; dd.ellipse((b[0] + inset, b[1] + inset, b[2] - inset, b[3] - inset), fill=fill)
    else:
        x0, y0, x1, y1 = 0, 0, W - 1, H - 1
        def draw(dd, inset, fill):
            r = max(1, radius_frac * min(W, H) - inset)
            if top_round:
                rr = (x1 - x0 - 2 * inset) / 2 * 0.95
                dd.rounded_rectangle((x0 + inset, y0 + inset, x1 - inset, y1 - inset), radius=max(1, S * 2.2 - inset * 0.5), fill=fill)
                # dome on top: an ellipse merged into the top half
                dd.ellipse((x0 + inset, y0 + inset, x1 - inset, y0 + inset + 2 * rr * 0.55), fill=fill)
                dd.rectangle((x0 + inset, y0 + inset + rr * 0.55, x1 - inset, y1 - inset - S * 2.2), fill=fill)
            else:
                dd.rounded_rectangle((x0 + inset, y0 + inset, x1 - inset, y1 - inset), radius=r, fill=fill)
    draw(d, 0, OUTLINE)
    draw(d, o, RIM)
    mask = Image.new('L', (W, H), 0)
    draw(ImageDraw.Draw(mask), o + rim, 255)
    return gradient_fill(im, mask)


def symbol(im: Image.Image, kind: str) -> Image.Image:
    W, H = im.size
    d = ImageDraw.Draw(im)
    dia = min(W, H); cx, cy = W / 2, H / 2
    sw = max(S * 1.4, dia * 0.12)        # stroke width
    if kind == 'cross':
        r = dia * 0.25
        d.line((cx - r, cy - r, cx + r, cy + r), fill=SYMBOL, width=int(sw))
        d.line((cx - r, cy + r, cx + r, cy - r), fill=SYMBOL, width=int(sw))
    elif kind == 'circle':
        r = dia * 0.27
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=SYMBOL, width=int(sw))
    elif kind == 'square':
        r = dia * 0.25
        d.rectangle((cx - r, cy - r, cx + r, cy + r), outline=SYMBOL, width=int(sw))
    elif kind == 'triangle':
        r = dia * 0.30
        pts = [(cx, cy - r * 1.0), (cx + r * 1.05, cy + r * 0.72), (cx - r * 1.05, cy + r * 0.72)]
        d.polygon(pts, outline=SYMBOL, width=int(sw))
    elif kind == 'stick':
        # concave stick cap plus four direction arrows: the stick is tilted, not pressed
        r = dia * 0.285
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(40, 40, 46, 255), outline=(96, 96, 106, 255), width=int(S * 0.8))
        a, t, rr = dia * 0.12, dia * 0.085, dia * 0.375
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            tip = (cx + dx * (rr + t), cy + dy * (rr + t))
            base = (cx + dx * (rr - t), cy + dy * (rr - t))
            px, py = -dy, dx
            d.polygon([tip, (base[0] + px * a, base[1] + py * a), (base[0] - px * a, base[1] - py * a)], fill=SYMBOL)
    return im


def downsample(hi: Image.Image) -> np.ndarray:
    a = np.asarray(hi).astype(np.float64)
    al = a[..., 3:4] / 255.0
    pm = np.concatenate([a[..., :3] * al, al], -1)
    H, W = pm.shape[0] // S, pm.shape[1] // S
    pm = pm.reshape(H, S, W, S, 4).mean((1, 3))
    alpha = pm[..., 3:4]
    rgb = np.where(alpha > 1e-6, pm[..., :3] / np.maximum(alpha, 1e-6), 0)
    return np.dstack([rgb, alpha * 255]).round().clip(0, 255).astype(np.uint8)


def make_icon(kind: str, w: int, h: int, label: str | None, small: bool) -> np.ndarray:
    if kind in ('cross', 'circle', 'square', 'triangle'):
        hi = body('circle', w, h) if small else symbol(body('circle', w, h), kind)
    elif kind == 'stick':
        hi = symbol(body('circle', w, h), 'stick')
    elif kind == 'shoulder':
        bh = (9 if small else 14)
        hi = Image.new('RGBA', (w * S, h * S), (0, 0, 0, 0))
        b = body('rect', w, bh, radius_frac=0.42)
        hi.paste(b, (0, ((h - bh) // 2) * S))
    elif kind == 'trigger':
        hi = body('rect', w, h, top_round=True)
    else:
        raise ValueError(kind)
    img = downsample(hi)
    if small and kind in SMALL_SYMBOLS:
        rows = SMALL_SYMBOLS[kind]
        y0 = (h - len(rows)) // 2; x0 = (w - len(rows[0])) // 2
        for r, row in enumerate(rows):
            for c, bit in enumerate(row):
                if bit == '1':
                    img[y0 + r, x0 + c] = SYMBOL
    if label:
        font = FONT3x5 if small else (FONT5x7 if kind == 'stick' else FONT5x9)
        cy = h / 2 + (0.5 if kind != 'trigger' else (1.0 if small else 1.5))
        blit_label(img, label, w / 2, cy, font)
    return img


# ---------------------------------------------------------------- glyph map
# (x0, y0, x1, y1) exclusive, measured from the decoded atlases.
# Xbox -> DualSense follows the port's default mapping (README: White=L1, Black=R1, LT=L2, RT=R2).
SMALL = [
    ((95, 99, 107, 111), 'shoulder', 'L1'),   # White
    ((107, 99, 119, 111), 'trigger', 'L2'),   # L trigger box
    ((0, 113, 11, 125), 'trigger', 'R2'),     # R trigger box
    ((11, 113, 23, 125), 'shoulder', 'R1'),   # Black
    ((71, 112, 83, 124), 'square', None),     # X
    ((83, 112, 95, 124), 'triangle', None),   # Y
    ((95, 112, 107, 124), 'cross', None),     # A
    ((107, 112, 119, 124), 'circle', None),   # B
]
LARGE = [
    # Triggers: left halves (E = PT-BR/EN slot, I = ES, S = IT, G = FR) and the shared D right halves.
    ((189, 210, 209, 228), 'trigger', 'L2'),
    ((209, 210, 229, 228), 'trigger', 'R2'),
    ((63, 210, 83, 228), 'trigger', 'L2'),
    ((83, 210, 103, 228), 'trigger', 'R2'),
    ((21, 147, 41, 165), 'trigger', 'L2'),
    ((42, 147, 62, 165), 'trigger', 'L2'),
    # Shoulder buttons
    ((168, 210, 186, 228), 'shoulder', 'L1'),  # White
    ((231, 210, 249, 228), 'shoulder', 'R1'),  # Black
    # Thumbsticks (grey caps): E/D and S, G, I, D language variants
    # The text calls them "Analógico Esquerdo (])" and "Analógico Direito (`)": tilted sticks, not L3/R3.
    ((0, 230, 20, 251), 'stick', 'L'),
    ((21, 230, 41, 251), 'stick', 'R'),
    ((0, 251, 20, 272), 'stick', 'L'),
    ((21, 251, 41, 272), 'stick', 'L'),
    ((42, 251, 62, 272), 'stick', 'L'),
    ((63, 251, 83, 272), 'stick', 'R'),
    # Face buttons
    ((147, 231, 165, 249), 'square', None),    # X
    ((168, 231, 186, 249), 'triangle', None),  # Y
    ((189, 231, 207, 249), 'cross', None),     # A
    ((210, 231, 228, 249), 'circle', None),    # B
]


# Shadow pixels of an original glyph that fall outside its drawing box.
EXTRA_CLEAR = {(True, 107, 112): [(119, 112, 120, 124)]}


# ---------------------------------------------------------------- DXT5 encoding
def c565(c):
    r, g, b = (int(v) for v in c)
    return ((r * 31 + 127) // 255) << 11 | ((g * 63 + 127) // 255) << 5 | ((b * 31 + 127) // 255)


def e565(v):
    return np.array([((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31], np.int64)


def encode_alpha(a: np.ndarray) -> bytes:
    best = None
    lo, hi = int(a.min()), int(a.max())
    cands = [(hi, lo)]
    if lo > 0 or hi < 255:  # 6-value mode keeps exact 0 and 255
        nz = a[(a > 0) & (a < 255)]
        if nz.size:
            cands.append((int(nz.min()), int(nz.max())))
        else:
            cands.append((lo if lo not in (0, 255) else 1, hi if hi not in (0, 255) else 2))
    for a0, a1 in cands:
        if a0 > a1:
            pal = [a0, a1] + [(a0 * (7 - k) + a1 * k) // 7 for k in range(1, 7)]
        elif a0 == a1:
            pal = [a0] * 8; a0, a1 = a0, a1
        else:
            pal = [a0, a1] + [(a0 * (5 - k) + a1 * k) // 5 for k in range(1, 5)] + [0, 255]
        pal = np.array(pal)
        idx = np.abs(a[:, None] - pal[None, :]).argmin(1)
        err = int((np.abs(a - pal[idx]) ** 2).sum())
        if best is None or err < best[0]:
            best = (err, a0, a1, idx)
    _, a0, a1, idx = best
    bits = 0
    for k, i in enumerate(idx):
        bits |= int(i) << (3 * k)
    return bytes([a0, a1]) + bits.to_bytes(6, 'little')


def encode_color(rgb: np.ndarray, w: np.ndarray) -> bytes:
    if w.sum() == 0:
        w = np.ones_like(w)
    q = {c565(c) for c in rgb}
    uniq = sorted(q)
    # candidates: all pairs of the block's own quantised colours plus PCA extremes
    mean = (rgb * w[:, None]).sum(0) / w.sum()
    cov = ((rgb - mean) * w[:, None]).T @ (rgb - mean)
    axis = np.linalg.eigh(cov)[1][:, -1]
    proj = (rgb - mean) @ axis
    uniq += [c565(np.clip(rgb[proj.argmin()], 0, 255)), c565(np.clip(rgb[proj.argmax()], 0, 255))]
    uniq = sorted(set(uniq))
    best = None
    for i in range(len(uniq)):
        for j in range(i, len(uniq)):
            hi_, lo_ = max(uniq[i], uniq[j]), min(uniq[i], uniq[j])
            p0, p1 = e565(hi_), e565(lo_)
            pal = np.array([p0, p1, (2 * p0 + p1) // 3, (p0 + 2 * p1) // 3])
            d = ((rgb[:, None, :] - pal[None]) ** 2).sum(-1)
            idx = d.argmin(1)
            err = float((d[np.arange(16), idx] * w).sum())
            if best is None or err < best[0]:
                best = (err, hi_, lo_, idx)
    _, c0, c1, idx = best
    bits = 0
    for k, i in enumerate(idx):
        bits |= int(i) << (2 * k)
    return struct.pack('<HHI', c0, c1, bits)


def encode_block(px: np.ndarray) -> bytes:
    px = px.reshape(16, 4).astype(np.int64)
    a = px[:, 3]
    w = a / 255.0 + 0.02
    return encode_alpha(a) + encode_color(px[:, :3], w)


# ---------------------------------------------------------------- main
def process(src: Path, dst: Path, w: int, h: int, glyphs, small: bool, preview: Path) -> dict:
    raw = bytearray(src.read_bytes())
    assert raw[:4] == b'XPR0'
    header = struct.unpack_from('<I', raw, 8)[0]
    tex = bytes(raw[header:header + w * h])
    img = decode_dxt5(tex, w, h).copy()
    changed = np.zeros((h // 4, w // 4), bool)
    for (x0, y0, x1, y1), kind, label in glyphs:
        icon = make_icon(kind, x1 - x0, y1 - y0, label, small)
        img[y0:y1, x0:x1] = 0
        for cx0, cy0, cx1, cy1 in EXTRA_CLEAR.get((small, x0, y0), []):
            img[cy0:cy1, cx0:cx1] = 0
        img[y0:y1, x0:x1] = icon
        changed[y0 // 4:(y1 + 3) // 4, x0 // 4:(x1 + 3) // 4] = True
    blocks = 0
    for by, bx in zip(*np.nonzero(changed)):
        off = header + (by * (w // 4) + bx) * 16
        raw[off:off + 16] = encode_block(img[by * 4:by * 4 + 4, bx * 4:bx * 4 + 4])
        blocks += 1
    dst.write_bytes(raw)
    # verify by decoding what was written
    out = decode_dxt5(bytes(raw[header:header + w * h]), w, h)
    Image.fromarray(out).save(preview)
    return {'blocks': blocks, 'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw)}


if __name__ == '__main__':
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    dst.mkdir(parents=True, exist_ok=True)
    work = Path(__file__).parent
    print('small', process(src / 'small.xpr', dst / 'small.xpr', 128, 128, SMALL, True, work / 'new_small.png'))
    print('large', process(src / 'large.xpr', dst / 'large.xpr', 256, 512, LARGE, False, work / 'new_large.png'))
