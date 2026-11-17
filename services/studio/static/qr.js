/* Minimal QR code encoder: byte mode, error correction level M, versions 1 to 40, automatic mask.
   Written for the Studio from ISO/IEC 18004 (same structure as the widely used public-domain algorithm); no network,
   no library. Tested from Python by an independent decoder (services/studio/tests/test_studio_qr.py).
   Usable in the browser (window.StudioQR) and in Node (module.exports) for the tests. */
(function (root) {
  'use strict';
  var ECC_PER_BLOCK = [-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26, 26, 28, 28,
    28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28];
  var NUM_BLOCKS = [-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16, 17, 17, 18, 20, 21, 23, 25, 26,
    28, 29, 31, 33, 35, 37, 38, 40, 43, 45, 47, 49];
  var ECL_M_FORMAT = 0; // format bits for level M

  function rawModules(ver) {
    var r = (16 * ver + 128) * ver + 64;
    if (ver >= 2) {
      var n = Math.floor(ver / 7) + 2;
      r -= (25 * n - 10) * n - 55;
      if (ver >= 7) r -= 36;
    }
    return r;
  }
  function dataCodewords(ver) { return Math.floor(rawModules(ver) / 8) - ECC_PER_BLOCK[ver] * NUM_BLOCKS[ver]; }

  function gfMul(x, y) {
    var z = 0;
    for (var i = 7; i >= 0; i--) {
      z = (z << 1) ^ ((z >>> 7) * 0x11D);
      z ^= ((y >>> i) & 1) * x;
    }
    return z & 0xFF;
  }
  function rsDivisor(degree) {
    var r = [], i, j, rootv = 1;
    for (i = 0; i < degree - 1; i++) r.push(0);
    r.push(1);
    for (i = 0; i < degree; i++) {
      for (j = 0; j < r.length; j++) {
        r[j] = gfMul(r[j], rootv);
        if (j + 1 < r.length) r[j] ^= r[j + 1];
      }
      rootv = gfMul(rootv, 0x02);
    }
    return r;
  }
  function rsRemainder(data, div) {
    var r = div.map(function () { return 0; });
    data.forEach(function (b) {
      var f = b ^ r.shift();
      r.push(0);
      div.forEach(function (c, i) { r[i] ^= gfMul(c, f); });
    });
    return r;
  }

  function utf8(text) {
    var out = [], s = unescape(encodeURIComponent(text));
    for (var i = 0; i < s.length; i++) out.push(s.charCodeAt(i));
    return out;
  }

  function encode(text) {
    var bytes = utf8(String(text)), ver, ccBits, cap;
    for (ver = 1; ver <= 40; ver++) {
      ccBits = ver <= 9 ? 8 : 16;
      cap = dataCodewords(ver) * 8;
      if (4 + ccBits + bytes.length * 8 <= cap) break;
    }
    if (ver > 40) throw new RangeError('data too long');
    var bits = [];
    function put(val, len) { for (var i = len - 1; i >= 0; i--) bits.push((val >>> i) & 1); }
    put(4, 4); put(bytes.length, ccBits);
    bytes.forEach(function (b) { put(b, 8); });
    put(0, Math.min(4, cap - bits.length));
    put(0, (8 - bits.length % 8) % 8);
    var data = [], i;
    for (i = 0; i < bits.length; i += 8) {
      var v = 0;
      for (var k = 0; k < 8; k++) v = (v << 1) | bits[i + k];
      data.push(v);
    }
    for (var pad = 0xEC; data.length < cap / 8; pad ^= 0xEC ^ 0x11) data.push(pad);
    return build(ver, interleave(data, ver));
  }

  function interleave(data, ver) {
    var nb = NUM_BLOCKS[ver], ecc = ECC_PER_BLOCK[ver], raw = Math.floor(rawModules(ver) / 8);
    var nShort = nb - raw % nb, shortLen = Math.floor(raw / nb), div = rsDivisor(ecc), blocks = [], k = 0, i;
    for (i = 0; i < nb; i++) {
      var dat = data.slice(k, k + shortLen - ecc + (i < nShort ? 0 : 1));
      k += dat.length;
      var e = rsRemainder(dat, div);
      if (i < nShort) dat.push(0);
      blocks.push(dat.concat(e));
    }
    var out = [];
    for (i = 0; i < blocks[0].length; i++) {
      blocks.forEach(function (b, j) { if (i !== shortLen - ecc || j >= nShort) out.push(b[i]); });
    }
    return out;
  }

  function alignPositions(ver) {
    if (ver === 1) return [];
    var n = Math.floor(ver / 7) + 2, size = ver * 4 + 17;
    var step = Math.floor((ver * 8 + n * 3 + 5) / (n * 4 - 4)) * 2, r = [6];
    for (var p = size - 7; r.length < n; p -= step) r.splice(1, 0, p);
    return r;
  }

  function build(ver, codewords) {
    var size = ver * 4 + 17, m = [], fn = [], x, y, i;
    for (y = 0; y < size; y++) { m.push(new Array(size).fill(false)); fn.push(new Array(size).fill(false)); }
    function set(px, py, dark) { m[py][px] = dark; fn[py][px] = true; }
    for (i = 0; i < size; i++) { set(6, i, i % 2 === 0); set(i, 6, i % 2 === 0); }
    [[3, 3], [size - 4, 3], [3, size - 4]].forEach(function (c) {
      for (var dy = -4; dy <= 4; dy++) for (var dx = -4; dx <= 4; dx++) {
        var d = Math.max(Math.abs(dx), Math.abs(dy)), xx = c[0] + dx, yy = c[1] + dy;
        if (xx >= 0 && xx < size && yy >= 0 && yy < size) set(xx, yy, d !== 2 && d !== 4);
      }
    });
    var al = alignPositions(ver), na = al.length;
    for (i = 0; i < na; i++) for (var j = 0; j < na; j++) {
      if ((i === 0 && j === 0) || (i === 0 && j === na - 1) || (i === na - 1 && j === 0)) continue;
      for (var ay = -2; ay <= 2; ay++) for (var ax = -2; ax <= 2; ax++) set(al[i] + ax, al[j] + ay, Math.max(Math.abs(ax), Math.abs(ay)) !== 1);
    }
    function format(mask) {
      var d = (ECL_M_FORMAT << 3) | mask, rem = d;
      for (var q = 0; q < 10; q++) rem = (rem << 1) ^ ((rem >>> 9) * 0x537);
      var b = ((d << 10) | rem) ^ 0x5412, bit = function (n) { return ((b >>> n) & 1) !== 0; };
      for (q = 0; q <= 5; q++) set(8, q, bit(q));
      set(8, 7, bit(6)); set(8, 8, bit(7)); set(7, 8, bit(8));
      for (q = 9; q < 15; q++) set(14 - q, 8, bit(q));
      for (q = 0; q < 8; q++) set(size - 1 - q, 8, bit(q));
      for (q = 8; q < 15; q++) set(8, size - 15 + q, bit(q));
      set(8, size - 8, true);
    }
    format(0);
    if (ver >= 7) {
      var rem = ver;
      for (i = 0; i < 12; i++) rem = (rem << 1) ^ ((rem >>> 11) * 0x1F25);
      var vb = (ver << 12) | rem;
      for (i = 0; i < 18; i++) {
        var on = ((vb >>> i) & 1) !== 0, a = size - 11 + i % 3, b = Math.floor(i / 3);
        set(a, b, on); set(b, a, on);
      }
    }
    var n = 0;
    for (var right = size - 1; right >= 1; right -= 2) {
      if (right === 6) right = 5;
      for (var vert = 0; vert < size; vert++) for (var c = 0; c < 2; c++) {
        x = right - c;
        y = ((right + 1) & 2) === 0 ? size - 1 - vert : vert;
        if (!fn[y][x] && n < codewords.length * 8) {
          m[y][x] = ((codewords[n >>> 3] >>> (7 - (n & 7))) & 1) !== 0;
          n++;
        }
      }
    }
    function maskAt(mask, px, py) {
      switch (mask) {
        case 0: return (px + py) % 2 === 0;
        case 1: return py % 2 === 0;
        case 2: return px % 3 === 0;
        case 3: return (px + py) % 3 === 0;
        case 4: return (Math.floor(px / 3) + Math.floor(py / 2)) % 2 === 0;
        case 5: return (px * py) % 2 + (px * py) % 3 === 0;
        case 6: return ((px * py) % 2 + (px * py) % 3) % 2 === 0;
        default: return ((px + py) % 2 + (px * py) % 3) % 2 === 0;
      }
    }
    function applyMask(mask) {
      for (var py = 0; py < size; py++) for (var px = 0; px < size; px++) {
        if (!fn[py][px] && maskAt(mask, px, py)) m[py][px] = !m[py][px];
      }
    }
    var best = 0, bestScore = Infinity;
    for (var mk = 0; mk < 8; mk++) {
      applyMask(mk); format(mk);
      var s = penalty(m);
      if (s < bestScore) { bestScore = s; best = mk; }
      applyMask(mk);
    }
    applyMask(best); format(best);
    return { version: ver, size: size, mask: best, modules: m };
  }

  function penalty(m) {
    var size = m.length, score = 0, x, y, dark = 0;
    function lines(get) {
      for (var a = 0; a < size; a++) {
        var run = 1, line = [];
        for (var b = 0; b < size; b++) line.push(get(a, b));
        for (b = 1; b <= size; b++) {
          if (b < size && line[b] === line[b - 1]) { run++; continue; }
          if (run >= 5) score += 3 + (run - 5);
          run = 1;
        }
        for (b = 0; b + 11 <= size; b++) {
          var s = line.slice(b, b + 11).map(Number).join('');
          if (s === '10111010000' || s === '00001011101') score += 40;
        }
      }
    }
    lines(function (a, b) { return m[a][b]; });
    lines(function (a, b) { return m[b][a]; });
    for (y = 0; y + 1 < size; y++) for (x = 0; x + 1 < size; x++) {
      var c = m[y][x];
      if (c === m[y][x + 1] && c === m[y + 1][x] && c === m[y + 1][x + 1]) score += 3;
    }
    for (y = 0; y < size; y++) for (x = 0; x < size; x++) if (m[y][x]) dark++;
    var total = size * size;
    score += (Math.ceil(Math.abs(dark * 20 - total * 10) / total) - 1) * 10;
    return score;
  }

  /* SVG element (no markup strings): one light rect and one path of dark squares. */
  function toSvg(doc, qr, border) {
    var ns = 'http://www.w3.org/2000/svg', b = border === undefined ? 4 : border, dim = qr.size + b * 2, d = [];
    for (var y = 0; y < qr.size; y++) for (var x = 0; x < qr.size; x++) {
      if (qr.modules[y][x]) d.push('M' + (x + b) + ',' + (y + b) + 'h1v1h-1z');
    }
    var svg = doc.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 ' + dim + ' ' + dim);
    svg.setAttribute('shape-rendering', 'crispEdges');
    var bg = doc.createElementNS(ns, 'rect');
    bg.setAttribute('width', String(dim)); bg.setAttribute('height', String(dim)); bg.setAttribute('class', 'qr-light');
    var path = doc.createElementNS(ns, 'path');
    path.setAttribute('d', d.join('')); path.setAttribute('class', 'qr-dark');
    svg.appendChild(bg); svg.appendChild(path);
    return svg;
  }

  var api = { encode: encode, toSvg: toSvg };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.StudioQR = api;
})(typeof self !== 'undefined' ? self : this);
