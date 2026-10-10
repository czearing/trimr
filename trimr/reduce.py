"""Batch reduction with the safety gate. One worker process per CPU core; each mesh is tried boldest first and
only the first result that passes the preview check is shipped. Everything else keeps its original file."""
import concurrent.futures as cf
import json
import os
import shutil
import subprocess
import tempfile
import time

from . import gate
from .mo2 import Instance
from .presets import PRESETS

_W = {}


def _init(inst_path, profile, ignore, exe, preset, out_dir, sheets_dir):
    _W.update(inst=Instance(inst_path, profile, ignore), exe=exe, preset=PRESETS[preset], out=out_dir, sheets=sheets_dir)
    _W["texs"] = gate.TextureCache(_W["inst"])


def _tris(stdout):
    for line in stdout.splitlines():
        if line.startswith("TOTAL"):
            a = line.split()
            return int(a[1]), int(a[3])
    return None


def _work(job, sheet):
    exe, preset, out_dir = _W["exe"], _W["preset"], _W["out"]
    rel, src = job["rel"], job["path"]
    kind = "foliage" if job["alpha"] else "solid"
    wd = tempfile.mkdtemp(prefix="trimr_")
    tries, best = [], None
    try:
        ob = os.path.join(wd, "orig.bin")
        if subprocess.run([exe, "dump", src, ob], capture_output=True).returncode != 0:
            return dict(rel=rel, mod=job["mod"], status="unreadable")
        for ratio, err in preset["attempts"]:
            red = os.path.join(wd, "red.nif")
            p = subprocess.run([exe, "reduce", src, red, str(ratio), str(err), "300"], capture_output=True, text=True)
            tc = _tris(p.stdout) if p.returncode == 0 else None
            if not tc or tc[1] >= tc[0] * 0.92:
                tries.append(dict(ratio=ratio, status="no_gain"))
                continue
            rb = os.path.join(wd, "red.bin")
            if subprocess.run([exe, "dump", red, rb], capture_output=True).returncode != 0:
                tries.append(dict(ratio=ratio, status="reload_fail"))
                continue
            png = os.path.join(_W["sheets"], rel.replace("\\", "_") + ".png") if sheet else None
            c = gate.compare(ob, rb, _W["texs"], png)
            ok = gate.passes(kind, c, preset)
            tries.append(dict(ratio=ratio, ok=ok, **{k: round(v, 4) for k, v in c.items()}))
            if ok:
                dst = os.path.join(out_dir, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(red, dst)
                best = dict(before=tc[0], after=tc[1], ratio=ratio)
                break
    finally:
        shutil.rmtree(wd, ignore_errors=True)
    return dict(rel=rel, mod=job["mod"], kind=kind, placed=job["placed"], status="shipped" if best else "kept_original", result=best, tries=tries)


def select(rows, preset, max_meshes=None, mods=None, skip_mods=None):
    keep = []
    for r in rows:
        if mods and r["mod"].lower() not in mods:
            continue
        if skip_mods and r["mod"].lower() in skip_mods:
            continue
        keep.append(r)
    total = sum(r["mass"] for r in keep) or 1
    out, cum = [], 0
    for r in keep:
        out.append(r)
        cum += r["mass"]
        if cum >= preset["mass"] * total or (max_meshes and len(out) >= max_meshes):
            break
    return out


def run(inst, exe, preset_name, jobs, out_dir, state_dir, workers, progress=print):
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(state_dir, exist_ok=True)
    sheets = os.path.join(state_dir, "previews")
    log = os.path.join(state_dir, "results.jsonl")
    done = set()
    if os.path.exists(log):
        for line in open(log, encoding="utf-8"):
            try:
                done.add(json.loads(line)["rel"])
            except Exception:
                pass
    todo = [j for j in jobs if j["rel"] not in done]
    progress("%d meshes selected, %d already done, %d to do, %d workers" % (len(jobs), len(done), len(todo), workers))
    t0 = time.time()
    n = 0
    with cf.ProcessPoolExecutor(workers, initializer=_init, initargs=(inst.path, inst.profile, sorted(inst.ignore), exe, preset_name, out_dir, sheets)) as ex, \
            open(log, "a", encoding="utf-8") as lf:
        futs = {ex.submit(_work, j, i < 40): j for i, j in enumerate(todo)}
        for fu in cf.as_completed(futs):
            try:
                r = fu.result()
            except Exception as e:  # keep going, never ship a half checked file
                r = dict(rel=futs[fu]["rel"], mod=futs[fu]["mod"], status="error", error=str(e))
            lf.write(json.dumps(r) + "\n")
            lf.flush()
            n += 1
            if n % 10 == 0 or n == len(todo):
                progress("  %d / %d  (%.0fs)" % (n, len(todo), time.time() - t0))
    return [json.loads(l) for l in open(log, encoding="utf-8")]
