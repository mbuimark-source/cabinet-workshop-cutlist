"""Adapter mapping test with mocked Archicad JSON API responses (no socket needed)."""
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import cutlist_mcp
GUID="12345678-0000-0000-0000-000000000000"
def fake_api(port, command, parameters=None, timeout=2):
    assert port==19723
    if command=="GetSelectedElements": return {"elements":[{"elementId":{"guid":GUID}}]}
    if command=="Get3DBoundingBoxes": return {"boundingBoxes3D":[{"boundingBox3D":{"xMin":0,"yMin":0,"zMin":0,"xMax":.6,"yMax":.56,"zMax":.72}}]}
    raise AssertionError(command)
with patch.object(cutlist_mcp,"api",side_effect=fake_api):
    result=cutlist_mcp.read_archicad(19723)
assert result["cabinets"][0]["w"]==600 and result["cabinets"][0]["h"]==720 and result["cabinets"][0]["d"]==560
assert result["cabinets"][0]["flags"]
print("Archicad selection/bounding-box mapping passed against mocked JSON API responses.")
