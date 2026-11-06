"""End-to-end smoke test for the built-in stdio MCP bridge (stdlib only)."""
import json, subprocess, sys
p=subprocess.Popen([sys.executable,"launch_mcp.py"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
def request(i,method,params=None):
    msg={"jsonrpc":"2.0","id":i,"method":method}
    if params is not None: msg["params"]=params
    p.stdin.write(json.dumps(msg)+"\n"); p.stdin.flush()
    return json.loads(p.stdout.readline())
try:
    assert request(1,"initialize")["result"]["serverInfo"]["name"]=="cabinet-workshop-cutlist"
    p.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n'); p.stdin.flush()
    tools=request(2,"tools/list")["result"]["tools"]
    assert {t["name"] for t in tools}>={"archicad_instances","archicad_cabinets","cutlist_generate","cutlist_export"}
    out=request(3,"tools/call",{"name":"cutlist_generate","arguments":{"cabinets":[{"ref":"SMOKE","type":"base","w":600,"h":720,"d":560,"qty":1,"doors":2,"shelves":1}]}})["result"]["structuredContent"]
    assert out["summary"]["cabinet_count"]==1 and not out["errors"] and out["hardware"]
    print("MCP stdio handshake, tool listing, and cutlist generation passed.")
finally:
    p.terminate(); p.wait(timeout=5)
