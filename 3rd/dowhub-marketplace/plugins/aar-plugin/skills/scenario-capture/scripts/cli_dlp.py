#!/usr/bin/env python3
"""Show CLI-origin DLP (451) blocks vs passes from a network-proxy archive.

Filters flows carrying the Claude Code CLI user-agent, then prints the locally
blocked (451, {blocked:true, rule_name, matched}) requests and a few passing
(200) control requests so the shape-regex DLP control is visible. The request
never reaches Anthropic on a 451.

Usage: cli_dlp.py <env>/<archive-folder>
"""
import sys, os, glob, json
from archive_common import UA_CLI, archive_dir_from_argv, repo_root, resolve  # 공통(중복 제거)

UA = UA_CLI




def main():
    d = archive_dir_from_argv("cli_dlp.py")
    blocked = []
    passed = []
    for f in sorted(glob.glob(os.path.join(d, "[0-9]*.json"))):
        try:
            fl = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if UA not in json.dumps(fl.get("req_headers") or {}):
            continue
        s = fl.get("status")
        ep = fl.get("method") + " " + fl.get("path", "").split("?")[0]
        if s == 451:
            blocked.append((ep, str(fl.get("resp_body"))[:260]))
        elif s == 200:
            passed.append(ep)
    print("=== CLI requests BLOCKED locally (HTTP 451, never reached Anthropic) ===")
    seen = set()
    for ep, body in blocked:
        if body in seen:
            continue
        seen.add(body)
        print("\n[BLOCKED 451] %s" % ep)
        print("  %s" % body)
    print("\n=== CLI control requests that PASSED (no sensitive shape in body) ===")
    import collections
    c = collections.Counter(passed)
    for ep, n in c.most_common():
        print("  %3d x 200  %s" % (n, ep))
    print("\nsummary: %d blocked(451) flows, %d passed(200) flows" % (len(blocked), len(passed)))


if __name__ == "__main__":
    main()
