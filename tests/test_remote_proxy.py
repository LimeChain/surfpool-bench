"""Exercise HTTP write denial without ever connecting to a public datasource."""
import importlib.util
import json
from pathlib import Path
import threading
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import pytest
from http.server import ThreadingHTTPServer

@pytest.fixture
def proxy(tmp_path,monkeypatch):
    # Module startup creates /records, so import with a patched Path.mkdir and
    # replace ROOT immediately; no filesystem access to a privileged directory.
    source=Path(__file__).parents[1]/'src/surfbench/remote_proxy.py'
    spec=importlib.util.spec_from_file_location('tested_proxy',source)
    module=importlib.util.module_from_spec(spec)
    with monkeypatch.context() as patch:
        patch.setattr(Path,'mkdir',lambda *args,**kwargs:None)
        spec.loader.exec_module(module)
    module.ROOT=tmp_path
    calls=[]
    def forbidden_network(*args,**kwargs):calls.append(args);raise AssertionError('Write reached upstream!')
    monkeypatch.setattr(module,'urlopen',forbidden_network)
    server=ThreadingHTTPServer(('127.0.0.1',0),module.Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    yield f'http://127.0.0.1:{server.server_port}',calls,tmp_path
    server.shutdown();server.server_close();thread.join()

@pytest.mark.parametrize('method',['sendTransaction','requestAirdrop','simulateTransaction','surfnet_setAccount','unknown'])
def test_non_read_methods_never_reach_upstream(proxy,method):
    url,calls,path=proxy
    request=Request(url,json.dumps({'jsonrpc':'2.0','id':12,'method':method,'params':[]}).encode(),{'Content-Type':'application/json'})
    with pytest.raises(HTTPError) as error:urlopen(request,timeout=2)
    assert error.value.code==403 and calls==[]
    record=json.loads((path/'remote.jsonl').read_text());assert record['blocked'] is True
