"""Fixed, predeclared repetitions. Retain failures; never select best-of-N."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
from surfbench.specs import CASES

ROOT=Path(__file__).resolve().parents[1]

async def main(args):
    from surfbench.fixture_store import validate_saved
    for seed in range(args.seed,args.seed+args.repetitions):
        validate_saved(ROOT/'fixtures/variants',seed)
    semaphore=asyncio.Semaphore(args.concurrency)
    async def case_runs(case):
        results=[]
        for seed in range(args.seed,args.seed+args.repetitions):
            run=f'{args.run}-{case.lower()}-seed{seed}'
            async with semaphore:
                log=ROOT/'runs'/f'{run}.log';log.parent.mkdir(exist_ok=True)
                trial=ROOT/'runs'/run/f'{case.lower()}-{args.agent}'
                if args.resume and trial.exists():
                    summary=json.loads((trial/'summary.json').read_text())
                    manifest=json.loads((trial/'run-manifest.json').read_text())
                    result=json.loads((trial/'result.json').read_text())
                    assert result.get('finished_at'), 'Only completed trials can be resumed'
                    assert manifest['case']==case and manifest['seed']==seed and manifest['agent']==args.agent
                    assert manifest['model']==args.model
                    assert bool(manifest.get('provider_profile'))==(args.profile=='ogi')
                    code=0 if summary['status']=='pass' else 2 if summary['status']=='infrastructure_error' else 1
                    record={'case':case,'seed':seed,'run':run,'exit_code':code,'reused_completed_attempt':True,
                            'log':str((trial/'trial.log').relative_to(ROOT))}
                    results.append(record);print(json.dumps(record),flush=True)
                    continue
                with log.open('w') as f:
                    process=await asyncio.create_subprocess_exec(sys.executable,str(ROOT/'scripts/run_trial.py'),case,
                        '--agent',args.agent,'--model',args.model,'--profile',args.profile,'--seed',str(seed),'--run',run,stdout=f,stderr=asyncio.subprocess.STDOUT)
                    code=await process.wait()
                result={'case':case,'seed':seed,'run':run,'exit_code':code,'log':str(log.relative_to(ROOT))}
                results.append(result);print(json.dumps(result),flush=True)
        return results
    all_results=await asyncio.gather(*(case_runs(case) for case in args.cases))
    report={'agent':args.agent,'model':args.model,'profile':args.profile,'repetitions':args.repetitions,'retry_policy':'no automatic retries',
            'results':[r for results in all_results for r in results]}
    report_name=args.report_name or f'{args.run}-batch'
    if Path(report_name).name!=report_name:raise ValueError('Report name must not contain a directory')
    (ROOT/'reports'/f'{report_name}.json').write_text(json.dumps(report,indent=2))
    return int(any(r['exit_code'] for r in report['results']))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--agent',choices=['codex','oracle'],default='codex')
    p.add_argument('--model',default='openai/gpt-6-astra');p.add_argument('--run',required=True)
    p.add_argument('--profile',choices=['default','ogi'],default='default')
    p.add_argument('--resume',action='store_true',help='Retain completed matching attempts; never rerun them')
    p.add_argument('--report-name',help='Separate batch report filename stem when splitting disjoint cases')
    p.add_argument('--repetitions',type=int,default=5);p.add_argument('--seed',type=int,default=0)
    p.add_argument('--concurrency',type=int,default=3);p.add_argument('--cases',nargs='+',choices=list(CASES),default=list(CASES))
    raise SystemExit(asyncio.run(main(p.parse_args())))
