#!/usr/bin/env python3
"""CLI-origin egress enumeration from a network-proxy archive.

Filters flows whose req_headers carry the Claude Code CLI user-agent
(claude-cli/...) so Desktop GUI traffic on the same VM is excluded, then
prints the destination-host table and the api.anthropic.com endpoint breakdown.

Usage: cli_egress.py <env>/<archive-folder>
"""
import sys, os, glob, json, collections
from archive_common import UA_CLI, archive_dir_from_argv, repo_root, resolve  # 공통(중복 제거)

UA_MARK = UA_CLI




def main():
    d = archive_dir_from_argv("cli_egress.py")
    hosts = collections.Counter()
    status = collections.defaultdict(collections.Counter)
    paths = collections.Counter()
    for f in sorted(glob.glob(os.path.join(d, "[0-9]*.json"))):
        try:
            fl = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if UA_MARK not in json.dumps(fl.get("req_headers") or {}):
            continue
        h = fl.get("host", "")
        hosts[h] += 1
        status[h][fl.get("status")] += 1
        paths[fl.get("method", "") + " " + fl.get("path", "").split("?")[0]] += 1
    print("=== CLI-origin egress (claude-cli user-agent only) ===")
    for h, c in hosts.most_common():
        print("  %-28s %4d flows   statuses=%s" % (h, c, dict(status[h])))
    print("  total CLI flows: %d" % sum(hosts.values()))
    print()
    print("=== api.anthropic.com endpoints (CLI) ===")
    for p, c in paths.most_common():
        print("  %3d  %s" % (c, p))


if __name__ == "__main__":
    main()
