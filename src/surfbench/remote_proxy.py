"""Read-only recording mainnet datasource. Runs in a separate trusted container."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import time
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from urllib.parse import urlparse

UPSTREAM=os.environ.get('SURFBENCH_UPSTREAM_RPC','https://api.mainnet-beta.solana.com')
if urlparse(UPSTREAM).scheme!='https':raise ValueError('Live upstream must use authenticated HTTPS')
ALLOWED=frozenset({'getAccountInfo','getMultipleAccounts','getEpochInfo','getEpochSchedule','getSlot',
    'getBlockTime','getVersion','getGenesisHash','getLatestBlockhash','getMinimumBalanceForRentExemption',
    'getHealth','getBlockHeight','getRecentPerformanceSamples','getFees','getFeeForMessage','isBlockhashValid'})
ROOT=Path('/records');ROOT.mkdir(exist_ok=True);LOCK=threading.Lock()


def append(record):
    with LOCK:
        with (ROOT/'remote.jsonl').open('a') as f:
            f.write(json.dumps(record)+'\n');f.flush();os.fsync(f.fileno())


class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def reply(self,status,body):
        self.send_response(status);self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_GET(self):
        self.reply(200 if self.path=='/health' else 404,b'{"healthy":true}' if self.path=='/health' else b'{}')
    def do_POST(self):
        record={'started':time.time(),'source_host':urlparse(UPSTREAM).hostname,'source_tls_verified':True,'mode':'live'}
        try:
            n=int(self.headers.get('Content-Length','0'))
            if n<1 or n>1_000_000:raise ValueError('Invalid request size')
            payload=json.loads(self.rfile.read(n));record['request']=payload
            if not isinstance(payload,dict) or payload.get('method') not in ALLOWED:
                record['blocked']=True
                body=json.dumps({'jsonrpc':'2.0','id':payload.get('id') if isinstance(payload,dict) else None,
                    'error':{'code':-32601,'message':'Read-only datasource: method is not allowed'}}).encode()
                status=403
            else:
                request=Request(UPSTREAM,json.dumps(payload).encode(),{'Content-Type':'application/json','Accept-Encoding':'identity'})
                try:
                    with urlopen(request,timeout=20) as response:status=response.status;body=response.read(8_000_001)
                except HTTPError as error:status=error.code;body=error.read(8_000_001)
                if len(body)>8_000_000:raise ValueError('Upstream response too large')
                record['response']=json.loads(body);record['http_status']=status
            record['finished']=time.time();append(record);self.reply(status,body)
        except Exception as error:
            record['infrastructure_error']=type(error).__name__+': '+str(error)
            record['finished']=time.time();append(record)
            self.reply(502,b'{"jsonrpc":"2.0","id":null,"error":{"code":-32000,"message":"Upstream infrastructure failure"}}')
    def log_message(self,*args):pass

if __name__=='__main__':
    (ROOT/'remote.jsonl').touch()
    ThreadingHTTPServer(('0.0.0.0',8888),Handler).serve_forever()
