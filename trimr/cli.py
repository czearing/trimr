"""Trimr command line. Run with no arguments for the guided menu (like VRAMr)."""
import argparse
import json
import os
import shutil
import sys
import time

from . import __version__
from .enable import enable
from .mo2 import Instance, find_instances
from .presets import ALL_TARGETS, PRESETS
from .rank import analyze
from .reduce import run as run_reduce, select
from . import report

OUT_MOD = "Trimr Output"


def find_exe():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    for p in (os.path.join(root, "trimr-reduce.exe"), os.path.join(root, "reducer", "build", "trimr-reduce.exe"),
              os.path.join(root, "reducer", "build", "Release", "trimr-reduce.exe")):
        if os.path.isfile(p):
            return p
    raise SystemExit("trimr-reduce.exe not found. Download the release zip or run build.bat.")


def _targets(s):
    if not s or s == "all":
        return set(ALL_TARGETS)
    t = {x.strip().lower() for x in s.split(",") if x.strip()}
    bad = t - set(ALL_TARGETS)
    if bad:
        raise SystemExit("Unknown target(s): %s. Choose from: %s" % (", ".join(sorted(bad)), ", ".join(ALL_TARGETS)))
    return t


def _csv(s):
    return {x.strip().lower() for x in s.split(",") if x.strip()} if s else None


def _prog(n, total, name):
    if n % 100 == 0:
        print("  reading plugins %d / %d" % (n, total), flush=True)


def cached_analyze(inst, exe, targets, progress=_prog):
    """analyze() with an on-disk cache keyed by the profile files, ignore list and targets (the plugin scan is slow)."""
    state = os.path.join(inst.path, "trimr")
    f = os.path.join(state, "analysis.json")
    sig = [os.path.getmtime(os.path.join(inst.profile_dir, n)) for n in ("modlist.txt", "plugins.txt", "loadorder.txt") if os.path.exists(os.path.join(inst.profile_dir, n))]
    key = dict(sig=sig, ignore=sorted(inst.ignore), targets=sorted(targets), exe=os.path.getmtime(exe), profile=inst.profile)
    if os.path.exists(f):
        try:
            c = json.load(open(f, encoding="utf-8"))
            if c["key"] == key:
                print("Using cached analysis (delete %s to refresh)." % f)
                return c["rows"], c["stats"]
        except Exception:
            pass
    rows, stats = analyze(inst, exe, targets, progress=progress)
    os.makedirs(state, exist_ok=True)
    json.dump(dict(key=key, rows=rows, stats=stats), open(f, "w", encoding="utf-8"))
    return rows, stats


def open_instance(a):
    path = a.instance
    if not path:
        found = find_instances()
        if not found:
            raise SystemExit("No Mod Organizer instance found. Pass --instance <folder that contains ModOrganizer.ini>.")
        if len(found) > 1:
            print("Several instances found:")
            for i, f in enumerate(found):
                print("  [%d] %s" % (i + 1, f))
            path = found[int(input("Pick one: ")) - 1]
        else:
            path = found[0]
    ignore = list(filter(None, (a.ignore or "").split(","))) + [OUT_MOD]
    return Instance(path, a.profile, ignore)


def cmd_analyze(a):
    inst = open_instance(a)
    exe = find_exe()
    rows, st = cached_analyze(inst, exe, _targets(a.targets))
    print("\n%s | profile %s | %d placed exterior references, %d distinct meshes, %d loose files" % (inst.game_name, inst.profile, st["refs"], st["unique_meshes"], st["loose"]))
    tot = sum(r["mass"] for r in rows) or 1
    by_cat, by_mod = {}, {}
    for r in rows:
        by_cat[r["cat"]] = by_cat.get(r["cat"], 0) + r["mass"]
        by_mod[r["mod"]] = by_mod.get(r["mod"], 0) + r["mass"]
    print("\nPlaced triangles (millions) by target:")
    for k, v in sorted(by_cat.items(), key=lambda kv: -kv[1]):
        print("  %-10s %7.1f M  (%2.0f%%)" % (k, v / 1e6, 100 * v / tot))
    print("\nHeaviest mods:")
    for k, v in sorted(by_mod.items(), key=lambda kv: -kv[1])[:12]:
        print("  %-48s %7.1f M  (%2.0f%%)" % (k[:48], v / 1e6, 100 * v / tot))
    print("\nHeaviest meshes:")
    for r in rows[:15]:
        print("  %7.1f M = %5d x %6d tris  %-9s %s" % (r["mass"] / 1e6, r["placed"], r["reducible"], r["cat"], os.path.basename(r["rel"])))
    return rows


def cmd_run(a):
    inst = open_instance(a)
    exe = find_exe()
    preset = PRESETS[a.preset]
    print("Preset %s: %s" % (a.preset, preset["blurb"]))
    rows, _ = cached_analyze(inst, exe, _targets(a.targets))
    jobs = select(rows, preset, a.max_meshes, _csv(a.only_mods), _csv(a.skip_mods))
    if not jobs:
        raise SystemExit("Nothing to reduce with these options.")
    out_dir = a.out or os.path.join(inst.mods_dir, OUT_MOD)
    state = os.path.join(inst.path, "trimr")
    if a.fresh:
        shutil.rmtree(out_dir, ignore_errors=True)
        shutil.rmtree(os.path.join(state, "previews"), ignore_errors=True)
        for n in ("results.jsonl", "report.md"):
            if os.path.exists(os.path.join(state, n)):
                os.remove(os.path.join(state, n))
    workers = a.workers or max(1, (os.cpu_count() or 4) - 2)
    results = run_reduce(inst, exe, a.preset, jobs, out_dir, state, workers)
    res = report.write(os.path.join(state, "report.md"), a.preset, OUT_MOD, results, {r["rel"]: r for r in rows})
    print("\nDone. %d meshes reduced, %d kept original." % (res["shipped"], res["kept"]))
    if res["tris_before"]:
        print("Triangles in those files: %d -> %d (%.0f%% fewer). Placed in the world: %.1f M -> %.1f M." % (
            res["tris_before"], res["tris_after"], 100 * (1 - res["tris_after"] / res["tris_before"]), res["world_before"] / 1e6, res["world_after"] / 1e6))
    print("Output mod: %s\nReport and previews: %s" % (out_dir, state))
    if a.enable and res["mods"]:
        above = enable(inst, OUT_MOD, res["mods"].keys())
        print("Enabled '%s' in profile %s (backup modlist.txt.before-trimr)." % (OUT_MOD, inst.profile))
    else:
        print("Next: in MO2 enable '%s' and drag it above the mods listed in the report." % OUT_MOD)


def cmd_undo(a):
    inst = open_instance(a)
    out_dir = os.path.join(inst.mods_dir, OUT_MOD)
    shutil.rmtree(out_dir, ignore_errors=True)
    shutil.rmtree(os.path.join(inst.path, "trimr"), ignore_errors=True)
    p = os.path.join(inst.profile_dir, "modlist.txt")
    t = open(p, encoding="utf-8", newline="").read()
    nl = "\r\n" if "\r\n" in t else "\n"
    open(p, "w", encoding="utf-8", newline="").write(nl.join(l for l in t.split(nl) if l not in ("+" + OUT_MOD, "-" + OUT_MOD)))
    print("Removed %s and its entry in the profile." % OUT_MOD)


def menu():
    print("Trimr %s  -  trim triangles, keep the look\n" % __version__)
    names = list(PRESETS)
    for i, n in enumerate(names):
        print("  [%d] %-12s %s" % (i + 1, n, PRESETS[n]["blurb"]))
    p = input("\nPreset [2]: ").strip() or "2"
    preset = names[int(p) - 1]
    print("\nWhat to trim: %s" % ", ".join(ALL_TARGETS))
    t = input("Targets, comma separated, or Enter for all: ").strip() or "all"
    ns = argparse.Namespace(instance=None, profile=None, ignore="", targets=t, preset=preset, max_meshes=None, only_mods=None, skip_mods=None,
                            out=None, fresh=False, workers=None, enable=False)
    cmd_run(ns)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="trimr", description="Trim triangles from heavy Skyrim meshes and keep the look. Output is a separate MO2 mod.")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd")

    def common(p):
        p.add_argument("--instance", help="MO2 instance folder (contains ModOrganizer.ini). Auto detected if omitted.")
        p.add_argument("--profile", help="MO2 profile (default: the selected one)")
        p.add_argument("--ignore", default="", help="comma separated mod names to treat as absent")
        p.add_argument("--targets", default="all", help="comma list of: %s" % ", ".join(ALL_TARGETS))
    pa = sub.add_parser("analyze", help="rank what costs the most. Changes nothing.")
    common(pa)
    pr = sub.add_parser("run", help="reduce meshes into the 'Trimr Output' mod")
    common(pr)
    pr.add_argument("--preset", default="balanced", choices=list(PRESETS))
    pr.add_argument("--max-meshes", type=int, help="stop after this many meshes")
    pr.add_argument("--only-mods", help="comma list: only touch meshes that come from these mods")
    pr.add_argument("--skip-mods", help="comma list: never touch meshes from these mods")
    pr.add_argument("--out", help="write the output mod here instead of <instance>\\mods\\%s" % OUT_MOD)
    pr.add_argument("--fresh", action="store_true", help="delete the previous output and start over")
    pr.add_argument("--workers", type=int)
    pr.add_argument("--enable", action="store_true", help="also add the mod to the profile (MO2 must be closed)")
    pu = sub.add_parser("undo", help="delete the output mod")
    common(pu)
    a = ap.parse_args(argv)
    if not a.cmd:
        return menu()
    {"analyze": cmd_analyze, "run": cmd_run, "undo": cmd_undo}[a.cmd](a)


if __name__ == "__main__":
    main()
