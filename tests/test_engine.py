"""Regression checks for panel sizes and nesting. Run: python tests/test_engine.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import engine, parser  # noqa: E402


def test_base_cabinet_sizes():
    r = engine.build_cabinet({"ref": "B1", "type": "base", "w": 600, "h": 720, "d": 560,
                              "doors": 2, "shelves": 1}, engine.DEFAULTS)
    by = {p["code"]: p for p in r["panels"]}
    assert (by["SIDE-L"]["l"], by["SIDE-L"]["w"]) == (620, 554)
    assert (by["BOTTOM"]["l"], by["BOTTOM"]["w"]) == (564, 554)
    assert (by["DOOR-1"]["l"], by["DOOR-1"]["w"]) == (616, 297)
    assert (by["SHELF-1"]["l"], by["SHELF-1"]["w"]) == (562, 534)
    hinges = [h for h in r["hardware"] if h["item"].startswith("Hinge")][0]
    assert hinges["qty"] == 4


def test_drawer_base():
    r = engine.build_cabinet({"ref": "DB1", "type": "drawer", "w": 600, "h": 720, "d": 560,
                              "drawers": 3}, engine.DEFAULTS)
    fronts = [p for p in r["panels"] if p["code"].startswith("DRFRONT")]
    assert len(fronts) == 3 and all(f["w"] == 204 for f in fronts)
    assert len([p for p in r["panels"] if p["code"].startswith("DRBOX")]) == 15


def test_nesting_valid():
    rows = [{"ref": f"B{i}", "type": "base", "w": 600, "h": 720, "d": 560, "doors": 2,
             "shelves": 1, "qty": 3} for i in range(1, 5)]
    res = engine.generate(rows)
    S = res["settings"]
    placed = 0
    for n in res["nesting"]:
        assert not n["oversize"]
        for s in n["sheets"]:
            pl = s["placed"]
            placed += len(pl)
            for i, a in enumerate(pl):
                assert a["x"] >= S["trim"] and a["y"] >= S["trim"]
                assert a["x"] + a["w"] <= S["sheet_l"] - S["trim"]
                assert a["y"] + a["h"] <= S["sheet_w"] - S["trim"]
                for b in pl[i + 1:]:
                    assert not (a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"]
                                and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"])
    assert placed == sum(r["qty"] * len(r["panels"]) for r in res["cabinets"])


def test_grain_parts_not_rotated():
    res = engine.generate([{"ref": "T1", "type": "tall", "w": 600, "h": 2100, "d": 560,
                            "doors": 2, "shelves": 3, "qty": 1}], {"grain_fronts": True})
    for n in res["nesting"]:
        if n["material"] == "Door board":
            assert all(not p["rot"] for s in n["sheets"] for p in s["placed"])


def test_parser_variants():
    rows = parser.parse_lines([("Wl Wall unit 60 x 72 x 32 cm 1 door", 95.0),
                               ("B2 Base 8OO x 72O x 56O 2 doors qty 2", 90.0),
                               ("Page 3 of 12", 99.0)])
    assert len(rows) == 2
    assert (rows[0]["ref"], rows[0]["w"], rows[0]["h"], rows[0]["d"], rows[0]["type"]) == ("W1", 600, 720, 320, "wall")
    assert (rows[1]["w"], rows[1]["h"], rows[1]["d"], rows[1]["qty"]) == (800, 720, 560, 2)


def test_bay_composition():
    r = engine.build_cabinet({"ref": "E1A-2", "type": "bay", "w": 900, "h": 2700, "d": 200, "drawers": 2,
                              "shelves": 3, "t": 20, "base_h": 900, "header_h": 300}, engine.DEFAULTS)
    assert (r["w"], r["h"], r["d"], r["upper_d"]) == (900, 2700, 500, 200)
    top = max(p["box"]["y"] + p["box"]["h"] for p in r["panels"])
    assert top == 2700
    by = {p["code"]: p for p in r["panels"]}
    assert by["UP-SHELF-1"]["l"] == 860 and by["UP-SHELF-1"]["w"] == 194
    spaces = sorted(p["box"]["y"] for p in r["panels"] if p["code"].startswith("UP-SHELF"))
    gaps = [round(b - a - 20) for a, b in zip(spaces, spaces[1:])]
    assert gaps == [355, 355]       # equal display spaces


def test_cut_sequence_valid():
    rows = [{"ref": f"B{i}", "type": "base", "w": 600, "h": 720, "d": 560, "doors": 2,
             "shelves": 1, "qty": 2} for i in range(1, 4)]
    res = engine.generate(rows)
    assert [c["idx"] for c in res["cabinets"]] == [0, 1, 2]
    total = 0
    for n in res["nesting"]:
        for sh in n["sheets"]:
            cuts = sh["cuts"]
            assert cuts and all(c["dir"] in "HV" for c in cuts), cuts
            assert [c["n"] for c in cuts] == list(range(1, len(cuts) + 1))
            for c in cuts:
                total += 1
                for p in sh["placed"]:
                    if c["dir"] == "H":
                        crosses = p["y"] < c["pos"] < p["y"] + p["h"] and p["x"] < c["to"] and p["x"] + p["w"] > c["from"]
                    else:
                        crosses = p["x"] < c["pos"] < p["x"] + p["w"] and p["y"] < c["to"] and p["y"] + p["h"] > c["from"]
                    assert not crosses, (c, p)
            # every piece ends up bounded: its right and bottom edges are cut lines or the kept trim
            xs = {c["pos"] for c in cuts if c["dir"] == "V"}
            ys = {c["pos"] for c in cuts if c["dir"] == "H"}
            for p in sh["placed"]:
                assert (p["x"] + p["w"] in xs) or p["x"] + p["w"] >= res["settings"]["sheet_l"] - res["settings"]["trim"] - 1, p
                assert (p["y"] + p["h"] in ys) or p["y"] + p["h"] >= res["settings"]["sheet_w"] - res["settings"]["trim"] - 1, p
    assert total > 20


def test_fixtures_match_hardware():
    from collections import Counter
    def hw(r, name):
        return sum(h["qty"] for h in r["hardware"] if h["item"].startswith(name))
    for cab in ({"ref": "B1", "type": "base", "w": 900, "h": 720, "d": 560, "doors": 2, "shelves": 1},
                {"ref": "DB1", "type": "drawer", "w": 600, "h": 720, "d": 560, "drawers": 3},
                {"ref": "T1", "type": "tall", "w": 600, "h": 2100, "d": 560, "doors": 2, "shelves": 3},
                {"ref": "E1", "type": "bay", "w": 900, "h": 2700, "d": 200, "drawers": 2, "shelves": 3,
                 "t": 20, "base_h": 900, "header_h": 300}):
        r = engine.build_cabinet(cab, engine.DEFAULTS)
        n = Counter(f["kind"] for f in r["fixtures"])
        assert n["hinge"] == hw(r, "Hinge"), (cab["ref"], n, r["hardware"])
        assert n["handle"] == hw(r, "Handle"), (cab["ref"], n)
        assert n["leg"] == hw(r, "Adjustable leg"), (cab["ref"], n)
        assert n["runner"] == 2 * hw(r, "Drawer runners"), (cab["ref"], n)
        assert n["pin"] == hw(r, "Shelf pin"), (cab["ref"], n)
        for f in r["fixtures"]:
            b = f["box"]
            assert -1 <= b["x"] and b["x"] + b["w"] <= r["w"] + 1, f
            assert -1 <= b["y"] and b["y"] + b["h"] <= r["h"] + 1, f


DRAWING = Path("/mnt/user-data/attachments/331786f5-6c4b-50ea-aac3-ea405a9141ca/4486c57d-Jani_Cosmetics_Working_Drawings_Lavington.pdf")


def test_reads_a1_drawing():
    if not DRAWING.exists():
        print("  (skipped: drawing not present)")
        return
    from backend import drawing
    res = drawing.read_drawing(str(DRAWING))
    assert [s["size_mm"] for s in res["sheets"]] == [[841, 594]] * 3          # A1
    bays = {r["ref"]: r for r in res["rows"]}
    assert (bays["E1A-2"]["w"], bays["E1A-2"]["h"], bays["E1A-2"]["shelves"]) == (900, 2700, 3)
    assert bays["E1A-1"]["w"] == 1080
    assert bays["E2B-1"]["h"] == 2938 and bays["E2A-1"]["base_h"] == 875
    assert {b["name"] for b in res["bespoke"]} >= {"Reception desk", "Product display table"}
    out = engine.generate(res["rows"])
    assert not out["errors"] and out["summary"]["cabinet_count"] == len(res["rows"])


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
