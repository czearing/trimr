"""Plain markdown report of what was changed, and the instructions to enable it."""
import collections
import os
import time


def write(path, preset_name, out_mod_name, results, rows_by_rel):
    sh = [r for r in results if r["status"] == "shipped"]
    kept = [r for r in results if r["status"] == "kept_original"]
    b = sum(r["result"]["before"] for r in sh)
    a = sum(r["result"]["after"] for r in sh)
    wb = sum(r["placed"] * r["result"]["before"] for r in sh)
    wa = sum(r["placed"] * r["result"]["after"] for r in sh)
    mods = collections.Counter(r["mod"] for r in sh)
    lines = ["# Trimr report", "", "Preset: **%s**   |   %s" % (preset_name, time.strftime("%Y-%m-%d %H:%M")), "",
             "- Meshes reduced: **%d** (kept original: %d)" % (len(sh), len(kept)),
             "- Triangles in reduced files: %d -> %d (%.0f%% fewer)" % (b, a, 100 * (1 - a / b) if b else 0),
             "- Triangles placed in the world by those meshes: %.1f M -> %.1f M (%.0f%% fewer)" % (wb / 1e6, wa / 1e6, 100 * (1 - wa / wb) if wb else 0), "",
             "Enable **%s** in MO2 and drag it **above** these mods (it must win their file conflicts):" % out_mod_name, ""]
    for m, n in mods.most_common():
        lines.append("- %s (%d meshes)" % (m, n))
    lines += ["", "To undo: disable or delete **%s**. Original files are never modified." % out_mod_name, "", "## Largest wins", "",
              "| Mesh | Placed | Triangles | Preview |", "|---|---:|---:|---|"]
    for r in sorted(sh, key=lambda r: -r["placed"] * (r["result"]["before"] - r["result"]["after"]))[:25]:
        name = os.path.basename(r["rel"])
        lines.append("| %s | %d | %d -> %d | previews/%s.png |" % (name, r["placed"], r["result"]["before"], r["result"]["after"], r["rel"].replace("\\", "_")))
    lines += ["", "## Kept original (a change would have been visible)", ""]
    for r in sorted(kept, key=lambda r: -r.get("placed", 0))[:25]:
        lines.append("- %s (placed %d)" % (os.path.basename(r["rel"]), r.get("placed", 0)))
    open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return dict(shipped=len(sh), kept=len(kept), tris_before=b, tris_after=a, world_before=wb, world_after=wa, mods=mods)
