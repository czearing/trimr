"""Rank placed exterior meshes by how many triangles they put on screen (placed count x triangles)."""
import collections
import os
import subprocess
import tempfile

from .plugins import scan
from .presets import category_of

TYPES = ("STAT", "MSTT", "FLOR", "TREE", "ACTI", "CONT", "DOOR", "FURN")


def mesh_info(exe, paths):
    """Batch ask the reducer about files. Returns {path: (loadable, total_tris, reducible_tris, alpha_test, other_shapes)}."""
    out = {}
    if not paths:
        return out
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write("\n".join(paths))
        lst = f.name
    try:
        r = subprocess.run([exe, "info", lst], capture_output=True, text=True, encoding="utf-8", errors="replace")
    finally:
        os.remove(lst)
    for line in r.stdout.splitlines():
        p = line.split("\t")
        if len(p) == 7 and p[0] == "INFO":
            out[p[1]] = (p[2] == "1", int(p[3]), int(p[4]), p[5] == "1", int(p[6]))
    return out


def analyze(inst, exe, targets, min_tris=600, progress=None):
    """Returns a list of dicts sorted by mass (placed x reducible triangles), highest first."""
    records, refs = scan(inst, TYPES, progress)
    counts = collections.Counter(refs.values())
    by_rel = collections.defaultdict(lambda: dict(placed=0, edid=""))
    for base, n in counts.items():
        for t in TYPES:
            rec = records[t].get(base)
            if rec:
                modl, edid = rec
                if modl:
                    rel = "meshes\\" + modl.replace("/", "\\").lstrip("\\").lower()
                    e = by_rel[rel]
                    e["placed"] += n
                    e["edid"] = e["edid"] or edid
                break
    located = {}
    for rel in by_rel:
        mod, path = inst.find_file(rel)
        if path:
            located[rel] = (mod, path)
    ascii_map = {}
    for rel, (mod, path) in located.items():
        ascii_map[rel] = path
    info = mesh_info(exe, [p for p in ascii_map.values() if p.isascii()])
    rows = []
    for rel, (mod, path) in located.items():
        meta = info.get(path)
        if not meta or not meta[0]:
            continue
        _, total, reducible, alpha, other = meta
        if reducible < min_tris:
            continue
        cat = category_of(rel)
        if targets and cat not in targets:
            continue
        placed = by_rel[rel]["placed"]
        rows.append(dict(rel=rel, mod=mod, path=path, placed=placed, tris=total, reducible=reducible, alpha=alpha,
                         cat=cat, edid=by_rel[rel]["edid"], mass=placed * reducible))
    rows.sort(key=lambda r: -r["mass"])
    stats = dict(refs=len(refs), unique_meshes=len(by_rel), loose=len(located))
    return rows, stats
