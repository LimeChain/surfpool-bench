"""Summarize every declared attempt; do not omit missing or failed results."""
import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import statistics
from surfbench.specs import CASES

ROOT=Path(__file__).resolve().parents[1]

def elapsed(timing):
    if not timing or not timing.get('started_at') or not timing.get('finished_at'):return None
    return (datetime.fromisoformat(timing['finished_at'])-datetime.fromisoformat(timing['started_at'])).total_seconds()

def wilson(success,total):
    if not total:return None
    z=1.959963984540054;p=success/total;den=1+z*z/total
    center=(p+z*z/(2*total))/den
    margin=z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/den
    return [max(0,center-margin),min(1,center+margin)]

def main(args):
    records=[]
    for case in CASES:
        for seed in range(args.repetitions):
            run=f'{args.prefix}-{case.lower()}-seed{seed}';trial=ROOT/'runs'/run/f'{case.lower()}-codex'
            result_path=trial/'result.json'
            if not result_path.exists():raise RuntimeError(f'Missing declared attempt: {trial}')
            result=json.loads(result_path.read_text());manifest=json.loads((trial/'run-manifest.json').read_text())
            regrade=ROOT/'reports'/args.regrades/run/'regrade.json'
            if not regrade.exists():raise RuntimeError(f'Missing final regrade: {regrade}')
            audited=json.loads(regrade.read_text());reward=audited.get('rewards') or {}
            exception=result.get('exception_info')
            status='budget_exhaustion' if exception and exception['exception_type']=='AgentTimeoutError' else 'infrastructure_error' if exception or reward.get('infrastructure_error') or not reward else 'pass' if reward.get('completion')==1 else 'agent_failure'
            trajectory_path=trial/'agent/trajectory.json';trajectory=json.loads(trajectory_path.read_text()) if trajectory_path.exists() else {}
            metrics=trajectory.get('final_metrics',{});usage=result.get('agent_result') or {}
            tools=sum(len(step.get('tool_calls',[])) for step in trajectory.get('steps',[]))
            record={'case':case,'seed':seed,'status':status,'trial':str(trial.relative_to(ROOT)),
                'reward':reward,'agent_seconds':elapsed(result.get('agent_execution')),
                'setup_seconds':elapsed(result.get('environment_setup')),'grading_seconds':elapsed(result.get('verifier')),
                'input_tokens':usage.get('n_input_tokens'),'cached_tokens':usage.get('n_cache_tokens'),
                'output_tokens':usage.get('n_output_tokens'),'reasoning_output_tokens':metrics.get('extra',{}).get('reasoning_output_tokens'),
                'estimated_cost_usd':usage.get('cost_usd'),'tool_calls':tools,'agent_image':next(value for key,value in manifest['image_ids'].items() if key.startswith('surfbench-runtime:')),
                'final_verifier_image':audited.get('verifier_image'),'prompt_sha256':manifest['task_sha256']}
            records.append(record)
    by_case=[]
    for case,(name,_) in CASES.items():
        group=[r for r in records if r['case']==case];valid=[r for r in group if r['status']!='infrastructure_error'];success=sum(r['status']=='pass' for r in valid)
        times=[r['agent_seconds'] for r in valid if r['agent_seconds'] is not None]
        by_case.append({'case':case,'name':name,'success':success,'scored':len(valid),'infrastructure_errors':len(group)-len(valid),
            'wilson95':wilson(success,len(valid)),'median_agent_seconds':statistics.median(times) if times else None})
    report={'configuration':{'codex':'0.155.1','model':'gpt-6-astra','reasoning':'high','surface':'CLI + native MCP + pinned local docs','concurrency':3,
                'timeout_seconds':600,'cpu_per_trial':2,'memory_mib_per_trial':2048,'token_cap':None,'automatic_retries':0},
        'cases':by_case,'trials':records,'totals':{key:sum(r[key] for r in records if r[key] is not None) for key in ('input_tokens','cached_tokens','output_tokens','estimated_cost_usd')},
        'notes':['All declared attempts retained; final regrades do not overwrite original rewards.',
                 'Five trials per case are calibration, not a statistically powered model ranking.',
                 'Harbor cost estimates are not billing records; cached input tokens are reported separately.',
                 'Live mainnet reads use recorded responses and do not form one atomic chain snapshot.']}
    (ROOT/'reports/calibration-results.json').write_text(json.dumps(report,indent=2))
    lines=['# Codex calibration results','',f'{sum(r["status"]=="pass" for r in records)}/{len(records)} declared attempts passed after final evidence regrading.','',
           '| Case | Success / scored | Infrastructure exclusions | Median agent time | 95% Wilson interval |','|---|---:|---:|---:|---:|']
    for row in by_case:
        interval=row['wilson95'];ci=f'{interval[0]*100:.1f}–{interval[1]*100:.1f}%' if interval else 'n/a'
        duration=f'{row["median_agent_seconds"]:.1f}s' if row['median_agent_seconds'] is not None else 'n/a'
        lines.append(f'| {row["case"]}: {row["name"]} | {row["success"]}/{row["scored"]} | {row["infrastructure_errors"]} | {duration} | {ci} |')
    lines+=['','Configuration: Codex CLI 0.155.1; gpt-6-astra/high; CLI + MCP + local docs; 600 seconds per attempt; two CPUs/2 GiB; three concurrent trials; seeds 0–4; no automatic retries.','',
        'Each row has only five attempts. Wide intervals reflect that limited sample; these results establish suite functionality and a small reliability baseline, not general model superiority.','',
        'Full configurations, image IDs, scores, timings, usage, original results and regrade evidence are linked by path in `calibration-results.json`.','',
        f'Harbor estimated total model cost: ${report["totals"]["estimated_cost_usd"]:.2f}. This is not a billing statement.']
    (ROOT/'reports/calibration-results.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'attempts':len(records),'passes':sum(r['status']=='pass' for r in records),'cases':by_case},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prefix',default='codex-calibration');p.add_argument('--regrades',default='final-calibration-regrades');p.add_argument('--repetitions',type=int,default=5)
    main(p.parse_args())
