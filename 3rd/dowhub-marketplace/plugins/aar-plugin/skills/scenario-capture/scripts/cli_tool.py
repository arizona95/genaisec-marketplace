#!/usr/bin/env python3
"""Extract the CLI in-chat tool-use audit trail from a network-proxy archive.

Shows, from the decrypted CLI POST /v1/messages bodies, the tools[] catalog the
CLI advertises, the model's tool_use request (Bash + command), and the
tool_result fed back — i.e. how Claude Code tool usage appears on the wire.

Usage: cli_tool.py <env>/<archive-folder>
"""
import sys, os, glob, json, re
from archive_common import UA_CLI, archive_dir_from_argv, repo_root, resolve  # 공통(중복 제거)

UA = UA_CLI




def main():
    d = archive_dir_from_argv("cli_tool.py")
    counts = {"tools[]": 0, "tool_use": 0, "tool_result": 0}
    best = None
    for f in sorted(glob.glob(os.path.join(d, "[0-9]*.json"))):
        try:
            fl = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if UA not in json.dumps(fl.get("req_headers") or {}):
            continue
        if fl.get("method") != "POST" or "/v1/messages" not in fl.get("path", ""):
            continue
        req = str(fl.get("req_body"))
        if '"tools"' in req:
            counts["tools[]"] += 1
        if "tool_use" in req:
            counts["tool_use"] += 1
        if "tool_result" in req:
            counts["tool_result"] += 1
        if "tool_use" in req and "tool_result" in req and best is None:
            best = req
    print("=== CLI POST /v1/messages flows carrying tool audit (claude-cli UA) ===")
    print("  flows with tools[] catalog : %d" % counts["tools[]"])
    print("  flows with tool_use block  : %d" % counts["tool_use"])
    print("  flows with tool_result     : %d" % counts["tool_result"])
    if best:
        names = sorted(set(re.findall(r'"name":"([A-Z][A-Za-z]+)"', best)))
        print("\ntools[] catalog advertised by CLI:", ", ".join(names[:20]))
        tu = re.search(r'"type":"tool_use","id":"[^"]+","name":"Bash","input":\{[^}]{0,120}', best)
        tr = re.search(r'"type":"tool_result","content":"[^"]{0,80}', best)
        print("\ntool_use  (model -> tool):")
        print("  " + (tu.group(0) if tu else "(not found)"))
        print("\ntool_result (tool -> model):")
        print("  " + (tr.group(0) if tr else "(not found)"))


if __name__ == "__main__":
    main()
