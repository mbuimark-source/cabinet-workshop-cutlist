import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from backend.engine import generate
r=generate([{"ref":"A","type":"base","w":600,"h":720,"d":560,"doors":2,"qty":2,"shelves":1}])
assert r["summary"]["board_area_m2"]==round(sum(x["total_area_m2"] for x in r["cutlist"]),4)
assert all(x["total_area_m2"]==round(x["area_m2"]*x["qty"],4) for x in r["cutlist"])
print("Per-part and total board area calculations passed.")
