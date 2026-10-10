"""Mod Organizer 2 instance discovery and priority aware file lookup."""
import os
import re

BASE_MASTERS = ("skyrim.esm", "update.esm", "dawnguard.esm", "hearthfires.esm", "dragonborn.esm")


def _ini_value(text, key):
    m = re.search(r"(?mi)^%s\s*=\s*(.*)$" % re.escape(key), text)
    if not m:
        return None
    v = m.group(1).strip()
    m2 = re.match(r"@ByteArray\((.*)\)$", v)
    if m2:
        v = m2.group(1)
    return v.replace("\\\\", "\\")


def find_instances():
    """Instances under %LOCALAPPDATA%\\ModOrganizer plus a portable one in the current folder."""
    out = []
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ModOrganizer")
    if os.path.isdir(base):
        for d in sorted(os.listdir(base)):
            p = os.path.join(base, d)
            if os.path.isfile(os.path.join(p, "ModOrganizer.ini")):
                out.append(p)
    cwd = os.getcwd()
    if os.path.isfile(os.path.join(cwd, "ModOrganizer.ini")) and cwd not in out:
        out.append(cwd)
    return out


class Instance:
    def __init__(self, path, profile=None, ignore_mods=()):
        self.path = os.path.abspath(path)
        ini_path = os.path.join(self.path, "ModOrganizer.ini")
        if not os.path.isfile(ini_path):
            raise SystemExit("No ModOrganizer.ini in %s (use --instance <folder that contains ModOrganizer.ini>)" % self.path)
        text = open(ini_path, encoding="utf-8", errors="replace").read()
        self.game_name = _ini_value(text, "gameName") or "Skyrim"
        self.game_path = _ini_value(text, "gamePath") or ""
        self.profile = profile or _ini_value(text, "selected_profile") or "Default"
        base = _ini_value(text, "base_directory") or self.path
        self.mods_dir = os.path.join(base, "mods")
        self.profile_dir = os.path.join(base, "profiles", self.profile)
        if not os.path.isdir(self.profile_dir):
            raise SystemExit("Profile not found: %s" % self.profile_dir)
        self.game_data = os.path.join(self.game_path, "Data")
        self.ignore = {m.lower() for m in ignore_mods}
        self._enabled = None
        self._cache = {}

    def modlist(self):
        """All mods as (enabled, name), highest priority first (file order)."""
        out = []
        for line in open(os.path.join(self.profile_dir, "modlist.txt"), encoding="utf-8", errors="replace"):
            line = line.rstrip("\r\n")
            if line[:1] in ("+", "-") and len(line) > 1 and not line.endswith("_separator"):
                out.append((line[0] == "+", line[1:]))
        return out

    def enabled_mods(self):
        if self._enabled is None:
            self._enabled = [n for e, n in self.modlist() if e and n.lower() not in self.ignore]
        return self._enabled

    def find_file(self, rel):
        """Highest priority loose file for a path relative to Data. Returns (mod, full_path) or (None, None)."""
        k = rel.lower().replace("/", "\\").lstrip("\\")
        if k in self._cache:
            return self._cache[k]
        res = (None, None)
        for m in self.enabled_mods():
            p = os.path.join(self.mods_dir, m, k)
            if os.path.isfile(p):
                res = (m, p)
                break
        self._cache[k] = res
        return res

    def active_plugins(self):
        act = {n.lower() for n in BASE_MASTERS}
        for line in open(os.path.join(self.profile_dir, "plugins.txt"), encoding="utf-8", errors="replace"):
            if line.startswith("*"):
                act.add(line.strip()[1:].lower())
        return act

    def load_order(self):
        p = os.path.join(self.profile_dir, "loadorder.txt")
        if not os.path.isfile(p):
            p = os.path.join(self.profile_dir, "plugins.txt")
        order = [l.strip().lstrip("*") for l in open(p, encoding="utf-8", errors="replace") if l.strip() and not l.startswith("#")]
        low = [o.lower() for o in order]
        for b in reversed(BASE_MASTERS):
            if b not in low:
                order.insert(0, b)
        return order

    def plugin_files(self):
        """plugin name (lower) -> path. Mods in priority order, then the game Data folder."""
        files = {}
        for m in reversed(self.enabled_mods()):
            d = os.path.join(self.mods_dir, m)
            if os.path.isdir(d):
                for f in os.listdir(d):
                    if f.lower().endswith((".esp", ".esm", ".esl")) and os.path.isfile(os.path.join(d, f)):
                        files[f.lower()] = os.path.join(d, f)
        if os.path.isdir(self.game_data):
            for f in os.listdir(self.game_data):
                if f.lower().endswith((".esp", ".esm", ".esl")):
                    files.setdefault(f.lower(), os.path.join(self.game_data, f))
        return files
