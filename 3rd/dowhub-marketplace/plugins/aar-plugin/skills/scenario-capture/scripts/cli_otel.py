#!/usr/bin/env python3
"""Query the env's Loki log-server for Claude Code CLI OTel telemetry.

Proves CLI OTel export reaches the central log server: lists the service_name
label values and the Claude Code event_name breakdown with sample attributes
(cost_usd, duration_ms, tokens) pulled live from Loki at report-build time.

Usage: cli_otel.py [loki_base]   (default http://34.50.14.210:3100)
"""
import sys, json, time, urllib.parse, urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://34.50.14.210:3100"


def get(path, params=None):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=12) as r:
        return json.load(r)


def main():
    print("Loki log-server:", BASE)
    labels = get("/loki/api/v1/labels").get("data", [])
    print("labels:", labels)
    svcs = get("/loki/api/v1/label/service_name/values").get("data", [])
    print("service_name values:", svcs)
    if "claude-code" not in svcs:
        print("!! claude-code service not found in Loki")
        return
    now = int(time.time()) * 1_000_000_000
    start = (int(time.time()) - 3600) * 1_000_000_000
    res = get("/loki/api/v1/query_range", {
        "query": '{service_name="claude-code"}',
        "start": str(start), "end": str(now), "limit": "50",
    }).get("data", {}).get("result", [])
    from collections import Counter
    events = Counter()
    sample = None
    for s in res:
        st = s.get("stream", {})
        ev = st.get("event_name", "?")
        events[ev] += len(s.get("values", []))
        if ev == "api_request" and sample is None:
            sample = st
    print("\nservice_name=claude-code event_name breakdown (last 1h):")
    for ev, n in events.most_common():
        print("  %4d  claude_code.%s" % (n, ev))
    if sample:
        keys = [k for k in ("model", "cost_usd", "duration_ms", "input_tokens",
                            "output_tokens", "cache_read_tokens", "terminal_type",
                            "user_account_uuid", "organization_id")
                if k in sample]
        print("\nsample api_request attributes (selected):")
        for k in keys:
            print("  %-22s = %s" % (k, sample[k]))


if __name__ == "__main__":
    main()
