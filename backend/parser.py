"""Read a PDF (text layer first, OCR for scans) and pull out cabinet rows.

The parser is deliberately forgiving and flags what it is unsure about, so the
user can correct the table before the cut list is generated.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path



MAX_PAGES = 25

NUM = r"\d+(?:\.\d+)?"
DIM_RE = re.compile(
    rf"({NUM})\s*(mm|cm|m)?\s*[xXÃ—*]\s*({NUM})\s*(mm|cm|m)?(?:\s*[xXÃ—*]\s*({NUM}))?\s*(mm|cm|m)?"
)
REF_RE = re.compile(r"^[\s\W_]*([A-Za-z]{1,3}[-. ]?\d{1,3}[A-Za-z]?)\b")


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def _prep(img: Image.Image) -> Image.Image:
    try:
        from PIL import Image, ImageFilter, ImageOps
    except ImportError as exc:
        raise RuntimeError("Scanned PDF OCR requires Pillow. Text-layer parsing and cut-list generation do not.") from exc
    img = ImageOps.exif_transpose(img).convert("L")
    if img.width < 2000:
        scale = 2000 / img.width
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
    img = ImageOps.autocontrast(img, cutoff=1)
    return img.filter(ImageFilter.SHARPEN)

def _ocr_page(img: Image.Image) -> list[tuple[str, float]]:
    """Return [(line_text, mean_confidence)] for one page image."""
    import pytesseract

    data = pytesseract.image_to_data(
        _prep(img), config="--psm 6", output_type=pytesseract.Output.DICT
    )
    lines: dict[tuple, list[tuple[str, float]]] = defaultdict(list)
    for i, word in enumerate(data["text"]):
        word = word.strip()
        if not word:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines[key].append((word, float(data["conf"][i])))
    out = []
    for key in sorted(lines):
        words = lines[key]
        text = " ".join(w for w, _ in words)
        confs = [c for _, c in words if c >= 0]
        out.append((text, sum(confs) / len(confs) if confs else 0.0))
    return out


def extract_lines(pdf_path: str, dpi: int = 250) -> tuple[list[tuple[str, float]], str]:
    """Return (lines with confidence, source) where source is 'text' or 'ocr'."""
    try:
        txt = subprocess.run(
            ["pdftotext", "-layout", pdf_path, "-"],
            capture_output=True, text=True, timeout=60,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        txt = ""
    if len(re.findall(r"\d", txt)) > 30:   # real text layer with numbers
        return [(ln, 100.0) for ln in txt.splitlines() if ln.strip()], "text"

    from pdf2image import convert_from_path

    pages = convert_from_path(pdf_path, dpi=dpi, last_page=MAX_PAGES)
    lines: list[tuple[str, float]] = []
    for page in pages:
        lines.extend(_ocr_page(page))
    return lines, "ocr"


# ---------------------------------------------------------------------------
# Line -> cabinet row
# ---------------------------------------------------------------------------

KNOWN_PREFIXES = {"B", "W", "T", "P", "SB", "SK", "DB", "DU", "BC", "WC", "TC", "BU", "WU",
                  "TU", "TL", "OH", "UC", "LU"}


def _clean_digits(s: str) -> str:
    """Fix common OCR letter/digit swaps next to digits (O->0, l/I->1)."""
    # a leading reference such as "Tl" or "WI" is really "T1" / "W1"
    m = re.match(r"^(\s*)([A-Za-z]{1,2})([Il])(?=\s)", s)
    if m and m.group(2).upper() in KNOWN_PREFIXES:
        s = m.group(1) + m.group(2) + "1" + s[m.end():]
    # inside a number-like token that already holds a digit: O/o -> 0, I/l -> 1 ("6OO" -> "600")
    table = str.maketrans("OoIl", "0011")
    s = re.sub(r"\b(?=[\dOoIl]*\d)[\dOoIl]{2,5}\b", lambda m: m.group(0).translate(table), s)
    return s


def _to_mm(v: float, unit: str | None, assume_cm: bool) -> float:
    if unit == "m":
        return v * 1000
    if unit == "cm":
        return v * 10
    if assume_cm:
        return v * 10
    if v < 10:
        return v * 1000  # bare metres e.g. 0.6
    return v


def _infer_type(text: str, ref: str | None, w: float, h: float, d: float | None, drawers: int) -> str:
    t = text.lower()
    if "sink" in t:
        return "sink"
    if re.search(r"\b(tall|pantry|larder|oven housing|fridge housing|column|wardrobe)\b", t):
        return "tall"
    if re.search(r"\b(wall|overhead|hanging|hi-?level|upper)\b", t):
        return "wall"
    if drawers >= 2 and re.search(r"\b(base|floor|under)\b|drawer", t):
        return "drawer"
    if re.search(r"\b(base|floor|under)\b", t):
        return "base"
    if ref:
        p = re.match(r"[A-Za-z]+", ref).group(0).upper()
        if p in ("SB", "SK"):
            return "sink"
        if p in ("DB", "DU"):
            return "drawer"
        if p in ("W", "WC", "WU", "OH", "UC"):
            return "wall"
        if p in ("T", "TU", "TC", "TL", "P", "LU"):
            return "tall"
        if p in ("B", "BC", "BU"):
            return "drawer" if drawers >= 2 else "base"
    if h >= 1500:
        return "tall"
    if d is not None and d <= 400:
        return "wall"
    return "drawer" if drawers >= 2 else "base"


def _defaults_for(typ: str, w: float, h: float) -> tuple[int, int, int]:
    """doors, drawers, shelves when the drawing doesn't say."""
    if typ == "drawer":
        return 0, 3, 0
    if typ == "sink":
        return (1 if w <= 500 else 2), 0, 0
    if typ == "tall":
        return 2, 0, 3
    if typ == "wall":
        return (1 if w <= 500 else 2), 0, (2 if h >= 800 else 1)
    return (1 if w <= 500 else 2), 0, 1


def parse_lines(lines: list[tuple[str, float]], order: str = "WHD") -> list[dict]:
    order = order.upper()
    if sorted(order) != ["D", "H", "W"]:
        order = "WHD"
    rows: list[dict] = []
    for raw, conf in lines:
        text = _clean_digits(raw)
        flags: list[str] = []
        m = DIM_RE.search(text)
        numbers: list[float] = []
        units: list[str | None] = []
        if m:
            a, ua, b, ub, c, uc = m.groups()
            numbers = [float(a), float(b)] + ([float(c)] if c else [])
            units = [ua, ub, uc]
            rest = text[: m.start()] + " " + text[m.end():]
        else:
            # table fallback: "B1  600  720  560  2"
            ref_m = REF_RE.match(text)
            nums = [float(n) for n in re.findall(r"\b\d{3,4}\b", text)]
            nums = [n for n in nums if 100 <= n <= 2800]
            if ref_m and len(nums) >= 2:
                numbers = nums[:3]
                units = [None] * len(numbers)
                rest = text
                flags.append("read from table columns")
            else:
                continue

        # size sanity: 2-3 digit sets are probably centimetres
        assume_cm = all(n <= 300 for n in numbers) and not any(u == "mm" for u in units)
        mm = [_to_mm(n, u, assume_cm) for n, u in zip(numbers, units)]
        if assume_cm:
            flags.append("sizes looked like cm; converted to mm")

        if not all(100 <= v <= 3000 for v in mm):
            continue  # not cabinet dimensions (page number, note, etc.)

        dims = dict(zip(order[: len(mm)], mm))
        w, h = dims.get("W"), dims.get("H")
        d = dims.get("D")
        if w is None or h is None:
            # two numbers only; take them as W and H regardless of the order setting
            w, h = mm[0], mm[1]

        ref_m = REF_RE.match(rest.strip()) or REF_RE.match(text)
        ref = re.sub(r"[\s.]+", "-", ref_m.group(1)).upper() if ref_m else None
        if ref_m and REF_RE.match(rest.strip()):
            rest = rest.strip()[ref_m.end():]   # keep the reference's digit out of the counts

        drawers = 0
        dm = re.search(r"(\d+)\s*[- ]?\s*(?:drawers?|drws?)\b", rest, re.I)
        if dm:
            drawers = int(dm.group(1))
        elif re.search(r"\bdrawers?\b", rest, re.I):
            drawers = 3

        doors = None
        dm = re.search(r"(\d+)\s*[- ]?\s*(?:doors?|drs?)\b(?!awer)", rest, re.I)
        if dm:
            doors = int(dm.group(1))
        elif re.search(r"\bdoors?\b", rest, re.I):
            doors = 1

        shelves = None
        sm = re.search(r"(\d+)\s*[- ]?\s*(?:shel(?:f|ves)|shlv?s?)\b", rest, re.I)
        if sm:
            shelves = int(sm.group(1))

        qty = 1
        qm = (re.search(r"(?:qty|quantity)\s*[:=]?\s*(\d+)", rest, re.I)
              or re.search(r"(\d+)\s*(?:nos?\.?|pcs|off|units?)\b", rest, re.I))
        if qm:
            qty = max(1, int(qm.group(1)))

        typ = _infer_type(rest, ref, w, h, d, drawers)
        dd, dr, sh = _defaults_for(typ, w, h)
        if d is None:
            flags.append("depth not found; default used")
        if doors is None and drawers == 0:
            doors = dd
            drawers = dr
        elif doors is None:
            doors = 0
        if shelves is None:
            shelves = sh if (doors or typ == "tall") else 0
        if conf < 70:
            flags.append(f"low OCR confidence ({conf:.0f}%)")

        rows.append({
            "ref": ref or "",
            "type": typ,
            "w": round(w), "h": round(h),
            "d": round(d) if d else None,
            "qty": qty,
            "doors": doors, "drawers": drawers, "shelves": shelves,
            "raw": raw.strip(),
            "flags": flags,
        })

    # fill missing references
    used = {r["ref"] for r in rows if r["ref"]}
    n = 1
    for r in rows:
        if not r["ref"]:
            while f"C{n}" in used:
                n += 1
            r["ref"] = f"C{n}"
            used.add(r["ref"])
            r["flags"].append("reference assigned automatically")
    return rows


def parse_pdf(path: str, order: str = "WHD") -> dict:
    lines, source = extract_lines(path)
    rows = parse_lines(lines, order)
    return {
        "source": source,
        "rows": rows,
        "text": "\n".join(t for t, _ in lines),
    }


