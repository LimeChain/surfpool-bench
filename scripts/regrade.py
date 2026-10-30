"""Regrade preserved trusted evidence in a fresh offline verifier container."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]

def main(args):
    trials=sorted(ROOT.glob(f'runs/{args.prefix}*/*/result.json'))
    if args.expected is not None and len(trials)!=args.expected:raise RuntimeError(f'Expected {args.expected} finished trials, found {len(trials)}')
    image_id=subprocess.check_output(['docker','image','inspect',args.image,'--format','{{.Id}}'],text=True).strip()
    records=[]
    for result_path in trials:
        trial=result_path.parent;trusted=trial/'artifacts/trusted'
        destination=ROOT/'reports'/args.output/trial.parent.name
        if destination.exists():raise FileExistsError(destination)
        destination.mkdir(parents=True)
        original=json.loads(result_path.read_text())
        if not (trusted/'evidence.json').exists():
            record={'trial':str(trial.relative_to(ROOT)),'error':'No trusted evidence; preserve infrastructure classification','original_exception':original.get('exception_info')}
        else:
            command=['docker','run','--rm','--platform','linux/amd64','--network','none','--read-only','--tmpfs','/tmp',
                '-e','PYTHONDONTWRITEBYTECODE=1','-v',str(trusted.resolve())+':/protected:ro',
                '-v',str(destination.resolve())+':/logs/verifier',args.image,'python','-m','surfbench.grade','/protected','/logs/verifier']
            completed=subprocess.run(command,capture_output=True,text=True,timeout=120)
            (destination/'stdout.txt').write_text(completed.stdout);(destination/'stderr.txt').write_text(completed.stderr)
            record={'trial':str(trial.relative_to(ROOT)),'verifier_image':image_id,'exit_code':completed.returncode,
                'evidence_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in trusted.iterdir() if p.is_file()},
                'original_rewards':(original.get('verifier_result') or {}).get('rewards'),
                'rewards':json.loads((destination/'reward.json').read_text()) if (destination/'reward.json').exists() else None,
                'grader_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'src/surfbench').glob('*.py')}}
        (destination/'regrade.json').write_text(json.dumps(record,indent=2));records.append(record)
        print(json.dumps({'trial':record['trial'],'rewards':record.get('rewards'),'error':record.get('error')}),flush=True)
    (ROOT/'reports'/args.output/'index.json').write_text(json.dumps(records,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prefix',required=True);p.add_argument('--output',required=True)
    p.add_argument('--image',default='surfbench-verifier:0.1.1');p.add_argument('--expected',type=int)
    main(p.parse_args())
