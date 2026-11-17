"""The client-side QR encoder (static/qr.js), checked by an independent decoder written here from the standard: function
patterns, format information (BCH), unmasking, block de-interleaving, Reed-Solomon syndromes and the byte-mode payload.
Runs the encoder with Node; skipped (with the reason) only when Node is not installed."""
import base64
import json
import shutil
import subprocess

import pytest

from studio_testlib import STATIC

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is needed to run static/qr.js")

# Error correction level M, ISO/IEC 18004 table 9: version -> (ecc per block, [(block count, data codewords)]).
BLOCKS_M = {1: (10, [(1, 16)]), 2: (16, [(1, 28)]), 3: (26, [(1, 44)]), 4: (18, [(2, 32)]), 5: (24, [(2, 43)]),
            6: (16, [(4, 27)]), 7: (18, [(4, 31)]), 8: (22, [(2, 38), (2, 39)]), 9: (22, [(3, 36), (2, 37)]),
            10: (26, [(4, 43), (1, 44)])}
# Annex E: alignment pattern centre coordinates.
ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42],
         9: [6, 26, 46], 10: [6, 28, 50]}
MASKS = [lambda x, y: (x + y) % 2 == 0, lambda x, y: y % 2 == 0, lambda x, y: x % 3 == 0,
         lambda x, y: (x + y) % 3 == 0, lambda x, y: (x // 3 + y // 2) % 2 == 0,
         lambda x, y: (x * y) % 2 + (x * y) % 3 == 0, lambda x, y: ((x * y) % 2 + (x * y) % 3) % 2 == 0,
         lambda x, y: ((x + y) % 2 + (x * y) % 3) % 2 == 0]

EXP, LOG = [0] * 512, [0] * 256
_v = 1
for _i in range(255):
    EXP[_i], LOG[_v] = _v, _i
    _v <<= 1
    if _v & 0x100:
        _v ^= 0x11D
for _i in range(255, 512):
    EXP[_i] = EXP[_i - 255]


def encode(text: str) -> dict:
    script = "const q=require(process.argv[1]);process.stdout.write(JSON.stringify(q.encode(process.argv[2])));"
    out = subprocess.run([NODE, "-e", script, str(STATIC / "qr.js"), text], capture_output=True, text=True, timeout=30,
                         check=True)
    return json.loads(out.stdout)


def bch_format(data5: int) -> int:
    rem = data5 << 10
    for i in range(14, 9, -1):
        if rem >> i & 1:
            rem ^= 0x537 << (i - 10)
    return ((data5 << 10) | rem) ^ 0x5412


def function_mask(ver: int, size: int) -> list:
    f = [[False] * size for _ in range(size)]

    def box(x0, y0, w, h):
        for y in range(max(0, y0), min(size, y0 + h)):
            for x in range(max(0, x0), min(size, x0 + w)):
                f[y][x] = True
    box(0, 0, 9, 9)
    box(size - 8, 0, 8, 9)
    box(0, size - 8, 9, 8)
    box(6, 0, 1, size)
    box(0, 6, size, 1)
    al = ALIGN[ver]
    for cy in al:
        for cx in al:
            if (cx, cy) not in ((6, 6), (6, al[-1]), (al[-1], 6)):  # those three overlap the finders
                box(cx - 2, cy - 2, 5, 5)
    if ver >= 7:
        box(size - 11, 0, 3, 6)
        box(0, size - 11, 6, 3)
    return f


def decode(qr: dict) -> bytes:
    size, m = qr["size"], qr["modules"]
    ver = (size - 17) // 4
    assert size == ver * 4 + 17 and ver in BLOCKS_M
    finder = [[max(abs(dx), abs(dy)) not in (2, 4) for dx in range(-3, 4)] for dy in range(-3, 4)]
    for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):
        assert [[m[cy + dy][cx + dx] for dx in range(-3, 4)] for dy in range(-3, 4)] == finder
    assert all(m[6][i] == (i % 2 == 0) for i in range(8, size - 8))
    assert all(m[i][6] == (i % 2 == 0) for i in range(8, size - 8))
    assert m[size - 8][8] is True
    first = [m[i][8] for i in range(6)] + [m[7][8], m[8][8], m[8][7]] + [m[8][14 - i] for i in range(9, 15)]
    second = [m[8][size - 1 - i] for i in range(8)] + [m[size - 15 + i][8] for i in range(8, 15)]
    word = sum(int(b) << i for i, b in enumerate(first))
    assert word == sum(int(b) << i for i, b in enumerate(second))
    matches = [d for d in range(32) if bch_format(d) == word]
    assert len(matches) == 1, "format information is not a valid BCH codeword"
    ecl, mask = matches[0] >> 3, matches[0] & 7
    assert ecl == 0, "expected error correction level M"
    fmask = function_mask(ver, size)
    bits = []
    right = size - 1
    while right >= 1:
        if right == 6:
            right = 5
        for vert in range(size):
            for c in range(2):
                x = right - c
                y = size - 1 - vert if ((right + 1) & 2) == 0 else vert
                if not fmask[y][x]:
                    bits.append(m[y][x] ^ MASKS[mask](x, y))
        right -= 2
    ecc, groups = BLOCKS_M[ver]
    lens = [n for count, n in groups for _ in range(count)]
    total = sum(lens) + ecc * len(lens)
    assert len(bits) // 8 == total and len(bits) - total * 8 < 8
    cw = [int("".join("1" if b else "0" for b in bits[i * 8:i * 8 + 8]), 2) for i in range(total)]
    blocks, k = [[] for _ in lens], 0
    for i in range(max(lens)):
        for j, n in enumerate(lens):
            if i < n:
                blocks[j].append(cw[k])
                k += 1
    eccs = [[] for _ in lens]
    for i in range(ecc):
        for j in range(len(lens)):
            eccs[j].append(cw[k])
            k += 1
    data = []
    for blk, e in zip(blocks, eccs):
        poly = blk + e
        for r in range(ecc):
            s = 0
            for c in poly:
                s = (EXP[LOG[s] + r] if s else 0) ^ c
            assert s == 0, "Reed-Solomon syndrome is not zero"
        data += blk
    stream = "".join(f"{b:08b}" for b in data)
    assert stream[:4] == "0100", "expected byte mode"
    cc = 8 if ver <= 9 else 16
    n = int(stream[4:4 + cc], 2)
    start = 4 + cc
    payload = bytes(int(stream[start + 8 * i:start + 8 * i + 8], 2) for i in range(n))
    end = start + 8 * n
    term_end = min(len(stream), end + 4)
    assert set(stream[end:term_end]) <= {"0"}, "terminator"
    first_pad = -(-term_end // 8)
    assert set(stream[term_end:first_pad * 8]) <= {"0"}, "bit padding"
    assert all(b == (0xEC if i % 2 == 0 else 0x11) for i, b in enumerate(data[first_pad:])), "pad codewords"
    return payload


@pytest.mark.parametrize("text", ["A", "hello", "x" * 14, "y" * 40, "0123456789" * 7, "z" * 120, "q" * 200])
def test_qr_round_trips_through_an_independent_decoder(text):
    assert decode(encode(text)) == text.encode("utf-8")


def test_qr_round_trips_utf8_bytes():
    text = "الواحة 15.00"
    assert decode(encode(text)).decode("utf-8") == text


def test_qr_round_trips_a_real_phase1_payload(client):
    payload = client.get("/api/invoice?market=ksa&lang=ar")[1]["qr"]["payload"]
    qr = encode(payload)
    assert decode(qr) == payload.encode("ascii")
    base64.b64decode(payload, validate=True)


def test_qr_uses_a_version_large_enough_and_picks_a_mask():
    a, b = encode("short"), encode("w" * 150)
    assert a["version"] == 1 and b["version"] > a["version"]
    assert 0 <= a["mask"] <= 7 and 0 <= b["mask"] <= 7
