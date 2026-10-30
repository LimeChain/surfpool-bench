"""Exercise network and evidence boundaries without using agent credentials."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]

def docker(*args,input=None,check=True):
    return subprocess.run(['docker',*args],input=input,text=True,capture_output=True,check=check,timeout=60)

def main():
    suffix=uuid.uuid4().hex[:10];egress='surfbench-netcheck-'+suffix;boundary='surfbench-boundary-'+suffix
    results={}
    try:
        docker('run','-d','--name',egress,'--cap-add=NET_ADMIN','--cap-add=NET_RAW',
               '-e','EGRESS_CONTROL_INITIAL_NETWORK_MODE=allowlist','-e','EGRESS_CONTROL_INITIAL_ALLOWED_HOSTS=api.openai.com',
               '--entrypoint','/opt/egress-sidecar/entrypoint.sh','surfbench-egress:0.1.1')
        for _ in range(30):
            if docker('exec',egress,'test','-f','/tmp/harbor-docker-egress-control-sidecar.ready',check=False).returncode==0:break
            time.sleep(.2)
        probe=r'''
import subprocess,json,threading,http.server,socket
checks={}
for name,url in [('allowed_model','https://api.openai.com/v1/models'),('blocked_host','https://example.com'),('blocked_ip','http://1.1.1.1')]:
 p=subprocess.run(['curl','--noproxy','*','-sS','-o','/dev/null','-w','%{http_code}','--max-time','10',url],capture_output=True,text=True)
 checks[name]={'exit':p.returncode,'http':p.stdout}
s=http.server.HTTPServer(('127.0.0.1',18999),http.server.SimpleHTTPRequestHandler);threading.Thread(target=s.serve_forever,daemon=True).start()
p=subprocess.run(['curl','-sS','-o','/dev/null','-w','%{http_code}','http://127.0.0.1:18999'],capture_output=True,text=True)
checks['loopback']={'exit':p.returncode,'http':p.stdout}
print(json.dumps(checks))
assert checks['allowed_model']['http']=='401'
assert checks['blocked_host']['exit']!=0 and checks['blocked_ip']['exit']!=0
assert checks['loopback']['http']=='200'
'''
        result=docker('run','--rm','-i','--platform','linux/amd64','--network','container:'+egress,'--cap-drop','ALL','surfbench-base:1.7.0','python','-',input=probe)
        results['network']=json.loads(result.stdout)
        results['ipv4_rules']=docker('exec',egress,'nft','list','table','ip','gost_egress').stdout
        results['ipv6_rules']=docker('exec',egress,'nft','list','table','ip6','gost_egress').stdout
        docker('run','-d','--name',boundary,'--platform','linux/amd64','--network','none','--cap-add','SYS_PTRACE',
               '--security-opt','seccomp='+str(ROOT/'images/seccomp.json'),'surfbench-runtime:0.1.1','sleep','infinity')
        docker('exec','-d','-u','agent',boundary,'surfpool','start','--offline','--no-deploy','--no-tui','--no-studio')
        docker('exec',boundary,'python','-c','from surfbench.rpc import RPC;RPC().ready()')
        probe=r'''
import ctypes,os,json
from pathlib import Path
checks={}
pids=[]
for p in Path('/proc').iterdir():
 if p.name.isdigit():
  try:
   if b'surfpool\x00start' in (p/'cmdline').read_bytes():pids.append(int(p.name))
  except OSError:pass
assert pids
for pid in pids:
 try:fd=os.open(f'/proc/{pid}/mem',os.O_RDWR);os.close(fd);checks['simulator_memory_denied']=False
 except PermissionError:checks['simulator_memory_denied']=True
libc=ctypes.CDLL(None,use_errno=True);rc=libc.ptrace(0,0,0,0)
checks['ptrace_denied']=rc==-1 and ctypes.get_errno() in (1,38)
for label,path in [('protected','/protected/spec.json'),('binary','/usr/local/bin/surfpool')]:
 try:fd=os.open(path,os.O_WRONLY|os.O_CREAT,0o600);os.close(fd);checks[label+'_write_denied']=False
 except PermissionError:checks[label+'_write_denied']=True
checks['docker_socket_absent']=not Path('/var/run/docker.sock').exists()
checks['grader_absent']=not Path('/opt/verifier').exists()
checks['agent_uid']=os.getuid()==1000
print(json.dumps(checks));assert all(checks.values())
'''
        result=docker('exec','-i','-u','agent',boundary,'python','-',input=probe)
        results['boundary']=json.loads(result.stdout)
        results['passed']=True
        (ROOT/'reports/security-qualification.json').write_text(json.dumps(results,indent=2))
        print(json.dumps({'passed':True,'network':results['network'],'boundary':results['boundary']},indent=2))
    finally:
        docker('rm','-f',boundary,egress,check=False)

if __name__=='__main__':main()
