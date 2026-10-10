"""The safety check. Renders the original and the reduced mesh (textured, alpha tested, orthographic, 8 views) and scores them.
It checks SHAPE, COVERAGE, SURFACE DEPTH and TEXTURE PLACEMENT. It is not a game render: no lighting, shaders or wind."""
import math
import os
import struct

import numpy as np
from PIL import Image

VIEWS = [(0, 0), (90, 0), (180, 0), (270, 0), (45, 35), (135, 35), (225, 35), (0, 89)]


def read_bin(p):
    d = open(p, "rb").read()
    i = 0
    out = []
    while i < len(d):
        nv, nt, pl, sk = struct.unpack_from("<iiii", d, i)
        i += 16
        tex = d[i:i + pl].decode("latin1")
        i += pl
        pos = np.frombuffer(d, "<f4", nv * 3, i).reshape(nv, 3)
        i += nv * 12
        uv = np.frombuffer(d, "<f4", nv * 2, i).reshape(nv, 2)
        i += nv * 8
        i += nv * 4  # vertex colours (unused here)
        tri = np.frombuffer(d, "<u2", nt * 3, i).reshape(nt, 3)
        i += nt * 6
        out.append(dict(tex=tex, pos=pos, uv=uv, tri=tri, skinned=sk))
    return out


class TextureCache:
    def __init__(self, inst, maxdim=512):
        self.inst, self.maxdim, self.c = inst, maxdim, {}

    def get(self, path):
        if not path:
            return None
        k = path.lower().replace("/", "\\").lstrip("\\")
        if not k.startswith("textures"):
            k = "textures\\" + k
        if k in self.c:
            return self.c[k]
        arr = None
        _, p = self.inst.find_file(k)
        if p:
            try:
                im = Image.open(p).convert("RGBA")
                w, h = im.size
                if max(w, h) > self.maxdim:
                    im = im.resize((max(1, w * self.maxdim // max(w, h)), max(1, h * self.maxdim // max(w, h))), Image.BILINEAR)
                arr = np.asarray(im)
            except Exception:
                arr = None
        self.c[k] = arr
        return arr


def _basis(az, el):
    az, el = math.radians(az), math.radians(el)
    d = np.array([math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)])
    r = np.cross(np.array([0, 0, 1.0]), d)
    if np.linalg.norm(r) < 1e-6:
        r = np.array([1.0, 0, 0])
    r /= np.linalg.norm(r)
    return r, np.cross(d, r), d


def _render(shapes, view, bounds, texs, R):
    r, u, d = _basis(*view)
    x0, x1, y0, y1 = bounds
    img = np.zeros((R, R, 3), np.float32)
    mask = np.zeros((R, R), bool)
    zb = np.full((R, R), -1e9, np.float32)
    sc = (R - 4) / max(x1 - x0, y1 - y0, 1e-6)
    for s in shapes:
        tex = texs.get(s["tex"])
        P = s["pos"].astype(np.float64)
        X = (P @ r - x0) * sc + 2
        Y = (R - 3) - ((P @ u - y0) * sc)
        Z = P @ d
        uv = s["uv"]
        th, tw = (tex.shape[0], tex.shape[1]) if tex is not None else (1, 1)
        for a, b, c in s["tri"]:
            xs = (X[a], X[b], X[c])
            ys = (Y[a], Y[b], Y[c])
            xmin = max(int(math.floor(min(xs))), 0)
            xmax = min(int(math.ceil(max(xs))), R - 1)
            ymin = max(int(math.floor(min(ys))), 0)
            ymax = min(int(math.ceil(max(ys))), R - 1)
            if xmin > xmax or ymin > ymax:
                continue
            den = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
            if abs(den) < 1e-9:
                continue
            gx, gy = np.meshgrid(np.arange(xmin, xmax + 1) + 0.5, np.arange(ymin, ymax + 1) + 0.5)
            l0 = ((ys[1] - ys[2]) * (gx - xs[2]) + (xs[2] - xs[1]) * (gy - ys[2])) / den
            l1 = ((ys[2] - ys[0]) * (gx - xs[2]) + (xs[0] - xs[2]) * (gy - ys[2])) / den
            l2 = 1 - l0 - l1
            inside = (l0 >= -1e-4) & (l1 >= -1e-4) & (l2 >= -1e-4)
            if not inside.any():
                continue
            z = l0 * Z[a] + l1 * Z[b] + l2 * Z[c]
            if tex is not None:
                tu = (l0 * uv[a, 0] + l1 * uv[b, 0] + l2 * uv[c, 0]) % 1.0
                tv = (l0 * uv[a, 1] + l1 * uv[b, 1] + l2 * uv[c, 1]) % 1.0
                t = tex[np.clip((tv * th).astype(int), 0, th - 1), np.clip((tu * tw).astype(int), 0, tw - 1)]
                ok = inside & (t[..., 3] >= 115)
                rgb = t[..., :3].astype(np.float32)
            else:
                ok = inside
                rgb = np.full(inside.shape + (3,), 128, np.float32)
            sl = (slice(ymin, ymax + 1), slice(xmin, xmax + 1))
            upd = ok & (z > zb[sl])
            zb[sl][upd] = z[upd]
            mask[sl][upd] = True
            img[sl][upd] = rgb[upd]
    return mask, img, zb


def _dilate(m, k=2):
    o = m.copy()
    for dy in range(-k, k + 1):
        for dx in range(-k, k + 1):
            o |= np.roll(np.roll(m, dy, 0), dx, 1)
    return o


def _blocks(m, b=8):
    n = m.shape[0] // b * b
    return m[:n, :n].reshape(n // b, b, n // b, b)


def _bcolor(img, m, b=8):
    n = m.shape[0] // b * b
    mm = _blocks(m, b)
    im = img[:n, :n].reshape(n // b, b, n // b, b, 3)
    cnt = mm.sum((1, 3))
    return cnt, (im * mm[..., None]).sum((1, 3)) / np.maximum(cnt, 1)[..., None]


def compare(orig_bin, red_bin, texs, out_png=None, R=256):
    """texs: a TextureCache (reuse one per process, it keeps decoded textures)."""
    A, B = read_bin(orig_bin), read_bin(red_bin)
    allp = np.concatenate([s["pos"] for s in A]).astype(np.float64)
    diag = float(np.linalg.norm(allp.max(0) - allp.min(0))) or 1.0
    res, tiles = [], []
    for v in VIEWS:
        r, u, _ = _basis(*v)
        xs, ys = allp @ r, allp @ u
        bounds = (xs.min(), xs.max(), ys.min(), ys.max())
        ma, ia, za = _render(A, v, bounds, texs, R)
        mb, ib, zb = _render(B, v, bounds, texs, R)
        da, db = _dilate(ma), _dilate(mb)
        tol = float(((da & mb).sum() + (db & ma).sum()) / max(1, ma.sum() + mb.sum()))
        cov = float(mb.sum() / ma.sum()) if ma.sum() else 1.0
        qa, qb = _blocks(ma).mean((1, 3)), _blocks(mb).mean((1, 3))
        sel = qa > 0.05
        drms = float(np.sqrt(((qa - qb) ** 2)[sel].mean())) if sel.any() else 0.0
        ca, cla = _bcolor(ia, ma)
        cb, clb = _bcolor(ib, mb)
        bb = (ca >= 8) & (cb >= 8)
        bdiff = float(np.abs(cla - clb)[bb].mean() / 255.0) if bb.any() else 0.0
        both = ma & mb
        dz = np.abs(za - zb)[both] / diag if both.any() else np.zeros(1)
        res.append(dict(tol=tol, cov=cov, drms=drms, bdiff=bdiff, dzm=float(dz.mean()), dzp=float(np.percentile(dz, 99))))
        if out_png and v in ((0, 0), (90, 0), (45, 35), (0, 89)):
            diff = np.zeros((R, R, 3), np.float32)
            diff[..., 0] = (ma & ~mb) * 255
            diff[..., 1] = (mb & ~ma) * 255
            diff[..., 2] = both * 60
            tiles.append(np.concatenate([ia, ib, diff], axis=1))
    if out_png and tiles:
        os.makedirs(os.path.dirname(out_png), exist_ok=True)
        Image.fromarray(np.clip(np.concatenate(tiles, axis=0), 0, 255).astype(np.uint8)).save(out_png)
    return dict(tol=min(r["tol"] for r in res), cov=min(r["cov"] for r in res), drms=max(r["drms"] for r in res),
                bdiff=max(r["bdiff"] for r in res), dzm=max(r["dzm"] for r in res), dzp=max(r["dzp"] for r in res))


def passes(kind, c, preset):
    """kind: 'solid' or 'foliage'. preset: an entry from presets.PRESETS."""
    g = preset[kind]
    if c["tol"] < g["tol"] or c["cov"] < g["cov"] or c["bdiff"] > preset["bdiff"]:
        return False
    if kind == "foliage":
        return c["drms"] <= g["drms"]
    return c["dzp"] <= g["dzp"] and c["dzm"] <= g["dzm"]
