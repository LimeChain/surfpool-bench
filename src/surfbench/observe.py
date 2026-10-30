"""Trusted live observer. Install root-owned under /protected, never agent-writable.

This collects observations only. Expected assertions and grades stay in verifier.
"""
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from surfbench.rpc import RPC

ROOT=Path('/protected')

def processes():
    records=[]
    for folder in Path('/proc').iterdir():
        if not folder.name.isdigit(): continue
        try:
            # Avoid opening cmdline for unrelated, short-lived exec processes.
            # Rosetta can abort the reader while rewriting a disappearing
            # process's cmdline. This is only a prefilter: executable, maps,
            # arguments and binary hash below still establish identity.
            if (folder/'comm').read_text().strip() != 'surfpool': continue
            argv=(folder/'cmdline').read_bytes().decode().rstrip('\0').split('\0')
            if not any(x in ('surfpool','/usr/local/bin/surfpool') for x in argv[:3]):continue
            if not any(x in ('start','simnet') for x in argv[1:4]):continue
            exe=os.readlink(folder/'exe')
            maps=(folder/'maps').read_text()
            emulated=exe=='/run/rosetta/rosetta'
            if emulated:
                if not any('/usr/local/bin/surfpool' in line and 'x' in line.split()[1] for line in maps.splitlines()):continue
                if len(argv)>3 and argv[1]=='/usr/local/bin/surfpool':argv=argv[2:]
            elif exe!='/usr/local/bin/surfpool':continue
            if len(argv)<2 or argv[1] not in ('start','simnet'): continue
            records.append({'pid':int(folder.name),'exe':exe,'argv':argv,
                'start_ticks':(folder/'stat').read_text().split()[21],
                'binary_sha256':hashlib.sha256(Path('/usr/local/bin/surfpool').read_bytes()).hexdigest(),
                'environ_keys':sorted(item.split(b'=',1)[0].decode(errors='replace') for item in
                    (folder/'environ').read_bytes().split(b'\0') if item),
                'maps':maps,'emulated':emulated,
                'status':{line.split(':',1)[0]:line.split(':',1)[1].strip() for line in (folder/'status').read_text().splitlines() if ':' in line}})
        except (OSError,ValueError): pass
    return records

def listeners():
    """Map kernel listening sockets to real process descriptors."""
    found=[]
    for family in ('tcp','tcp6'):
        for line in Path('/proc/net/'+family).read_text().splitlines()[1:]:
            fields=line.split()
            if fields[3]!='0A': continue
            address,port=fields[1].split(':')
            inode=fields[9];pids=[]
            for proc in Path('/proc').iterdir():
                if not proc.name.isdigit():continue
                try:
                    for fd in (proc/'fd').iterdir():
                        try:
                            if os.readlink(fd)==f'socket:[{inode}]':pids.append(int(proc.name));break
                        except OSError:pass
                except OSError:pass
            found.append({'family':family,'address_hex':address,'port':int(port,16),'inode':inode,'pids':pids})
    return found

def freeze_agent_processes():
    """Stop remaining agent-UID processes, preserving only the pinned simulator.

The Docker seccomp profile and dropped ptrace capability apply separately.
No process is trusted solely because of its command name.
"""
    allowed={p['pid'] for p in processes()}
    stopped=[]
    for _ in range(3):
        for folder in Path('/proc').iterdir():
            if not folder.name.isdigit(): continue
            try:
                pid=int(folder.name)
                if folder.stat().st_uid==1000 and pid not in allowed:
                    os.kill(pid,signal.SIGSTOP);stopped.append(pid)
            except (OSError,ValueError): pass
        time.sleep(.05)
    return sorted(set(stopped))

def main():
    spec=json.loads((ROOT/'spec.json').read_text())
    rpc=RPC(spec.get('rpc','http://127.0.0.1:8899'),timeout=.4)
    last_processes=0
    with (ROOT/'observations.jsonl').open('a',buffering=1) as f:
        while not (ROOT/'stop').exists():
            sample={'time':time.time()}
            try:
                if spec['case']=='SP012':sample['health']=rpc.call('getHealth')
                else:sample['accounts']=rpc.call('getMultipleAccounts',spec['keys'],{'encoding':'base64','commitment':'confirmed'})
            except Exception as error:
                sample['rpc_error']=str(error)
                alternative=rpc.url.replace('127.0.0.1','[::1]') if '127.0.0.1' in rpc.url else rpc.url.replace('[::1]','127.0.0.1')
                rpc=RPC(alternative,timeout=.4)
            if time.monotonic()-last_processes>=.5:
                sample['processes']=[{k:v for k,v in p.items() if k!='maps'} for p in processes()]
                sample['listeners']=subprocess.run(['ss','-lntp'],capture_output=True,text=True,timeout=2).stdout
                last_processes=time.monotonic()
                if spec.get('sentinel_url'):
                    try:
                        import urllib.request
                        with urllib.request.urlopen(spec['sentinel_url'],timeout=.3) as response:
                            sample['sentinel']=response.read().decode()
                    except Exception as error: sample['sentinel_error']=str(error)
            f.write(json.dumps(sample)+'\n')
            (ROOT/'observer.ready').touch()
            time.sleep(.08)

if __name__=='__main__': main()
