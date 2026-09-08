#!/usr/bin/env python3
"""Show CLI-origin tenant-restriction blocks from a network-proxy archive.

Filters POST /v1/messages flows carrying the Claude Code CLI user-agent, prints
the BEFORE (200, no injected header) and AFTER (403, injected
anthropic-allowed-org-ids) so the server-side reversible block is visible with
the real Anthropic request_id and error body.

Usage: cli_tenant.py <env>/<archive-folder>
"""
import sys, os, glob, json
from archive_common import UA_CLI, archive_dir_from_argv, repo_root, resolve  # 공통(중복 제거)

UA = UA_CLI
HDR = "anthropic-allowed-org-ids"




def hdr_get(h, name):
    if isinstance(h, dict):
        for k, v in h.items():
            if k.lower() == name:
                return v
    elif isinstance(h, list):
        for it in h:
            if isinstance(it, dict) and str(it.get("name", "")).lower() == name:
                return it.get("value")
            if isinstance(it, (list, tuple)) and len(it) == 2 and str(it[0]).lower() == name:
                return it[1]
    return None


def main():
    d = archive_dir_from_argv("cli_tenant.py")
    seen = set()
    rows = []
    for f in sorted(glob.glob(os.path.join(d, "[0-9]*.json"))):
        try:
            fl = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        rh = fl.get("req_headers") or {}
        if UA not in json.dumps(rh):
            continue
        if fl.get("method") != "POST" or "/v1/messages" not in fl.get("path", ""):
            continue
        inj = hdr_get(rh, HDR)
        reqid = hdr_get(fl.get("resp_headers") or {}, "request-id")
        key = (fl.get("status"), reqid)
        if key in seen:
            continue
        seen.add(key)
        rows.append((fl.get("status"), inj, reqid, str(fl.get("resp_body"))[:240]))
    print("=== CLI POST /v1/messages — tenant-restriction (server-side) ===")
    for status, inj, reqid, body in rows:
        tag = "AFTER (rule on) " if inj else "BEFORE (no rule)"
        print("\n[%s]  HTTP %s" % (tag, status))
        print("  injected anthropic-allowed-org-ids = %s" % (inj if inj else "(none)"))
        print("  Anthropic request-id = %s" % reqid)
        print("  resp_body: %s" % body)


if __name__ == "__main__":
    main()
