"""Parse captured loopback HTTP JSON-RPC traffic; never trust agent-saved logs."""
import json
from collections import defaultdict


def http_messages(data):
    messages=[]; pos=0
    while pos<len(data):
        end=data.find(b'\r\n\r\n',pos)
        if end<0: break
        lines=data[pos:end].split(b'\r\n')
        first=lines[0].decode(errors='replace')
        if not (first.startswith('POST ') or first.startswith('HTTP/')):
            break
        headers={}
        for line in lines[1:]:
            if b':' in line:
                k,v=line.split(b':',1);headers[k.strip().lower()]=v.strip().lower()
        begin=end+4
        if headers.get(b'transfer-encoding')==b'chunked':
            body=bytearray();cursor=begin
            try:
                while True:
                    e=data.index(b'\r\n',cursor); n=int(data[cursor:e].split(b';')[0],16)
                    cursor=e+2
                    if n==0:
                        cursor+=2;break
                    if len(data)<cursor+n+2: return messages
                    body.extend(data[cursor:cursor+n]);cursor+=n+2
            except (ValueError,IndexError): break
            pos=cursor
        else:
            try:n=int(headers.get(b'content-length',b'0'))
            except ValueError:break
            if n<0 or n>32_000_000:break
            if len(data)<begin+n:break
            body=data[begin:begin+n];pos=begin+n
        try:payload=json.loads(body)
        except (ValueError,UnicodeDecodeError):continue
        messages.append({'first_line':first,'body':payload})
    return messages


def read_pcap(path, ports=(8899,18899)):
    from scapy.all import PcapReader, IP, IPv6, TCP
    streams=defaultdict(list); generations=defaultdict(int)
    with PcapReader(str(path)) as packets:
        for packet in packets:
            if not packet.haslayer(TCP) or not (packet.haslayer(IP) or packet.haslayer(IPv6)):continue
            ip,tcp=packet[IP] if packet.haslayer(IP) else packet[IPv6],packet[TCP]
            if tcp.dport not in ports and tcp.sport not in ports:continue
            flow=(ip.src,int(tcp.sport),ip.dst,int(tcp.dport))
            if int(tcp.flags)&2:generations[flow]+=1
            payload=bytes(tcp.payload)
            if payload:streams[(flow,generations[flow])].append((int(tcp.seq),payload,float(packet.time)))
    results=[]
    for (flow,generation),segments in streams.items():
        segments.sort(); out=bytearray(); next_seq=segments[0][0]; incomplete=False
        for seq,payload,_ in segments:
            if seq>next_seq: incomplete=True;break
            overlap=next_seq-seq
            if overlap<len(payload):out.extend(payload[overlap:]);next_seq=seq+len(payload)
        if incomplete:
            results.append({'capture_error':'TCP gap','flow':flow});continue
        for message in http_messages(bytes(out)):
            message.update({'flow':flow,'time':min(s[2] for s in segments)})
            results.append(message)
    return sorted(results,key=lambda m:m.get('time',0))


def exchanges(messages):
    """Pair JSON-RPC requests with responses from the opposite TCP direction."""
    pending={}; pairs=[]
    expanded=[]
    for message in messages:
        payload=message.get('body')
        for body in payload if isinstance(payload,list) else [payload]:expanded.append({**message,'body':body})
    for message in expanded:
        body=message.get('body');flow=tuple(message.get('flow',()))
        if len(flow)!=4 or not isinstance(body,dict):continue
        if 'method' in body:
            key=(flow,json.dumps(body.get('id'),sort_keys=True))
            pending.setdefault(key,[]).append(message)
        elif 'id' in body:
            reverse=(flow[2],flow[3],flow[0],flow[1])
            key=(reverse,json.dumps(body['id'],sort_keys=True))
            if pending.get(key):
                request=pending[key].pop(0)
                pairs.append({'request':request['body'],'response':body,'time':request['time']})
    return pairs
