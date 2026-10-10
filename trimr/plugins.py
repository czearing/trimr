"""Read-only Skyrim plugin reader: winning base records and every placed exterior reference."""
import struct
import zlib


def subrecs(data):
    i = 0
    out = []
    big = None
    while i + 6 <= len(data):
        t = data[i:i + 4]
        sz = struct.unpack_from("<H", data, i + 4)[0]
        i += 6
        if t == b"XXXX":
            big = struct.unpack_from("<I", data, i)[0]
            i += 4
            continue
        if big is not None:
            sz = big
            big = None
        out.append((t.decode("latin1"), data[i:i + sz]))
        i += sz
    return out


def scan(inst, types, progress=None):
    """Returns (records, refs).
    records[type][(master, id)] = (model path, editor id) of the winning base record.
    refs[(plugin, id)] = base key for every exterior REFR that is not deleted or initially disabled (later plugins win)."""
    files = inst.plugin_files()
    active = inst.active_plugins()
    want = set(types)
    records = {t: {} for t in types}
    refs = {}
    order = [o for o in inst.load_order() if o.lower() in active and o.lower() in files]
    for n, name in enumerate(order):
        if progress:
            progress(n, len(order), name)
        try:
            d = open(files[name.lower()], "rb").read()
        except OSError:
            continue
        hs = struct.unpack_from("<I", d, 4)[0]
        masters = [s[:-1].decode("latin1").lower() for t, s in subrecs(d[24:24 + hs]) if t == "MAST"]
        me = name.lower()

        def key(fid, masters=masters, me=me):
            idx = fid >> 24
            return (masters[idx] if idx < len(masters) else me, fid & 0xFFFFFF)

        def walk(j, end, label, d=d, key=key):
            while j < end:
                if d[j:j + 4] == b"GRUP":
                    gs = struct.unpack_from("<I", d, j + 4)[0]
                    walk(j + 24, j + gs, label)
                    j += gs
                    continue
                t = d[j:j + 4].decode("latin1")
                rs, fl, fid = struct.unpack_from("<III", d, j + 4)
                if label == "WRLD":
                    if t == "REFR":
                        rk = key(fid)
                        if fl & 0x20 or fl & 0x800:  # deleted or initially disabled
                            refs.pop(rk, None)
                        else:
                            body = d[j + 24:j + 24 + rs]
                            if fl & 0x00040000:
                                body = zlib.decompress(body[4:])
                            for tt, s in subrecs(body):
                                if tt == "NAME":
                                    refs[rk] = key(struct.unpack("<I", s[:4])[0])
                                    break
                else:
                    body = d[j + 24:j + 24 + rs]
                    if fl & 0x00040000:
                        body = zlib.decompress(body[4:])
                    modl = None
                    edid = ""
                    for tt, s in subrecs(body):
                        if tt == "MODL" and modl is None:
                            modl = s[:-1].decode("latin1")
                        elif tt == "EDID":
                            edid = s[:-1].decode("latin1")
                    records[t][key(fid)] = (modl, edid)
                j += 24 + rs

        i = 24 + hs
        while i < len(d):
            gs = struct.unpack_from("<I", d, i + 4)[0]
            label = d[i + 8:i + 12].decode("latin1")
            if label == "WRLD" or label in want:
                walk(i + 24, i + gs, label)
            i += gs
    return records, refs
