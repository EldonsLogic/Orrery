"""Self-contained QR Code matrix & SVG generator for bilingual tax invoices.

Uses `pyqrcode` (installed in the Frappe bench) or `segno` / `qrcode` when available,
with a clean pure-Python ISO/IEC 18004 Byte-mode QR encoder fallback (Versions 1..18,
EC level M) so unit tests and minimal environments still emit valid, scannable QR SVGs.
"""

from __future__ import annotations

import html
from typing import Iterable

# (ec_codewords_per_block, g1_blocks, g1_data_cw, g2_blocks, g2_data_cw) for EC level 'M'
_EC_M_TABLE: dict[int, tuple[int, int, int, int, int]] = {
    1: (10, 1, 16, 0, 0),
    2: (16, 1, 28, 0, 0),
    3: (26, 1, 44, 0, 0),
    4: (18, 2, 32, 0, 0),
    5: (24, 2, 43, 0, 0),
    6: (16, 4, 27, 0, 0),
    7: (18, 4, 31, 0, 0),
    8: (22, 2, 38, 2, 39),
    9: (22, 3, 36, 2, 37),
    10: (26, 4, 43, 1, 44),
    11: (30, 1, 50, 4, 51),
    12: (22, 6, 36, 2, 37),
    13: (22, 8, 37, 1, 38),
    14: (24, 4, 40, 5, 41),
    15: (24, 5, 41, 5, 42),
    16: (28, 7, 45, 3, 46),
    17: (28, 10, 46, 1, 47),
    18: (26, 9, 43, 4, 44),
}

_ALIGNMENT_CENTERS: dict[int, tuple[int, ...]] = {
    1: (),
    2: (6, 18),
    3: (6, 22),
    4: (6, 26),
    5: (6, 30),
    6: (6, 34),
    7: (6, 22, 38),
    8: (6, 24, 42),
    9: (6, 26, 46),
    10: (6, 28, 50),
    11: (6, 30, 54),
    12: (6, 32, 58),
    13: (6, 34, 62),
    14: (6, 26, 46, 66),
    15: (6, 26, 48, 70),
    16: (6, 26, 50, 74),
    17: (6, 30, 54, 78),
    18: (6, 30, 56, 82),
}

# Precomputed GF(256) log/antilog tables with primitive polynomial 0x11d (ISO/IEC 18004)
_GF_EXP = [0] * 512
_GF_LOG = [0] * 256
_x = 1
for _i in range(255):
    _GF_EXP[_i] = _x
    _GF_LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _GF_EXP[_i] = _GF_EXP[_i - 255]


def _gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _GF_EXP[_GF_LOG[a] + _GF_LOG[b]]


def _rs_generator_poly(degree: int) -> list[int]:
    poly = [1]
    for i in range(degree):
        root = _GF_EXP[i]
        nxt = [0] * (len(poly) + 1)
        for j, coef in enumerate(poly):
            nxt[j] ^= coef
            nxt[j + 1] ^= _gf_mul(coef, root)
        poly = nxt
    return poly


def _rs_remainder(data: list[int], ec_count: int) -> list[int]:
    gen = _rs_generator_poly(ec_count)
    res = list(data) + [0] * ec_count
    for i in range(len(data)):
        factor = res[i]
        if factor != 0:
            for j in range(1, len(gen)):
                res[i + j] ^= _gf_mul(gen[j], factor)
    return res[len(data) :]


def _format_bits_m(mask: int) -> int:
    # EC level M = 00 -> 5-bit data = (0b00 << 3) | mask
    data = mask & 0x07
    rem = data << 10
    gen = 0b10100110111
    for shift in range(4, -1, -1):
        if rem & (1 << (shift + 10)):
            rem ^= gen << shift
    return ((data << 10) | rem) ^ 0b101010000010010


def _version_bits(version: int) -> int:
    rem = version << 12
    gen = 0b1111100100101
    for shift in range(5, -1, -1):
        if rem & (1 << (shift + 12)):
            rem ^= gen << shift
    return (version << 12) | rem


def _encode_qr_matrix_pure_python(payload: str) -> list[list[bool]]:
    raw = payload.encode("utf-8")
    selected_version = None
    for ver in range(1, 19):
        _, g1_b, g1_d, g2_b, g2_d = _EC_M_TABLE[ver]
        total_data_cw = g1_b * g1_d + g2_b * g2_d
        char_count_bits = 8 if ver <= 9 else 16
        # Byte mode indicator (4 bits) + char_count_bits + payload bits
        needed_bits = 4 + char_count_bits + 8 * len(raw)
        if needed_bits <= total_data_cw * 8:
            selected_version = ver
            break
    if selected_version is None:
        raise ValueError(f"QR payload too large for pure-Python encoder ({len(raw)} bytes)")

    ver = selected_version
    ec_cw, g1_b, g1_d, g2_b, g2_d = _EC_M_TABLE[ver]
    total_data_cw = g1_b * g1_d + g2_b * g2_d
    char_count_bits = 8 if ver <= 9 else 16

    bits: list[int] = []

    def push_bits(val: int, width: int) -> None:
        for shift in range(width - 1, -1, -1):
            bits.append((val >> shift) & 1)

    push_bits(0b0100, 4)  # Byte mode
    push_bits(len(raw), char_count_bits)
    for byte in raw:
        push_bits(byte, 8)

    cap_bits = total_data_cw * 8
    term_len = min(4, cap_bits - len(bits))
    bits.extend([0] * term_len)
    while len(bits) % 8 != 0:
        bits.append(0)

    pad_bytes = (0xEC, 0x11)
    pad_idx = 0
    while len(bits) < cap_bits:
        push_bits(pad_bytes[pad_idx % 2], 8)
        pad_idx += 1

    data_cw = [0] * total_data_cw
    for idx in range(total_data_cw):
        b = 0
        for j in range(8):
            b = (b << 1) | bits[idx * 8 + j]
        data_cw[idx] = b

    # Split into RS blocks
    data_blocks: list[list[int]] = []
    ec_blocks: list[list[int]] = []
    offset = 0
    for count, size in ((g1_b, g1_d), (g2_b, g2_d)):
        for _ in range(count):
            blk = data_cw[offset : offset + size]
            offset += size
            data_blocks.append(blk)
            ec_blocks.append(_rs_remainder(blk, ec_cw))

    # Interleave data then EC codewords
    interleaved: list[int] = []
    max_data_len = max(len(b) for b in data_blocks)
    for i in range(max_data_len):
        for blk in data_blocks:
            if i < len(blk):
                interleaved.append(blk[i])
    for i in range(ec_cw):
        for blk in ec_blocks:
            interleaved.append(blk[i])

    # Convert to bit stream (+ remainder zero bits; Versions 1..18 need at most 7)
    stream: list[int] = []
    for cw in interleaved:
        for shift in range(7, -1, -1):
            stream.append((cw >> shift) & 1)
    stream.extend([0] * 7)

    dim = 17 + 4 * ver
    grid: list[list[bool]] = [[False] * dim for _ in range(dim)]
    is_func: list[list[bool]] = [[False] * dim for _ in range(dim)]

    def set_func(r: int, c: int, val: bool) -> None:
        grid[r][c] = val
        is_func[r][c] = True

    def draw_finder(top: int, left: int) -> None:
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                r, c = top + dr, left + dc
                if 0 <= r < dim and 0 <= c < dim:
                    in_outer = 0 <= dr <= 6 and 0 <= dc <= 6
                    on_border = dr in (0, 6) or dc in (0, 6)
                    in_inner = 2 <= dr <= 4 and 2 <= dc <= 4
                    set_func(r, c, in_outer and (on_border or in_inner))

    draw_finder(0, 0)
    draw_finder(0, dim - 7)
    draw_finder(dim - 7, 0)

    # Alignment patterns (skip only the three finder corners; may overlap timing row/col 6)
    centers = _ALIGNMENT_CENTERS[ver]
    for cy in centers:
        for cx in centers:
            if (cy < 9 and cx < 9) or (cy < 9 and cx >= dim - 9) or (cy >= dim - 9 and cx < 9):
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    val = abs(dr) == 2 or abs(dc) == 2 or (dr == 0 and dc == 0)
                    set_func(cy + dr, cx + dc, val)

    # Timing patterns
    for i in range(8, dim - 8):
        val = i % 2 == 0
        set_func(6, i, val)
        set_func(i, 6, val)

    # Reserve format info + dark module
    for i in range(9):
        if i != 6:
            set_func(8, i, False)
            set_func(i, 8, False)
    for i in range(8):
        set_func(8, dim - 1 - i, False)
    for i in range(7):
        set_func(dim - 1 - i, 8, False)
    set_func(dim - 8, 8, True)

    # Version info (>= 7)
    if ver >= 7:
        vbits = _version_bits(ver)
        for i in range(18):
            bit = bool((vbits >> i) & 1)
            a, b = dim - 11 + (i % 3), i // 3
            set_func(a, b, bit)
            set_func(b, a, bit)

    # Place data bits in zig-zag columns
    bit_idx = 0
    col = dim - 1
    upward = True
    while col > 0:
        if col == 6:
            col -= 1
        rows = range(dim - 1, -1, -1) if upward else range(dim)
        for row in rows:
            for c in (col, col - 1):
                if not is_func[row][c]:
                    grid[row][c] = bool(stream[bit_idx]) if bit_idx < len(stream) else False
                    bit_idx += 1
        upward = not upward
        col -= 2

    def mask_cond(mask: int, r: int, c: int) -> bool:
        if mask == 0:
            return (r + c) % 2 == 0
        if mask == 1:
            return r % 2 == 0
        if mask == 2:
            return c % 3 == 0
        if mask == 3:
            return (r + c) % 3 == 0
        if mask == 4:
            return (r // 2 + c // 3) % 2 == 0
        if mask == 5:
            return ((r * c) % 2) + ((r * c) % 3) == 0
        if mask == 6:
            return (((r * c) % 2) + ((r * c) % 3)) % 2 == 0
        return (((r + c) % 2) + ((r * c) % 3)) % 2 == 0

    def apply_format(g: list[list[bool]], mask: int) -> None:
        fb = _format_bits_m(mask)
        # Copy 1 around top-left finder: MSB (bit 14) at (8, 0) -> LSB (bit 0) at (0, 8)
        for i in range(6):
            g[8][i] = bool((fb >> (14 - i)) & 1)
        g[8][7] = bool((fb >> 8) & 1)
        g[8][8] = bool((fb >> 7) & 1)
        g[7][8] = bool((fb >> 6) & 1)
        for i in range(6):
            g[5 - i][8] = bool((fb >> (5 - i)) & 1)
        # Copy 2: bits 14..8 along bottom-left vertical, bits 7..0 along top-right horizontal
        for i in range(7):
            g[dim - 1 - i][8] = bool((fb >> (14 - i)) & 1)
        for i in range(8):
            g[8][dim - 8 + i] = bool((fb >> (7 - i)) & 1)

    def penalty_score(g: list[list[bool]]) -> int:
        score = 0
        # Rule 1: 5+ consecutive same-color modules
        for r in range(dim):
            run = 1
            for c in range(1, dim):
                if g[r][c] == g[r][c - 1]:
                    run += 1
                else:
                    if run >= 5:
                        score += run - 2
                    run = 1
            if run >= 5:
                score += run - 2
        for c in range(dim):
            run = 1
            for r in range(1, dim):
                if g[r][c] == g[r - 1][c]:
                    run += 1
                else:
                    if run >= 5:
                        score += run - 2
                    run = 1
            if run >= 5:
                score += run - 2
        # Rule 2: 2x2 blocks
        for r in range(dim - 1):
            for c in range(dim - 1):
                v = g[r][c]
                if g[r][c + 1] == v and g[r + 1][c] == v and g[r + 1][c + 1] == v:
                    score += 3
        # Rule 3: finder-like 1:1:3:1:1 patterns
        pat1 = (True, False, True, True, True, False, True, False, False, False, False)
        pat2 = (False, False, False, False, True, False, True, True, True, False, True)
        for r in range(dim):
            for c in range(dim - 10):
                seg = tuple(g[r][c : c + 11])
                if seg == pat1 or seg == pat2:
                    score += 40
        for c in range(dim):
            for r in range(dim - 10):
                seg = tuple(g[r + k][c] for k in range(11))
                if seg == pat1 or seg == pat2:
                    score += 40
        # Rule 4: dark ratio balance
        dark = sum(1 for r in range(dim) for c in range(dim) if g[r][c])
        pct = (dark * 100) // (dim * dim)
        prev5 = abs(pct - (pct % 5) - 50) // 5
        next5 = abs(pct + (5 - (pct % 5)) - 50) // 5
        score += min(prev5, next5) * 10
        return score

    best_grid = None
    best_score = 10**9
    for mask in range(8):
        cand = [
            [
                (not grid[r][c] if (not is_func[r][c] and mask_cond(mask, r, c)) else grid[r][c])
                for c in range(dim)
            ]
            for r in range(dim)
        ]
        apply_format(cand, mask)
        s = penalty_score(cand)
        if s < best_score:
            best_score = s
            best_grid = cand

    assert best_grid is not None
    return best_grid


def build_qr_matrix(payload: str) -> list[list[bool]]:
    """Build a boolean QR module matrix (True=dark) using pyqrcode/segno/qrcode or stdlib fallback."""
    if not payload:
        raise ValueError("QR payload cannot be empty")

    try:
        import pyqrcode  # type: ignore[import-not-found]

        qr = pyqrcode.create(payload, error="M")
        return [[bool(cell) for cell in row] for row in qr.code]
    except ImportError:
        pass

    try:
        import segno  # type: ignore[import-not-found]

        qr = segno.make(payload, error="m")
        return [[bool(cell) for cell in row] for row in qr.matrix]
    except ImportError:
        pass

    try:
        import qrcode  # type: ignore[import-not-found]

        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=0)
        qr.add_data(payload)
        qr.make(fit=True)
        return [[bool(cell) for cell in row] for row in qr.get_matrix()]
    except ImportError:
        pass

    return _encode_qr_matrix_pure_python(payload)


def _matrix_to_svg_path(matrix: Iterable[Iterable[bool]], quiet_modules: int) -> tuple[int, str]:
    rows = [list(r) for r in matrix]
    if not rows:
        raise ValueError("QR matrix cannot be empty")
    n = len(rows)
    total = n + 2 * quiet_modules
    parts: list[str] = []
    for r_idx, row in enumerate(rows):
        y = r_idx + quiet_modules
        c_idx = 0
        while c_idx < len(row):
            if row[c_idx]:
                start = c_idx
                while c_idx < len(row) and row[c_idx]:
                    c_idx += 1
                width = c_idx - start
                x = start + quiet_modules
                parts.append(f"M{x},{y}h{width}v1h-{width}z")
            else:
                c_idx += 1
    return total, "".join(parts)


def render_qr_svg(
    payload: str,
    *,
    size_mm: float = 32.0,
    quiet_modules: int = 4,
    label: str = "ZATCA Phase 1 QR Code",
    tlv_attribute: str | None = None,
) -> str:
    """Render a crisp, high-contrast black-on-white SVG QR code with a mandatory quiet zone."""
    if quiet_modules < 4:
        raise ValueError("QR quiet zone must be at least 4 modules")
    matrix = build_qr_matrix(payload)
    total, path_d = _matrix_to_svg_path(matrix, quiet_modules)
    escaped_label = html.escape(label, quote=True)
    tlv_val = html.escape(tlv_attribute if tlv_attribute is not None else payload, quote=True)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {total} {total}" '
        f'width="{size_mm:.1f}mm" height="{size_mm:.1f}mm" '
        f'shape-rendering="crispEdges" role="img" aria-label="{escaped_label}" '
        f'data-zatca-tlv="{tlv_val}">'
        f'<rect width="{total}" height="{total}" fill="#ffffff"/>'
        f'<path d="{path_d}" fill="#000000"/>'
        f"</svg>"
    )
