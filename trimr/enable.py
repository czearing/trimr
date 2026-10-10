"""Optional: add the output mod to the MO2 profile above the mods it overrides. MO2 must be closed (it rewrites modlist.txt on exit)."""
import os
import shutil
import subprocess


def mo2_running():
    out = subprocess.run(["tasklist"], capture_output=True, text=True).stdout.lower()
    return "modorganizer.exe" in out


def enable(inst, out_mod_name, source_mods):
    if mo2_running():
        raise SystemExit("Close Mod Organizer first (it overwrites modlist.txt when it closes), then run this again.")
    p = os.path.join(inst.profile_dir, "modlist.txt")
    text = open(p, encoding="utf-8", newline="").read()
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = [l for l in text.split(nl) if l not in ("+" + out_mod_name, "-" + out_mod_name)]
    src = {m.lower() for m in source_mods}
    idx = [i for i, l in enumerate(lines) if l[:1] in ("+", "-") and l[1:].lower() in src]
    pos = min(idx) if idx else 1
    shutil.copy2(p, p + ".before-trimr")
    lines.insert(pos, "+" + out_mod_name)
    open(p, "w", encoding="utf-8", newline="").write(nl.join(lines))
    return lines[pos + 1][1:] if pos + 1 < len(lines) else ""
