"""Dependency-free MCP stdio bridge for Cabinet Workshop.
Run with: python launch_mcp.py
"""
from __future__ import annotations
import csv, json, sys, http.client
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from backend import engine

NAME = "cabinet-workshop-cutlist"
PORTS = range(19723, 19744)

def api(port, command, parameters=None, timeout=2):
    body = {"command": "API." + command}
    if parameters is not None: body["parameters"] = parameters
    connection=http.client.HTTPConnection("127.0.0.1",port,timeout=timeout)
    try:
        connection.request("POST","/",body=json.dumps(body).encode(),headers={"Content-Type":"application/json"})
        response=connection.getresponse(); data=json.loads(response.read())
    finally: connection.close()
    if not data.get("succeeded"): raise RuntimeError(f"Archicad {command}: {data.get('error',{}).get('message','request failed')}")
    return data.get("result", {})
def instances():
    def probe(port):
        try:
            if api(port, "IsAlive", timeout=.35).get("isAlive"):
                info=api(port,"GetProductInfo")
                return {"port":port,"version":info.get("version"),"build":info.get("buildNumber")}
        except Exception: pass
        return None
    with ThreadPoolExecutor(max_workers=21) as pool: return [x for x in pool.map(probe, PORTS) if x]

def read_archicad(port=None):
    found=[{"port":port}] if port else instances()
    if len(found)!=1: raise RuntimeError("No Archicad JSON API found on ports 19723-19743; enable the API add-on and keep a project open." if not found else f"Several Archicad instances found: {found}; pass a port.")
    port=found[0]["port"]
    guids=[e["elementId"]["guid"] for e in api(port,"GetSelectedElements").get("elements",[])]
    if not guids: return {"cabinets":[],"notes":["Select cabinet objects in Archicad first."]}
    boxes=[]
    for i in range(0,len(guids),500):
        els=[{"elementId":{"guid":g}} for g in guids[i:i+500]]
        boxes.extend(api(port,"Get3DBoundingBoxes",{"elements":els}).get("boundingBoxes3D",[]))
    rows=[]
    for gid,entry in zip(guids,boxes):
        b=(entry or {}).get("boundingBox3D")
        if not b: continue
        dx=(b["xMax"]-b["xMin"])*1000; dy=(b["yMax"]-b["yMin"])*1000; h=(b["zMax"]-b["zMin"])*1000
        w,d=max(dx,dy),min(dx,dy)
        if min(w,h,d)<150: continue
        typ="tall" if h>=1800 else "wall" if b["zMin"]>=.9 and h<=1300 else "base"
        rows.append({"ref":f"AC-{gid[:8]}","type":typ,"w":round(w),"h":round(h),"d":round(d),"qty":1,"doors":0,"drawers":0,"shelves":0,"flags":["dimensions from bounding box; inspect rotated objects","cabinet type and internal counts are guesses"]})
    return {"cabinets":rows,"notes":["Read-only Archicad connection. Review inferred types and counts before production."],"port":port}

TOOLS=[
 {"name":"archicad_instances","description":"Find Archicad JSON API instances on this computer.","inputSchema":{"type":"object","properties":{}}},
 {"name":"archicad_cabinets","description":"Read selected Archicad objects as cabinet estimates. Read-only; inferred classifications and counts require review.","inputSchema":{"type":"object","properties":{"port":{"type":"integer"}}}},
 {"name":"cutlist_generate","description":"Generate a cut list, board nesting estimate, edge banding and hardware from cabinet rows (all sizes in mm).","inputSchema":{"type":"object","properties":{"cabinets":{"type":"array","items":{"type":"object"}},"settings":{"type":"object"}},"required":["cabinets"]}},
 {"name":"cutlist_export","description":"Write cutlist.csv, hardware.csv and banding.csv to the chosen output directory.","inputSchema":{"type":"object","properties":{"cabinets":{"type":"array","items":{"type":"object"}},"out_dir":{"type":"string"},"settings":{"type":"object"}},"required":["cabinets","out_dir"]}},
]

def run_tool(name,args):
    if name=="archicad_instances": return instances()
    if name=="archicad_cabinets": return read_archicad(args.get("port"))
    if name in ("cutlist_generate","cutlist_export"):
        result=engine.generate(args.get("cabinets",[]),args.get("settings") or {})
        if name=="cutlist_generate": return result
        folder=Path(args["out_dir"]).expanduser(); folder.mkdir(parents=True,exist_ok=True); files=[]
        for key in ("cutlist","hardware","banding"):
            rows=result[key]
            if not rows: continue
            path=folder/(key+".csv")
            with path.open("w",newline="",encoding="utf-8-sig") as f:
                writer=csv.DictWriter(f,list(dict.fromkeys(k for row in rows for k,v in row.items() if not isinstance(v,(dict,list)))),extrasaction="ignore"); writer.writeheader(); writer.writerows(rows)
            files.append(str(path))
        return {"files":files,"summary":result["summary"],"errors":result["errors"]}
    raise ValueError("Unknown tool: "+name)

def send(obj): sys.stdout.write(json.dumps(obj,separators=(",",":"),ensure_ascii=False)+"\n"); sys.stdout.flush()
def handle(msg):
    method=msg.get("method"); ident=msg.get("id")
    if method=="notifications/initialized" or method=="notifications/cancelled": return
    if ident is None: return
    if method=="initialize":
        send({"jsonrpc":"2.0","id":ident,"result":{"protocolVersion":"2024-11-05","capabilities":{"tools":{"listChanged":False}},"serverInfo":{"name":NAME,"version":"0.1.0"}}})
    elif method=="ping": send({"jsonrpc":"2.0","id":ident,"result":{}})
    elif method=="tools/list": send({"jsonrpc":"2.0","id":ident,"result":{"tools":TOOLS}})
    elif method=="tools/call":
        params=msg.get("params",{})
        try:
            result=run_tool(params.get("name"),params.get("arguments") or {})
            send({"jsonrpc":"2.0","id":ident,"result":{"content":[{"type":"text","text":json.dumps(result,ensure_ascii=False)}],"structuredContent":result,"isError":False}})
        except Exception as exc:
            send({"jsonrpc":"2.0","id":ident,"result":{"content":[{"type":"text","text":str(exc)}],"isError":True}})
    else: send({"jsonrpc":"2.0","id":ident,"error":{"code":-32601,"message":"Method not found"}})

def main():
    for line in sys.stdin:
        try: handle(json.loads(line))
        except Exception as exc: send({"jsonrpc":"2.0","id":None,"error":{"code":-32700,"message":str(exc)}})
if __name__=="__main__": main()

