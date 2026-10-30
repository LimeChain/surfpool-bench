from surfbench.wire import http_messages

def test_http_pipelining_and_chunked_responses():
    a=b'{"method":"surfnet_setAccount","params":[]}'
    b=b'{"result":null}'
    wire=b'POST / HTTP/1.1\r\nContent-Length: '+str(len(a)).encode()+b'\r\n\r\n'+a
    wire+=b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n'+hex(len(b))[2:].encode()+b'\r\n'+b+b'\r\n0\r\n\r\n'
    messages=http_messages(wire)
    assert messages[0]['body']['method']=='surfnet_setAccount'
    assert messages[1]['body']=={'result':None}

def test_truncated_and_invalid_payloads_never_become_evidence():
    assert http_messages(b'POST / HTTP/1.1\r\nContent-Length: 100\r\n\r\n{}')==[]
    assert http_messages(b'POST / HTTP/1.1\r\nContent-Length: 4\r\n\r\nFAIL')==[]


def test_json_rpc_batches_are_paired_by_id():
    from surfbench.wire import exchanges
    messages=[{'flow':['127.0.0.1',40000,'127.0.0.1',8899],'time':1,'body':[
        {'jsonrpc':'2.0','id':1,'method':'getSlot'}, {'jsonrpc':'2.0','id':2,'method':'getHealth'}]},
        {'flow':['127.0.0.1',8899,'127.0.0.1',40000],'time':2,'body':[
        {'jsonrpc':'2.0','id':2,'result':'ok'}, {'jsonrpc':'2.0','id':1,'result':20}]}]
    pairs=exchanges(messages)
    assert [(p['request']['method'],p['response']['result']) for p in pairs]==[('getHealth','ok'),('getSlot',20)]
