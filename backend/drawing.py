"""Read joinery bays from vector elevation drawings (any sheet size, e.g. A1).

Works from the PDF's own text layer and vector geometry, never from pixels:

* dimension text comes with page positions (pdftotext -bbox)
* the drawing scale is worked out from the drawing itself (the spacing of the
  bay dimension labels against the bay pitch), so nothing is tied to A1 or 1:15
* unit depth is measured from the side panels drawn in the plan view
  (pdftocairo -svg), when the plan shows them

Every threshold is relative to the page size or the dimension-text size.
The result is a first reading for the user to check, not a final answer.
"""
from __future__ import annotations

import html
import os
import re
import statistics
import subprocess
import tempfile
from collections import Counter

WORD_RE = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>')
PAGE_RE = re.compile(r'<page width="([\d.]+)" height="([\d.]+)"')
NUM_RE = re.compile(r"^\d[\d,]*$")
TITLE_BLOCK_X = 0.89          # drawing area ends here (fraction of page width)
ELEV_Y = 0.46                 # elevations sit below this fraction of page height
MARKER_MAX = 60               # 20 / 25 / 50 style board-thickness dimensions
DEFAULT_THICKNESS = 20
DEFAULT_HEADER = 300
MAX_PAGES = 40


def _val(tok: str) -> int:
    return int(tok.replace(",", ""))


# ---------------------------------------------------------------------------
# PDF access
# ---------------------------------------------------------------------------

def page_count(pdf: str) -> int:
    out = subprocess.run(["pdfinfo", pdf], capture_output=True, text=True, timeout=60).stdout
    m = re.search(r"^Pages:\s+(\d+)", out, re.M)
    return min(int(m.group(1)), MAX_PAGES) if m else 0


def page_words(pdf: str, page: int):
    out = subprocess.run(["pdftotext", "-f", str(page), "-l", str(page), "-bbox", pdf, "-"],
                         capture_output=True, text=True, timeout=120).stdout
    m = PAGE_RE.search(out)
    if not m:
        return 0.0, 0.0, []
    pw, ph = float(m.group(1)), float(m.group(2))
    words = []
    for a, b, c, d, t in WORD_RE.findall(out):
        words.append({"x0": float(a), "y0": float(b), "x1": float(c), "y1": float(d),
                      "t": html.unescape(t)})
    return pw, ph, words


def page_rects(pdf: str, page: int, pw: float, ph: float):
    """Axis-aligned rectangles drawn on the page: (x, y, w, h) in page points."""
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "p.svg")
        try:
            subprocess.run(["pdftocairo", "-svg", "-f", str(page), "-l", str(page), pdf, out],
                           capture_output=True, timeout=180)
            svg = open(out, encoding="utf-8", errors="ignore").read()
        except (OSError, subprocess.SubprocessError):
            return []
    rects = []
    for dpath in re.findall(r'<path[^>]*?\sd="([^"]+)"', svg):
        nums = [float(n) for n in re.findall(r"-?\d+\.?\d*(?:e-?\d+)?", dpath)]
        cmds = re.findall(r"[MLHVCZmlhvcz]", dpath)
        if len(nums) in (8, 10) and set(cmds) <= set("MLZ") and len(cmds) in (4, 5, 6):
            xs, ys = nums[0::2], nums[1::2]
            if len({round(x, 1) for x in xs}) <= 2 and len({round(y, 1) for y in ys}) <= 2:
                x, y, w, h = min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
                if 0 <= x <= pw and 0 <= y <= ph:
                    rects.append((x, y, w, h))
    return rects


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def sheet_title(words, pw, ph):
    """'ELEVATION 02' style title near the bottom of the drawing area, else None."""
    for w in words:
        if w["t"] == "ELEVATION" and w["y0"] > 0.78 * ph and w["x0"] < TITLE_BLOCK_X * pw:
            for n in words:
                if (re.fullmatch(r"\d{1,2}", n["t"]) and abs(n["y0"] - w["y0"]) < 8
                        and 0 < n["x0"] - w["x1"] < 60):
                    return f"ELEVATION {n['t']}"
    return None


def _numeric_tokens(words, pw):
    toks = [w for w in words if NUM_RE.match(w["t"]) and (w["x0"] + w["x1"]) / 2 < TITLE_BLOCK_X * pw]
    if not toks:
        return [], 0.0
    # Dimension text: every token has exactly one side equal to the font size.
    sides = Counter(round(v * 2) / 2 for w in toks for v in (w["x1"] - w["x0"], w["y1"] - w["y0"]))
    em = sides.most_common(1)[0][0]
    out = []
    for w in toks:
        ww, hh = w["x1"] - w["x0"], w["y1"] - w["y0"]
        if abs(hh - em) <= 1.2 and abs(ww - em) > 1.2:
            orient = "h"
        elif abs(ww - em) <= 1.2 and abs(hh - em) > 1.2:
            orient = "v"
        else:
            continue
        out.append({"v": _val(w["t"]), "cx": (w["x0"] + w["x1"]) / 2, "cy": (w["y0"] + w["y1"]) / 2,
                    "o": orient})
    return out, em


def _cluster(items, key, tol):
    items = sorted(items, key=key)
    groups, cur = [], []
    for it in items:
        if cur and key(it) - key(cur[-1]) > tol:
            groups.append(cur)
            cur = []
        cur.append(it)
    if cur:
        groups.append(cur)
    return groups


def _header_labels(words, pw, y_min):
    """Upper-case section labels (STORE, SKINCARE, PRODUCT DISCOVERY WALL, ...)."""
    cand = [w for w in words if re.fullmatch(r"[A-Z]{3,}", w["t"]) and w["y0"] >= y_min
            and (w["x0"] + w["x1"]) / 2 < TITLE_BLOCK_X * pw
            and w["t"] not in ("ELEVATION", "LAYOUT", "FLOOR", "REVISED", "LOGO", "OPEN")]
    labels = []
    for line in _cluster(cand, lambda w: w["y0"], 6):
        line.sort(key=lambda w: w["x0"])
        groups, cur = [], []
        for w in line:
            if cur and w["x0"] - cur[-1]["x1"] > 40:
                groups.append(cur)
                cur = []
            cur.append(w)
        if cur:
            groups.append(cur)
        for grp in groups:
            labels.append({"text": " ".join(w["t"] for w in grp),
                           "x0": min(w["x0"] for w in grp), "x1": max(w["x1"] for w in grp),
                           "y": grp[0]["y0"]})
    return labels


# ---------------------------------------------------------------------------
# One elevation sheet
# ---------------------------------------------------------------------------

def _bays_from_rows(h_tokens, pw, em):
    """Find bay segments: a dimension >=100 with a thickness marker on both sides.

    Thickness markers (20 20) are drawn on a line just above or below the bay
    widths, so markers are matched by proximity, not by sharing a row.
    """
    R = 0.075 * pw
    markers = [t for t in h_tokens if t["v"] <= MARKER_MAX]
    bays = []
    for seg in h_tokens:
        if seg["v"] < 100 or seg["v"] > 1300:
            continue
        near = [m for m in markers if abs(m["cy"] - seg["cy"]) <= 1.3 * em]
        left = [m for m in near if 0 < seg["cx"] - m["cx"] <= R]
        right = [m for m in near if 0 < m["cx"] - seg["cx"] <= R]
        if left and right:
            bays.append({"clear": seg["v"], "cx": seg["cx"], "cy": seg["cy"],
                         "marker": statistics.median([m["v"] for m in left + right])})
    return bays


def _split_runs(bays, pw):
    runs, cur = [], []
    for b in sorted(bays, key=lambda b: (round(b["cy"] / 12), b["cx"])):
        if cur and (abs(b["cy"] - cur[-1]["cy"]) > 12 or b["cx"] - cur[-1]["cx"] > 0.095 * pw):
            runs.append(cur)
            cur = []
        cur.append(b)
    if cur:
        runs.append(cur)
    return runs


def _run_scale(run):
    """mm per page-point from equal neighbouring bays, or None."""
    est = []
    for a, b in zip(run, run[1:]):
        if a["clear"] == b["clear"]:
            pitch_pt = b["cx"] - a["cx"]
            if pitch_pt > 20:
                est.append((a["clear"] + 2 * a["marker"]) / pitch_pt)
    return statistics.median(est) if est else None


def _vertical_chain(v_tokens, run_x0, run_x1, em):
    cols = _cluster(v_tokens, lambda t: t["cx"], 1.4 * em)
    best = None
    for col in cols:
        cx = statistics.mean(t["cx"] for t in col)
        main = [t for t in col if t["v"] > MARKER_MAX]
        if len(main) < 3 or not (run_x0 - 400 <= cx <= run_x1 + 60):
            continue
        dist = 0 if run_x0 <= cx <= run_x1 else min(abs(cx - run_x0), abs(cx - run_x1))
        score = (dist, -len(main))
        if best is None or score < best[0]:
            best = (score, sorted(col, key=lambda t: t["cy"]))
    return best[1] if best else None


def _read_chain(chain):
    main = [t["v"] for t in chain if t["v"] > MARKER_MAX]
    marker = [t["v"] for t in chain if t["v"] <= MARKER_MAX]
    header = base = None
    if len(main) >= 3 and 250 <= main[0] <= 400 and abs(main[0] - main[1]) > 15:
        header = main[0]
        main = main[1:]
    if len(main) >= 2 and 650 <= main[-1] <= 1000:
        base = main[-1]
        main = main[:-1]
    spaces = [v for v in main if 100 <= v <= 800]
    t = int(statistics.median(marker)) if marker else DEFAULT_THICKNESS
    return {"header": header, "base": base, "spaces": spaces, "t": t}


def _plan_depth(rects, scale, run_x0, run_x1, y_split, thickness):
    """Depth (mm) from the thin side panels drawn in the plan above the elevation."""
    if not scale:
        return None
    t_pt = thickness / scale
    sides = [r for r in rects
             if y_split * 0.0 <= r[1] < y_split and 0.6 * t_pt <= r[2] <= 1.7 * t_pt
             and 40 / scale <= r[3] <= 900 / scale
             and run_x0 - 40 <= r[0] <= run_x1 + 40]
    if not sides:
        return None
    heights = Counter(round(r[3] * 2) / 2 for r in sides)
    h, n = heights.most_common(1)[0]
    if n < 2:
        return None
    depth = int(round((h * scale + thickness) / 5.0) * 5)
    return depth if 150 <= depth <= 900 else None


def _read_elevation(pdf, page, pw, ph, words, title):
    rows, notes = [], []
    toks, em = _numeric_tokens(words, pw)
    if not toks:
        return rows, notes
    y_split = ELEV_Y * ph
    elev_h = [t for t in toks if t["o"] == "h" and t["cy"] >= y_split]
    elev_v = [t for t in toks if t["o"] == "v" and t["cy"] >= y_split]
    labels = _header_labels(words, pw, y_split)
    bays = _bays_from_rows(elev_h, pw, em)
    runs = _split_runs(bays, pw)
    if not runs:
        return rows, notes

    scales = [s for s in (_run_scale(r) for r in runs) if s]
    page_scale = statistics.median(scales) if scales else None
    rects = page_rects(pdf, page, pw, ph) if page_scale else []

    elev_no = title.split()[-1].lstrip("0") or "0"
    small_words = [w for w in words if w["y0"] >= y_split and re.search(r"cleaner|store", w["t"], re.I)]

    for ri, run in enumerate(runs):
        letter = chr(ord("A") + ri)
        x0, x1 = run[0]["cx"] - 90, run[-1]["cx"] + 90
        scale = _run_scale(run) or page_scale
        chain = _vertical_chain(elev_v, x0, x1, em)
        info = _read_chain(chain) if chain else {"header": None, "base": None, "spaces": [], "t": DEFAULT_THICKNESS}
        t = info["t"]
        has_headers = any(x0 - 60 <= (l["x0"] + l["x1"]) / 2 <= x1 + 60 for l in labels)
        header = info["header"] or (DEFAULT_HEADER if has_headers else 0)
        base = info["base"]
        spaces = info["spaces"]
        shelves = max(len(spaces) - 1, 0) if spaces else None

        height = None
        flags_h = []
        if base and spaces:
            height = base + sum(spaces) + max(len(spaces) - 1, 0) * t + header
            for tok in elev_v:   # an overall height on the sheet that agrees with the sum wins
                if 2000 <= tok["v"] <= 3200 and abs(tok["v"] - height) <= 60:
                    height = tok["v"]
                    break
            if not info["header"] and header:
                flags_h.append(f"header height {header} mm assumed")
        depth = _plan_depth(rects, scale, x0, x1, y_split, t)

        for bi, b in enumerate(run):
            flags = list(flags_h)
            label = None
            if labels:
                def gap(l):
                    return 0 if l["x0"] <= b["cx"] <= l["x1"] else min(abs(b["cx"] - l["x0"]), abs(b["cx"] - l["x1"]))
                near = min(labels, key=gap)
                if gap(near) < 0.07 * pw:
                    label = near["text"].title()
            if label and "store" in label.lower():
                flags.append("labelled STORE: probably has a door, check")
            for w in small_words:
                if abs((w["x0"] + w["x1"]) / 2 - b["cx"]) < 0.5 * (b["clear"] / (scale or 5.3)) and re.search(r"cleaner", w["t"], re.I):
                    flags.append("cleaner's store: probably a full-height door, check")
                    break
            if height is None:
                flags.append("height not read; check")
            if depth is None:
                flags.append("depth not shown in plan; default used")
            if base is None:
                flags.append("base height not read; default used")
            plain = chain is None
            if plain:
                flags = ["no shelf/height dimensions found: read as a plain base unit, check",
                         "height assumed 900 mm"] + [f for f in flags if "height not read" not in f and "base height" not in f]
                height = 900
            rows.append({
                "ref": f"E{elev_no}{letter}-{bi + 1}",
                "type": "base" if plain else "bay",
                "w": b["clear"] + 2 * t,
                "h": height,
                "d": depth,
                "qty": 1,
                "doors": (2 if b["clear"] + 2 * t > 600 else 1) if plain else 0,
                "drawers": 0 if plain else 2,
                "shelves": (1 if plain else (shelves if shelves is not None else 3)),
                "t": t,
                "base_h": None if plain else base,
                "header_h": None if plain else (header or None),
                "group": label or "",
                "raw": f"{title} · {label or 'bay'} · clear width {b['clear']} mm",
                "flags": flags,
            })
    return rows, notes


# ---------------------------------------------------------------------------
# Curved / bespoke items (flagged, not cut)
# ---------------------------------------------------------------------------

BESPOKE = [
    (re.compile(r"^reception$", re.I), "desk", "Reception desk"),
    (re.compile(r"^consultation$", re.I), "area", "Consultation counters"),
    (re.compile(r"^product$", re.I), "display", "Product display table"),
]


def _flag_bespoke(words, pw, title, seen):
    out = []
    ordered = sorted(words, key=lambda w: (round(w["y0"] / 8), w["x0"]))
    for i, w in enumerate(ordered):
        for first, second, name in BESPOKE:
            if not first.match(w["t"]):
                continue
            nxt = [n for n in ordered[i + 1:i + 4] if abs(n["y0"] - w["y0"]) < 8 and n["x0"] >= w["x1"]]
            if not nxt or nxt[0]["t"].lower() != second:
                continue
            after = [n for n in ordered[i + 1:i + 5] if abs(n["y0"] - w["y0"]) < 8 and n["x0"] > nxt[0]["x1"]]
            if second == "display" and after and after[0]["t"].lower().startswith("shel"):
                continue   # "Product display shelves" is a normal bay run
            if (name, title) in seen:
                continue
            seen.add((name, title))
            near = sorted((t for t in words if NUM_RE.match(t["t"]) and _val(t["t"]) > MARKER_MAX
                           and abs((t["x0"] + t["x1"]) / 2 - w["x0"]) < 300
                           and abs(t["y0"] - w["y0"]) < 300),
                          key=lambda t: (t["x0"] - w["x0"]) ** 2 + (t["y0"] - w["y0"]) ** 2)
            sizes = []
            for t in near:
                if _val(t["t"]) not in sizes:
                    sizes.append(_val(t["t"]))
                if len(sizes) == 4:
                    break
            out.append({"name": name, "sheet": title, "nearby_sizes": sizes})
    return out


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def read_drawing(pdf_path: str) -> dict:
    rows, bespoke, sheets, seen = [], [], [], set()
    for p in range(1, page_count(pdf_path) + 1):
        pw, ph, words = page_words(pdf_path, p)
        if not words:
            continue
        title = sheet_title(words, pw, ph)
        if not title:
            continue
        got, _ = _read_elevation(pdf_path, p, pw, ph, words, title)
        sheets.append({"page": p, "title": title, "bays": len(got),
                       "size_mm": [round(pw / 72 * 25.4), round(ph / 72 * 25.4)]})
        rows.extend(got)
        bespoke.extend(_flag_bespoke(words, pw, title, seen))
    return {"rows": rows, "bespoke": bespoke, "sheets": sheets}
