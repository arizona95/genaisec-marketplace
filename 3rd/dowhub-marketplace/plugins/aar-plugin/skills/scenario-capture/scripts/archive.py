"""Archive-based packet analysis — analyze a network-proxy capture from its
**on-disk archive folder**, never the web UI.

Methodology (what the scenarios now use):
  1. capture traffic through the proxy
  2. snapshot it:   python archive.py export <env> <folder>
       → POST /api/v1/envs/<env>/network-proxy/api/export
       → writes runs/envs/<env>/captures/archives/<folder>/NNNN_*.json (one per flow)
  3. analyse the folder with bash/python — the sub-commands below. Every number
     is recomputed from the real JSON files, so a report that embeds this output
     cannot drift from what was actually captured.

  hosts   <archive>              egress allowlist: scheme://host (+port) · count · statuses
  hosts_tsv <archive>            ↑ 를 순수 TSV(헤더無)로: endpoint·건수·method·주요경로·상태
                                 → report.py 의 table 블록 cmd 로 써서 egress 목적지 '표' 렌더
  status  <archive>              status-code distribution
  grep    <archive> <regex> [field]   flows whose field (url/host/req_body/resp_body/
                                       req_headers/resp_headers/any, default=any) matches
  header  <archive> <name>       flows carrying header <name>, with its value (req+resp)
  blocked <archive>              flows blocked/denied: status 451/403 + rule_name / error_code
  convo   <archive>              completion flows: decrypted prompt (req_body) + reply (resp_body)

<archive> may be a path or "<env>/<folder>" (resolved under runs/envs).
"""
import sys, os, json, glob, re, urllib.request, collections, signal

# 분석 cmd 는 리포트에서 `archive.py ... | head -N` / `| grep` 처럼 파이프된다.
# 뒤쪽(head)이 먼저 닫히면 print() 루프가 BrokenPipeError 를 던지고, 그 traceback 이
# report.py 의 stdout+stderr 캡처를 통해 HTML 에 그대로 박혔다(5개 리포트 오염).
# 표준 유닉스 도구(cat/grep)처럼 SIGPIPE 에 조용히 종료하도록 기본 처리로 되돌린다.
try:
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
except (AttributeError, ValueError):
    pass  # SIGPIPE 없는 플랫폼(예: Windows)

API = os.environ.get("AGENTREVIEW_API", "http://localhost:8080")


def _repo_root():
    # .../SDSreviewBLUE/aar-plugin/skills/scenario-capture/scripts/archive.py
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))


def _resolve(archive):
    if os.path.isdir(archive):
        return archive
    p = os.path.join(_repo_root(), "runs", "envs", *archive.split("/"))
    # allow "<env>/<folder>" -> runs/envs/<env>/captures/archives/<folder>
    if not os.path.isdir(p) and "/" in archive:
        env, folder = archive.split("/", 1)
        p = os.path.join(_repo_root(), "runs", "envs", env, "captures", "archives", folder)
    if not os.path.isdir(p):
        sys.exit(f"archive not found: {archive}  (looked under runs/envs)")
    return p


def _flows(archive):
    d = _resolve(archive)
    for f in sorted(glob.glob(os.path.join(d, "[0-9]*.json"))):
        try:
            yield json.load(open(f, encoding="utf-8"))
        except Exception:
            continue


def _scheme(d):
    u = str(d.get("url", ""))
    return u.split("://", 1)[0] if "://" in u else "?"


def _port(scheme):
    return {"https": 443, "http": 80}.get(scheme, "?")


def _headers_items(h):
    """Headers may be a dict or a list of [k,v] / {name,value} pairs."""
    if isinstance(h, dict):
        return list(h.items())
    out = []
    for it in (h or []):
        if isinstance(it, (list, tuple)) and len(it) == 2:
            out.append((str(it[0]), str(it[1])))
        elif isinstance(it, dict):
            out.append((str(it.get("name", "")), str(it.get("value", ""))))
    return out


def cmd_hosts(archive):
    agg = collections.defaultdict(lambda: [0, collections.Counter()])
    for d in _flows(archive):
        sch = _scheme(d)
        key = f"{sch}://{d.get('host')}:{_port(sch)}"
        agg[key][0] += 1
        agg[key][1][d.get("status")] += 1
    rows = sorted(agg.items(), key=lambda kv: -kv[1][0])
    print(f"{'flows':>6}  endpoint (scheme://host:port){'':21}status codes")
    print("-" * 78)
    for ep, (n, st) in rows:
        sts = " ".join(f"{k}×{v}" for k, v in st.most_common())
        print(f"{n:6}  {ep:<48} {sts}")
    print("-" * 78)
    print(f"{sum(n for _, (n, _) in rows):6}  total · {len(rows)} distinct endpoints")


def cmd_hosts_tsv(archive):
    """egress 목적지를 순수 TSV 로(헤더·장식 없음) — report.py 의 table 블록이 실행해 표로 렌더.
    컬럼: 목적지(scheme://host:port) · 건수 · method · 주요경로(distinct 최대3) · 상태코드."""
    agg = collections.defaultdict(lambda: [0, collections.Counter(), set(), set()])
    for d in _flows(archive):
        sch = _scheme(d)
        key = f"{sch}://{d.get('host')}:{_port(sch)}"
        a = agg[key]
        a[0] += 1
        a[1][d.get("status")] += 1
        if d.get("method"):
            a[2].add(d.get("method"))
        p = str(d.get("path", "") or "")
        if p:
            a[3].add(p[:48])
    for ep, (n, st, methods, paths) in sorted(agg.items(), key=lambda kv: -kv[1][0]):
        sts = " ".join(f"{k}×{v}" for k, v in st.most_common())
        meth = ",".join(sorted(m for m in methods if m))
        pth = " ".join(sorted(paths)[:3]) or "/"
        print(f"{ep}\t{n}\t{meth}\t{pth}\t{sts}")


def cmd_status(archive):
    c = collections.Counter(d.get("status") for d in _flows(archive))
    for s, n in c.most_common():
        print(f"  {str(s):>5} × {n}")
    print(f"  total {sum(c.values())}")


def cmd_grep(archive, pat, field="any"):
    rx = re.compile(pat, re.I)
    fields = [field] if field != "any" else ["url", "host", "req_body", "resp_body", "req_headers", "resp_headers"]
    n = 0
    for d in _flows(archive):
        blob = " ".join(json.dumps(d.get(f), ensure_ascii=False) if isinstance(d.get(f), (dict, list)) else str(d.get(f, "")) for f in fields)
        m = rx.search(blob)
        if m:
            n += 1
            ctx = blob[max(0, m.start() - 40):m.end() + 60].replace("\n", " ")
            print(f"  {d.get('status')} {d.get('method'):4} {d.get('host')}{str(d.get('path',''))[:40]}")
            print(f"       …{ctx}…")
    print(f"-- {n} match(es) for /{pat}/ in {field}")


def cmd_header(archive, name):
    nl = name.lower()
    n = 0
    for d in _flows(archive):
        for side in ("req_headers", "resp_headers"):
            for k, v in _headers_items(d.get(side)):
                if k.lower() == nl:
                    n += 1
                    print(f"  [{side.split('_')[0]}] {d.get('status')} {d.get('method'):4} {d.get('host')} :: {k}: {v}")
    print(f"-- {n} flow-header occurrence(s) of '{name}'")


def cmd_blocked(archive):
    n = 0
    for d in _flows(archive):
        st = d.get("status")
        if st not in (451, 403, 401):
            continue
        body = str(d.get("resp_body", ""))
        rule = re.search(r'"rule_name"\s*:\s*"([^"]+)"', body)
        ec = re.search(r'"error_code"\s*:\s*"([^"]+)"', body)
        blk = re.search(r'X-AgentReview-Block', json.dumps(d.get("resp_headers"), ensure_ascii=False), re.I)
        tag = []
        if rule: tag.append(f"rule_name={rule.group(1)}")
        if ec: tag.append(f"error_code={ec.group(1)}")
        if blk: tag.append("X-AgentReview-Block")
        n += 1
        print(f"  {st} {d.get('method'):4} {d.get('host')}{str(d.get('path',''))[:45]}")
        if tag:
            print(f"       → {'  '.join(tag)}")
        if body.strip():
            print(f"       resp_body: {body[:160]}")
    print(f"-- {n} blocked/denied flow(s) (status 451/403/401)")


def _sse_text(body):
    """Reconstruct assistant text from an SSE completion stream."""
    out = []
    for line in str(body).splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        try:
            ev = json.loads(line[5:].strip())
        except Exception:
            continue
        for k in ("completion", "text"):
            if isinstance(ev.get(k), str):
                out.append(ev[k])
        d = ev.get("delta") or {}
        if isinstance(d.get("text"), str):
            out.append(d["text"])
    return "".join(out)


def cmd_convo(archive):
    rx = re.compile(r"completion|/v1/messages|/v1/chat|chat_conversations.*completion", re.I)
    n = 0
    for d in _flows(archive):
        if not rx.search(str(d.get("url", "")) + str(d.get("path", ""))):
            continue
        n += 1
        print(f"\n● {d.get('method')} {d.get('host')}{d.get('path')}  [{d.get('status')}]")
        # prompt
        prompt = ""
        try:
            j = json.loads(d.get("req_body") or "{}")
            prompt = j.get("prompt") or json.dumps(j.get("messages", j), ensure_ascii=False)
        except Exception:
            prompt = str(d.get("req_body", ""))
        print(f"  PROMPT (req_body, 복호화 평문): {prompt[:300]}")
        # reply
        reply = _sse_text(d.get("resp_body", "")) or str(d.get("resp_body", ""))
        print(f"  REPLY  (resp_body, 복호화 평문): {reply[:300]}")
    print(f"\n-- {n} completion flow(s)")


def cmd_tools(archive):
    """Audit trail of tool/MCP/connector usage as seen at the proxy (decrypted)."""
    mcp_opt = 0
    mcp_rpc, conn, inchat = [], [], []
    for d in _flows(archive):
        url, path, host = str(d.get("url", "")), str(d.get("path", "")), d.get("host", "")
        ts = str(d.get("time") or "")[11:19] or "?"
        if host == "mcp-proxy.anthropic.com" or "/v1/mcp/" in path:
            if d.get("method") == "OPTIONS":
                mcp_opt += 1
                continue
            srv = (re.search(r"(mcpsrv_[0-9A-Za-z]+)", url + path) or [None, "?"])[1]
            meth = client = ec = ""
            try:
                j = json.loads(d.get("req_body") or "{}")
                meth = j.get("method", "")
                client = (((j.get("params") or {}).get("clientInfo")) or {}).get("name", "")
            except Exception:
                pass
            m = re.search(r'"error_code"\s*:\s*"([^"]+)"', str(d.get("resp_body", "")))
            if m: ec = m.group(1)
            mcp_rpc.append((ts, d.get("status"), srv, meth, client, ec))
        elif re.search(r"/v1/code|/github|/connector|integration", url + path, re.I):
            conn.append((ts, d.get("status"), d.get("method"), host, path[:46],
                         str(d.get("req_body", ""))[:140], str(d.get("resp_body", ""))[:140]))
        if re.search(r"completion|/v1/messages", url + path, re.I):
            blob = str(d.get("req_body", "")) + str(d.get("resp_body", ""))
            for kind in ("tool_use", "tool_result"):
                for mm in re.finditer(r'"type"\s*:\s*"%s".{0,120}' % kind, blob):
                    inchat.append((ts, kind, mm.group(0)[:130]))

    print("【 MCP (Model Context Protocol) — 프록시가 본 것 】")
    print(f"  · OPTIONS preflight {mcp_opt}건 — 앱이 등록된 MCP 서버 다수를 탐침(서버 ID 전수 노출)")
    print(f"  · JSON-RPC 호출 {len(mcp_rpc)}건 (메서드·클라이언트·인증결과까지 평문):")
    for ts, st, srv, meth, cl, ec in mcp_rpc[:18]:
        print(f"      {ts} {st} {srv} method={meth or '-'} client={cl or '-'}{('  → '+ec) if ec else ''}")

    print("\n【 Connector 호출 — 요청 인자/결과 평문 】")
    for ts, st, meth, host, path, rb, sb in conn[:6]:
        print(f"  {ts} {st} {meth} {host}{path}")
        if rb.strip(): print(f"      req : {rb}")
        if sb.strip(): print(f"      resp: {sb}")
    print(f"  ({len(conn)} connector flow)")

    print("\n【 In-chat tool_use / tool_result (completion 본문 내부) 】")
    if inchat:
        for ts, kind, snip in inchat[:10]:
            print(f"  {ts} {kind}: {snip}")
    else:
        print("  (이 캡처엔 0건 — 모델이 채팅 중 직접 툴을 호출한 completion 이 없었음.")
        print("   그런 대화를 캡처하면 tool_use/tool_result 도 동일하게 평문으로 잡힘.)")


def cmd_export(env, folder):
    body = json.dumps({"folder": folder}).encode()
    req = urllib.request.Request(
        f"{API}/api/v1/envs/{env}/network-proxy/api/export",
        data=body, headers={"Content-Type": "application/json"}, method="POST")
    r = json.load(urllib.request.urlopen(req, timeout=20))
    path = os.path.join(_repo_root(), "runs", "envs", env, "captures", "archives", r.get("folder", folder))
    print(f"archived {r.get('count')} flows → {path}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    cmd, rest = a[0], a[1:]
    fn = {"export": cmd_export, "hosts": cmd_hosts, "hosts_tsv": cmd_hosts_tsv,
          "status": cmd_status, "grep": cmd_grep, "header": cmd_header,
          "blocked": cmd_blocked, "convo": cmd_convo, "tools": cmd_tools}.get(cmd)
    if not fn:
        sys.exit(__doc__)
    fn(*rest)
