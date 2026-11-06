"""Cabinet construction rules, cut list, edge banding, hardware and sheet nesting.

All dimensions are millimetres.

3D coordinate convention (used by the preview):
  x = width (0 at the left side), y = up from the floor, z = depth
  (0 at the back of the cabinet, +z towards the front / the user).

Panel convention: `l` is the grain direction, `w` the other face dimension.
"""
from __future__ import annotations

import math
from typing import Any

DEFAULTS: dict[str, Any] = {
    # Boards
    "sheet_l": 2440,
    "sheet_w": 1220,
    "kerf": 3,
    "trim": 5,
    # Thicknesses
    "t": 18,            # carcass
    "back_t": 6,
    "door_t": 18,
    "box_t": 16,        # drawer box sides / front / back
    "box_bottom_t": 6,
    # Construction
    "reveal": 2,
    "plinth_h": 100,
    "shelf_setback": 20,
    "stretcher_w": 100,
    "runner_clear": 13,  # per side, for side-mount runners
    "box_h": 120,
    "drawer_front_h": 180,  # used when drawers share a cabinet with doors
    # Materials
    "carcass_material": "White melamine MFC",
    "front_material": "Door board",
    "back_material": "HDF",
    "box_material": "White melamine MFC",
    "grain_carcass": False,
    "grain_fronts": False,
    # Edge banding
    "band_front_t": 2.0,
    "band_carcass_t": 0.8,
    "band_waste_pct": 10,
    # Hardware
    "handles": True,
    "bay_base_depth": 500,   # depth of the drawer base under a display bay
}

DEFAULT_DEPTH = {"base": 560, "wall": 320, "tall": 560, "sink": 560, "drawer": 560,
                 "bay": 300, "bayup": 300, "counter": 600}
RUNNER_LENGTHS = [250, 300, 350, 400, 450, 500, 550]
HAS_PLINTH = {"base", "tall", "sink", "drawer", "counter"}
FULL_TOP = {"wall", "tall", "bayup", "counter"}


def _r(x: float) -> int:
    return int(math.floor(x + 0.5))


def _panel(code, name, l, w, t, material, edges, box, group, grain=False, band="carcass"):
    x, y, z, bw, bh, bd = box
    return {
        "code": code,
        "name": name,
        "l": _r(l),
        "w": _r(w),
        "t": t,
        "material": material,
        "edge_l": edges[0],
        "edge_w": edges[1],
        "band": band,
        "group": group,
        "grain": bool(grain),
        "box": {"x": round(x, 1), "y": round(y, 1), "z": round(z, 1),
                "w": round(bw, 1), "h": round(bh, 1), "d": round(bd, 1)},
    }


def _fx(kind, shape, axis, x, y, z, w, h, d):
    """A hardware item for the 3D view: a box (or a cylinder along `axis`) in cabinet mm."""
    return {"kind": kind, "shape": shape, "axis": axis,
            "box": {"x": round(x, 1), "y": round(y, 1), "z": round(z, 1),
                    "w": round(w, 1), "h": round(h, 1), "d": round(d, 1)}}


def hinges_per_door(door_h: float) -> int:
    if door_h <= 900:
        return 2
    if door_h <= 1500:
        return 3
    if door_h <= 2000:
        return 4
    return 5


def build_cabinet(cab: dict, S: dict) -> dict:
    """Return panels, hardware and warnings for ONE cabinet."""
    warnings: list[str] = []
    typ = cab.get("type", "base")
    if typ not in DEFAULT_DEPTH:
        typ = "base"
    if typ == "bay":
        return _compose_bay(cab, S)
    W = float(cab["w"])
    H = float(cab["h"])
    D = float(cab.get("d") or DEFAULT_DEPTH[typ])
    doors = int(cab.get("doors", 0) or 0)
    drawers = int(cab.get("drawers", 0) or 0)
    shelves = int(cab.get("shelves", 0) or 0)

    S = dict(S)
    if cab.get("t"):
        S["t"] = int(cab["t"]) if float(cab["t"]).is_integer() else float(cab["t"])
    t, bt, dt = S["t"], S["back_t"], S["door_t"]
    bxt, bxb = S["box_t"], S["box_bottom_t"]
    is_bay = typ == "bayup"          # the display unit that sits on a bay's base
    base_h = 0.0
    header_h = float(cab.get("header_h") or 0) if is_bay else 0.0
    rv = S["reveal"]
    plinth = S["plinth_h"] if typ in HAS_PLINTH else 0
    Hc = H - plinth            # carcass height
    Dc = D - bt                # carcass panel depth (back is fixed on the rear)
    Wi = W - 2 * t             # inside width

    if W < 150 or H < 200 or D < 100:
        raise ValueError(f"{cab.get('ref','?')}: dimensions too small ({W}x{H}x{D})")
    if Wi <= 0 or Hc <= 2 * t + 50:
        raise ValueError(f"{cab.get('ref','?')}: carcass too small for board thickness")
    if is_bay and H - header_h < (shelves + 2) * t + 80:
        raise ValueError(f"{cab.get('ref','?')}: display height {int(H)} leaves no room for "
                         f"{shelves} shelves under a {int(header_h)} mm header")

    cm, fm, bm, xm = S["carcass_material"], S["front_material"], S["back_material"], S["box_material"]
    gc, gf = S["grain_carcass"], S["grain_fronts"]
    panels: list[dict] = []

    # ---- carcass ----------------------------------------------------------
    panels.append(_panel("SIDE-L", "Side panel", Hc, Dc, t, cm, (1, 0),
                         (0, plinth, bt, t, Hc, Dc), "carcass", gc))
    panels.append(_panel("SIDE-R", "Side panel", Hc, Dc, t, cm, (1, 0),
                         (W - t, plinth, bt, t, Hc, Dc), "carcass", gc))

    has_bottom = typ != "sink"
    if has_bottom:
        panels.append(_panel("BOTTOM", "Bottom panel", Wi, Dc, t, cm, (1, 0),
                             (t, plinth, bt, Wi, t, Dc), "carcass", gc))
    if typ in FULL_TOP:
        panels.append(_panel("TOP", "Top panel", Wi, Dc, t, cm, (1, 0),
                             (t, H - t, bt, Wi, t, Dc), "carcass", gc))
    else:
        sw = S["stretcher_w"]
        panels.append(_panel("STR-F", "Top stretcher", Wi, sw, t, cm, (1, 0),
                             (t, H - t, D - sw, Wi, t, sw), "carcass", gc))
        panels.append(_panel("STR-B", "Top stretcher", Wi, sw, t, cm, (0, 0),
                             (t, H - t, bt, Wi, t, sw), "carcass", gc))

    # ---- display unit: fixed shelves, header box ----------------------------
    if is_bay:
        zone_top = H - header_h if header_h else H - t
        zone_bot = t
        space = (zone_top - zone_bot - shelves * t) / (shelves + 1)
        if space < 100:
            warnings.append(f"{shelves} fixed shelves leave only {_r(space)} mm spaces")
        for i in range(shelves):
            y = zone_bot + space * (i + 1) + t * i
            panels.append(_panel(f"SHELF-{i+1}", "Fixed shelf", Wi, Dc, t, cm, (1, 0),
                                 (t, y, bt, Wi, t, Dc), "shelf", gc))
        if header_h:
            panels.append(_panel("HDR-BASE", "Header bottom panel", Wi, Dc, t, cm, (1, 0),
                                 (t, zone_top, bt, Wi, t, Dc), "carcass", gc))
            panels.append(_panel("HDR-FASCIA", "Header fascia", W - 2 * rv, header_h - rv, dt, fm, (2, 2),
                                 (rv, zone_top, D, W - 2 * rv, header_h - rv, dt),
                                 "front", S["grain_fronts"], "front"))

    # ---- adjustable shelves -------------------------------------------------
    if shelves > 0 and not is_bay:
        inner_bottom = plinth + (t if has_bottom else 0)
        inner_top = H - t
        inner_h = inner_top - inner_bottom
        gap = (inner_h - shelves * t) / (shelves + 1)
        if gap < 80:
            warnings.append(f"{shelves} shelves leave only {_r(gap)} mm gaps")
        sl = Wi - 2
        sd = Dc - S["shelf_setback"]
        for i in range(shelves):
            y = inner_bottom + gap * (i + 1) + t * i
            panels.append(_panel(f"SHELF-{i+1}", "Adjustable shelf", sl, sd, t, cm, (1, 0),
                                 (t + 1, y, bt, sl, t, sd), "shelf", gc))

    # ---- back -------------------------------------------------------------
    panels.append(_panel("BACK", "Back panel", Hc, W, bt, bm, (0, 0),
                         (0, plinth, 0, W, Hc, bt), "back", False))

    # ---- plinth -----------------------------------------------------------
    if plinth:
        panels.append(_panel("PLINTH", "Plinth", W, plinth, t, cm, (0, 0),
                             (0, 0, D - 70 - t, W, plinth, t), "plinth", gc))

    # ---- fronts: drawers on top, doors below ------------------------------
    front_z = D
    zone_top_f = H
    y_top = zone_top_f - rv
    drawer_fronts: list[tuple[float, float]] = []   # (y0, height)
    if drawers:
        if doors:
            df = S["drawer_front_h"]
        else:
            df = (zone_top_f - plinth - rv * (drawers + 1)) / drawers
        for i in range(drawers):
            fh = df
            y0 = y_top - fh
            drawer_fronts.append((y0, fh))
            y_top = y0 - rv
            panels.append(_panel(f"DRFRONT-{i+1}", "Drawer front", W - 2 * rv, fh, dt, fm,
                                 (2, 2), (rv, y0, front_z, W - 2 * rv, fh, dt),
                                 "front", S["grain_fronts"], "front"))
    door_h = 0.0
    door_geo: list[tuple[float, float]] = []      # (x0, width) of each door
    door_y0 = plinth + rv
    if doors:
        door_y0 = plinth + rv
        door_h = y_top - door_y0
        if door_h < 100:
            warnings.append("No room left for doors above/below the drawers")
        dw = (W - rv * (doors + 1)) / doors
        if dw > 600:
            warnings.append(f"Doors are {_r(dw)} mm wide; consider more doors")
        if door_h > 2200:
            warnings.append(f"Doors are {_r(door_h)} mm tall; consider splitting")
        for i in range(doors):
            x0 = rv + i * (dw + rv)
            door_geo.append((x0, dw))
            panels.append(_panel(f"DOOR-{i+1}", "Door", door_h, dw, dt, fm, (2, 2),
                                 (x0, door_y0, front_z, dw, door_h, dt), "front", gf, "front"))

    # ---- drawer boxes -------------------------------------------------------
    runner_len = 0
    if drawers:
        rc = S["runner_clear"]
        bw = Wi - 2 * rc
        avail = Dc - 40
        fits = [r for r in RUNNER_LENGTHS if r <= avail]
        if not fits:
            warnings.append("Cabinet too shallow for a drawer runner")
            runner_len = max(int(avail // 10 * 10), 100)
        else:
            runner_len = fits[-1]
        bd = runner_len
        for i, (fy, fh) in enumerate(drawer_fronts):
            bh = min(S["box_h"], fh - 50)
            if bh < 60:
                warnings.append(f"Drawer {i+1} front only {_r(fh)} mm high; box is {_r(bh)} mm")
                bh = max(bh, 40)
            by = fy + 15
            x0 = t + rc
            zf = D - 2
            n = i + 1
            panels.append(_panel(f"DRBOX{n}-SIDE-L", "Drawer box side", bd, bh, bxt, xm, (0, 0),
                                 (x0, by, zf - bd, bxt, bh, bd), "drawerbox"))
            panels.append(_panel(f"DRBOX{n}-SIDE-R", "Drawer box side", bd, bh, bxt, xm, (0, 0),
                                 (x0 + bw - bxt, by, zf - bd, bxt, bh, bd), "drawerbox"))
            panels.append(_panel(f"DRBOX{n}-FRONT", "Drawer box front/back", bw - 2 * bxt, bh, bxt, xm, (0, 0),
                                 (x0 + bxt, by, zf - bxt, bw - 2 * bxt, bh, bxt), "drawerbox"))
            panels.append(_panel(f"DRBOX{n}-BACK", "Drawer box front/back", bw - 2 * bxt, bh, bxt, xm, (0, 0),
                                 (x0 + bxt, by, zf - bd, bw - 2 * bxt, bh, bxt), "drawerbox"))
            panels.append(_panel(f"DRBOX{n}-BASE", "Drawer base", bw, bd, bxb, bm, (0, 0),
                                 (x0, by, zf - bd, bw, bxb, bd), "drawerbox"))

    # ---- hardware positions for the 3D view -------------------------------
    fx: list[dict] = []
    if typ in HAS_PLINTH and plinth:
        xs = [60, W / 2, W - 60] if W > 800 else [60, W - 60]
        zs = [bt + 60, D - 70 - t - 40]
        for x in xs:
            for z in zs:
                fx.append(_fx("leg", "cyl", "y", x - 18, 0, z - 18, 36, plinth, 36))
    for i, (x0, dw) in enumerate(door_geo):
        left = (i % 2 == 0) if doors > 1 else True
        n = hinges_per_door(door_h)
        for j in range(n):
            y = door_y0 + door_h / 2 if n == 1 or door_h < 250 else door_y0 + 100 + j * (door_h - 200) / (n - 1)
            hx = x0 + 8 if left else x0 + dw - 8 - 35
            fx.append(_fx("hinge", "box", "y", hx, y - 20, front_z - 14, 35, 40, 14))
        if S["handles"]:
            gx = x0 + dw - 30 if left else x0 + 18
            fx.append(_fx("handle", "box", "y", gx, door_y0 + door_h / 2 - 80, front_z + dt, 12, 160, 25))
    if S["handles"]:
        for (fy, fh) in drawer_fronts:
            fx.append(_fx("handle", "box", "x", W / 2 - 80, fy + fh - 40, front_z + dt, 160, 12, 25))
    if drawers:
        for (fy, fh), n in zip(drawer_fronts, range(1, drawers + 1)):
            bh_ = min(S["box_h"], fh - 50)
            by_ = fy + 15
            for sx in (t, W - t - S["runner_clear"]):
                fx.append(_fx("runner", "box", "z", sx, by_ + bh_ / 2 - 22, D - 2 - runner_len, S["runner_clear"], 45, runner_len))
    for pnl in panels:
        if pnl["group"] in ("carcass", "shelf") and pnl["code"] not in ("SIDE-L", "SIDE-R"):
            b = pnl["box"]
            if pnl["code"].startswith("SHELF") and not is_bay:
                for sx in (t, W - t - 3):
                    for z in (bt + 37, bt + Dc - S["shelf_setback"] - 37):
                        fx.append(_fx("pin", "cyl", "x", sx, b["y"] - 6, z - 2.5, 3, 5, 5))
            else:
                for end_x in (t - 6, W - t):
                    for z in (b["z"] + 37, b["z"] + b["d"] - 37):
                        fx.append(_fx("fixing", "cyl", "x", end_x, b["y"] + b["h"] / 2 - 7, z - 7, 6, 14, 14))

    # ---- hardware ---------------------------------------------------------
    hw: list[dict] = []
    if doors:
        hw.append({"item": "Hinge (concealed, 110Â°)", "qty": doors * hinges_per_door(door_h)})
    if S["handles"] and (doors + drawers):
        hw.append({"item": "Handle / pull", "qty": doors + drawers})
    if drawers:
        hw.append({"item": f"Drawer runners, pair ({runner_len} mm)", "qty": drawers})
    if shelves and not is_bay:
        hw.append({"item": "Shelf pin", "qty": shelves * 4})
    if typ in HAS_PLINTH:
        hw.append({"item": "Adjustable leg", "qty": 6 if W > 800 else 4})
    if typ in ("wall", "tall", "bayup"):
        hw.append({"item": "Wall hanging / fixing bracket", "qty": 2})
    cams = 8
    if is_bay:   # every fixed shelf, the base top and the header bottom are cammed in
        cams += 4 * (shelves + 1 + (1 if header_h else 0))
    hw.append({"item": "Cam fitting + dowel set", "qty": cams})

    return {
        "ref": cab.get("ref", ""),
        "type": typ,
        "w": _r(W), "h": _r(H), "d": _r(D),
        "doors": doors, "drawers": drawers, "shelves": shelves,
        "plinth": plinth,
        "t": t,
        "base_h": None,
        "header_h": _r(header_h) if is_bay else None,
        "group": cab.get("group", ""),
        "panels": panels,
        "hardware": hw,
        "fixtures": fx,
        "warnings": warnings,
    }


def _compose_bay(cab: dict, S: dict) -> dict:
    """A display bay = drawer/door base (deeper) + shallow shelved display unit on top."""
    S = dict(S)
    if cab.get("t"):
        S["t"] = cab["t"]
    W, H = float(cab["w"]), float(cab["h"])
    up_d = float(cab.get("d") or DEFAULT_DEPTH["bay"])
    base_d = float(cab.get("base_d") or S.get("bay_base_depth", 500))
    base_h = float(cab.get("base_h") or 900)
    ref = cab.get("ref", "")
    if H <= base_h + 200:
        raise ValueError(f"{ref}: height {int(H)} is not taller than the {int(base_h)} mm base")
    drawers = int(cab.get("drawers", 0) or 0)
    doors = int(cab.get("doors", 0) or 0)
    lo = build_cabinet({"ref": ref, "type": "drawer" if drawers else "base", "w": W, "h": base_h,
                        "d": max(base_d, up_d), "drawers": drawers, "doors": doors, "shelves": 0,
                        "t": cab.get("t")}, S)
    up = build_cabinet({"ref": ref, "type": "bayup", "w": W, "h": H - base_h, "d": up_d,
                        "shelves": int(cab.get("shelves", 0) or 0), "header_h": cab.get("header_h"),
                        "t": cab.get("t")}, S)
    panels = []
    for p in lo["panels"]:
        p = dict(p)
        p["code"] = "LO-" + p["code"]
        panels.append(p)
    for p in up["panels"]:
        p = dict(p)
        p["code"] = "UP-" + p["code"]
        p["box"] = {**p["box"], "y": round(p["box"]["y"] + base_h, 1)}
        panels.append(p)
    fixtures = list(lo["fixtures"]) + [
        {**f, "box": {**f["box"], "y": round(f["box"]["y"] + base_h, 1)}} for f in up["fixtures"]]
    hw: dict[str, int] = {}
    for h in lo["hardware"] + up["hardware"]:
        hw[h["item"]] = hw.get(h["item"], 0) + h["qty"]
    return {
        "ref": ref, "type": "bay", "w": _r(W), "h": _r(H), "d": lo["d"],
        "doors": doors, "drawers": drawers, "shelves": up["shelves"],
        "plinth": lo["plinth"], "t": up["t"], "base_h": _r(base_h), "header_h": up["header_h"],
        "upper_d": up["d"], "group": cab.get("group", ""),
        "panels": panels,
        "hardware": [{"item": k, "qty": v} for k, v in hw.items()],
        "fixtures": fixtures,
        "warnings": lo["warnings"] + up["warnings"],
    }


# ---------------------------------------------------------------------------
# Nesting (guillotine packer â€” every cut runs edge to edge, panel-saw friendly)
# ---------------------------------------------------------------------------

def _pack(pieces: list[dict], sheet_l: int, sheet_w: int, kerf: int, trim: int, sort_key) -> list[dict]:
    usable_l = sheet_l - 2 * trim
    usable_w = sheet_w - 2 * trim
    sheets: list[dict] = []

    def new_sheet():
        s = {"free": [(trim, trim, usable_l + kerf, usable_w + kerf)], "placed": []}
        sheets.append(s)
        return s

    for p in sorted(pieces, key=sort_key, reverse=True):
        best = None
        for si, s in enumerate(sheets):
            for fi, (fx, fy, fw, fh) in enumerate(s["free"]):
                for rot in ((False, True) if p["rot_ok"] else (False,)):
                    pw, ph = (p["w"], p["l"]) if rot else (p["l"], p["w"])
                    if pw + kerf <= fw and ph + kerf <= fh:
                        score = fw * fh - (pw + kerf) * (ph + kerf)
                        cand = (si, score, fi, rot)
                        if best is None or cand < best:
                            best = cand
            if best is not None and best[0] == si:
                break  # first sheet that can take the piece
        if best is None:
            s = new_sheet()
            si, fi, rot = len(sheets) - 1, 0, False
            for r in ((False, True) if p["rot_ok"] else (False,)):
                pw, ph = (p["w"], p["l"]) if r else (p["l"], p["w"])
                if pw + kerf <= s["free"][0][2] and ph + kerf <= s["free"][0][3]:
                    rot = r
                    break
            best = (si, 0, fi, rot)
        si, _, fi, rot = best
        s = sheets[si]
        fx, fy, fw, fh = s["free"].pop(fi)
        pw, ph = (p["w"], p["l"]) if rot else (p["l"], p["w"])
        s["placed"].append({"id": p["id"], "label": p["label"], "x": fx, "y": fy,
                            "w": pw, "h": ph, "rot": rot})
        rw, rh = fw - (pw + kerf), fh - (ph + kerf)
        if rw < rh:   # split horizontally (shorter leftover axis)
            rects = [(fx + pw + kerf, fy, rw, ph + kerf), (fx, fy + ph + kerf, fw, rh)]
        else:
            rects = [(fx + pw + kerf, fy, rw, fh), (fx, fy + ph + kerf, pw + kerf, rh)]
        s["free"].extend(r for r in rects if r[2] > kerf and r[3] > kerf)
    return sheets


def _strips(pcs: list[dict], axis: str) -> list[list[dict]]:
    """Split pieces into strips separated by a clear full-width (H) or full-height (V) line."""
    lo, hi = ("y", "h") if axis == "H" else ("x", "w")
    ordered = sorted(pcs, key=lambda p: p[lo])
    strips, cur, edge = [], [], None
    for p in ordered:
        if cur and p[lo] >= edge - 0.5:
            strips.append(cur)
            cur, edge = [], None
        cur.append(p)
        end = p[lo] + p[hi]
        edge = end if edge is None else max(edge, end)
    if cur:
        strips.append(cur)
    return strips


def cut_sequence(placed: list[dict], S: dict) -> list[dict]:
    """Saw cut order for a guillotine layout, stage by stage.

    H cut = line at y = pos running along x; V cut = line at x = pos running along y.
    Positions are measured from the board's top / left edge and mark the edge of the
    part being kept; the saw kerf falls on the waste / far side of the line.
    """
    kerf, trim = S["kerf"], S["trim"]
    cuts: list[dict] = []
    level = [((trim, trim, S["sheet_l"] - trim, S["sheet_w"] - trim), placed)]
    stage = 0
    while level and stage < 20:
        stage += 1
        nxt = []
        for (x0, y0, x1, y1), pcs in level:
            if not pcs:
                continue
            right = max(p["x"] + p["w"] for p in pcs)
            bottom = max(p["y"] + p["h"] for p in pcs)
            if bottom < y1 - 0.5:
                cuts.append({"stage": stage, "dir": "H", "pos": bottom, "from": x0, "to": x1})
                y1 = bottom
            if right < x1 - 0.5:
                cuts.append({"stage": stage, "dir": "V", "pos": right, "from": y0, "to": y1})
                x1 = right
            if len(pcs) == 1:
                continue
            for axis in ("H", "V"):
                strips = _strips(pcs, axis)
                if len(strips) > 1:
                    break
            else:
                cuts.append({"stage": stage, "dir": "?", "pos": 0, "from": 0, "to": 0})
                continue
            lo, hi = ("y", "h") if axis == "H" else ("x", "w")
            start = y0 if axis == "H" else x0
            for i, strip in enumerate(strips):
                end = max(p[lo] + p[hi] for p in strip)
                region = (x0, start, x1, end) if axis == "H" else (start, y0, end, y1)
                if i < len(strips) - 1:
                    if axis == "H":
                        cuts.append({"stage": stage, "dir": "H", "pos": end, "from": x0, "to": x1})
                    else:
                        cuts.append({"stage": stage, "dir": "V", "pos": end, "from": y0, "to": y1})
                nxt.append((region, strip))
                start = end + kerf
        level = sorted(nxt, key=lambda r: (r[0][1], r[0][0]))
    for i, c in enumerate(cuts):
        c["n"] = i + 1
        c["len"] = int(round(c["to"] - c["from"]))
    return cuts


def nest_group(pieces: list[dict], S: dict) -> dict:
    sl, sw, kerf, trim = S["sheet_l"], S["sheet_w"], S["kerf"], S["trim"]
    usable_l, usable_w = sl - 2 * trim, sw - 2 * trim
    ok, oversize = [], []
    for p in pieces:
        fits = (p["l"] <= usable_l and p["w"] <= usable_w) or \
               (p["rot_ok"] and p["w"] <= usable_l and p["l"] <= usable_w)
        (ok if fits else oversize).append(p)

    keys = [
        lambda p: (p["l"] * p["w"], max(p["l"], p["w"])),
        lambda p: (max(p["l"], p["w"]), p["l"] * p["w"]),
        lambda p: (p["w"], p["l"]),
        lambda p: (min(p["l"], p["w"]), p["l"] * p["w"]),
    ]
    best = None
    for k in keys:
        sheets = _pack(ok, sl, sw, kerf, trim, k) if ok else []
        biggest = max((fw * fh for s in sheets for (_, _, fw, fh) in s["free"]), default=0)
        score = (len(sheets), -biggest)
        if best is None or score < best[0]:
            best = (score, sheets)
    sheets = best[1]

    sheet_area = sl * sw
    out_sheets = []
    for i, s in enumerate(sheets):
        used = sum(pl["w"] * pl["h"] for pl in s["placed"])
        out_sheets.append({
            "index": i + 1,
            "placed": s["placed"],
            "cuts": cut_sequence(s["placed"], S),
            "used_area": used,
            "utilisation": round(100 * used / sheet_area, 1),
        })
    total_used = sum(s["used_area"] for s in out_sheets)
    return {
        "sheets": out_sheets,
        "sheet_count": len(out_sheets),
        "piece_count": len(ok),
        "utilisation": round(100 * total_used / (sheet_area * len(out_sheets)), 1) if out_sheets else 0,
        "oversize": [{"label": p["label"], "l": p["l"], "w": p["w"]} for p in oversize],
    }


# ---------------------------------------------------------------------------
# Top level
# ---------------------------------------------------------------------------

def generate(cabinets: list[dict], settings: dict | None = None) -> dict:
    S = {**DEFAULTS, **{k: v for k, v in (settings or {}).items() if v is not None}}
    results, errors = [], []
    for idx, c in enumerate(cabinets):
        try:
            qty = max(int(c.get("qty", 1) or 1), 1)
            r = build_cabinet(c, S)
            r["qty"] = qty
            r["idx"] = idx
            results.append(r)
        except (ValueError, KeyError, TypeError) as e:
            errors.append(str(e))

    # consolidated cut list
    cut: dict[tuple, dict] = {}
    for r in results:
        for p in r["panels"]:
            key = (p["name"], p["l"], p["w"], p["t"], p["material"], p["edge_l"], p["edge_w"], p["band"], p["grain"])
            row = cut.setdefault(key, {
                "name": p["name"], "l": p["l"], "w": p["w"], "t": p["t"], "material": p["material"],
                "edge_l": p["edge_l"], "edge_w": p["edge_w"], "band": p["band"], "grain": p["grain"],
                "qty": 0, "refs": [],
            })
            row["qty"] += r["qty"]
            if r["ref"] not in row["refs"]:
                row["refs"].append(r["ref"])
    for row in cut.values():
        row["area_m2"] = round(row["l"] * row["w"] / 1_000_000, 4)
        row["total_area_m2"] = round(row["qty"] * row["area_m2"], 4)
    cutlist = sorted(cut.values(), key=lambda x: (x["material"], x["t"], -x["l"], -x["w"]))

    # edge banding
    band_mm = {"front": 0.0, "carcass": 0.0}
    for r in results:
        for p in r["panels"]:
            band_mm[p["band"]] += r["qty"] * (p["edge_l"] * p["l"] + p["edge_w"] * p["w"])
    waste = 1 + S["band_waste_pct"] / 100
    banding = [
        {"type": f"{S['band_front_t']:g} mm (fronts)", "metres": round(band_mm["front"] / 1000, 2),
         "metres_with_waste": round(band_mm["front"] / 1000 * waste, 1)},
        {"type": f"{S['band_carcass_t']:g} mm (carcass)", "metres": round(band_mm["carcass"] / 1000, 2),
         "metres_with_waste": round(band_mm["carcass"] / 1000 * waste, 1)},
    ]

    # hardware
    hw: dict[str, int] = {}
    for r in results:
        for h in r["hardware"]:
            hw[h["item"]] = hw.get(h["item"], 0) + h["qty"] * r["qty"]
    hardware = [{"item": k, "qty": v} for k, v in sorted(hw.items())]

    # nesting, grouped by board
    groups: dict[tuple, list[dict]] = {}
    for r in results:
        for k in range(r["qty"]):
            inst = f"{r['ref']}.{k+1}" if r["qty"] > 1 else r["ref"]
            for i, p in enumerate(r["panels"]):
                groups.setdefault((p["material"], p["t"]), []).append({
                    "id": f"{inst}|{p['code']}",
                    "label": f"{inst} {p['code']}",
                    "l": p["l"], "w": p["w"], "rot_ok": not p["grain"],
                })
    nesting = []
    for (mat, th), pieces in sorted(groups.items()):
        n = nest_group(pieces, S)
        n.update({"material": mat, "t": th})
        nesting.append(n)

    sheet_total = sum(n["sheet_count"] for n in nesting)
    return {
        "settings": S,
        "cabinets": results,
        "cutlist": cutlist,
        "banding": banding,
        "hardware": hardware,
        "nesting": nesting,
        "errors": errors,
        "summary": {
            "cabinet_count": sum(r["qty"] for r in results),
            "panel_count": sum(c["qty"] for c in cutlist),
            "board_area_m2": round(sum(c["total_area_m2"] for c in cutlist), 4),
            "sheet_count": sheet_total,
        },
    }


