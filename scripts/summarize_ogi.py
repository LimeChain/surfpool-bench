"""Report all 48 declared Ogi attempts, keeping failures and infrastructure errors."""
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import statistics
from surfbench.specs import CASES

ROOT=Path(__file__).resolve().parents[1]

def duration(timing):
    if not timing or not timing.get('finished_at'):return None
    return (datetime.fromisoformat(timing['finished_at'])-datetime.fromisoformat(timing['started_at'])).total_seconds()

def main():
    records=[]
    baseline={case:[] for case in CASES}
    baseline_smoke={}
    for cohort in ('calibration','smoke'):
        for row in json.loads((ROOT/f'reports/release-{cohort}-regrades/index.json').read_text()):
            trial=ROOT/row['trial'];manifest=json.loads((trial/'run-manifest.json').read_text())
            original=json.loads((trial/'result.json').read_text())
            full_pass=row['rewards']['completion']==1 and row['rewards']['reporting_endpoint']==1 and not original.get('exception_info')
            baseline[manifest['case']].append(full_pass)
            if cohort=='smoke':
                assert manifest['seed']==5
                baseline_smoke[manifest['case']]=full_pass
    assert all(len(rows)==6 for rows in baseline.values())
    assert set(baseline_smoke)==set(CASES)
    for case in CASES:
        for seed in range(6):
            trial=ROOT/'runs'/f'ogi-calibration-{case.lower()}-seed{seed}'/f'{case.lower()}-codex'
            result=json.loads((trial/'result.json').read_text())
            summary=json.loads((trial/'summary.json').read_text())
            manifest=json.loads((trial/'run-manifest.json').read_text())
            assert result['finished_at'] and manifest['model']=='openai/DeepSeek-V4.1-Flash-1017'
            prefix='codex-calibration' if seed<5 else 'final-smoke'
            paired=ROOT/'runs'/f'{prefix}-{case.lower()}-seed{seed}'/f'{case.lower()}-codex'
            paired_manifest=json.loads((paired/'run-manifest.json').read_text())
            assert manifest['task_sha256']==paired_manifest['task_sha256']
            for fixture in (trial/'fixtures-generated').glob('*.json'):
                assert fixture.read_bytes()==(paired/'fixtures-generated'/fixture.name).read_bytes()
            assertions_path=trial/'verifier/assertions.json'
            assertions=json.loads(assertions_path.read_text()) if assertions_path.exists() else {}
            usage=result.get('agent_result') or {}
            native_completion=[]
            for session in (trial/'agent/sessions').rglob('*.jsonl'):
                for line in session.read_text().splitlines():
                    try:event=json.loads(line)
                    except ValueError:continue
                    if event.get('type')=='event_msg' and event.get('payload',{}).get('type')=='task_complete':
                        native_completion.append(event['timestamp'])
            native_seconds=None
            if native_completion and result.get('agent_execution'):
                native_seconds=(datetime.fromisoformat(max(native_completion))-datetime.fromisoformat(result['agent_execution']['started_at'])).total_seconds()
            visible_tool_markup=False
            log=trial/'agent/codex.txt'
            if log.exists():
                for line in log.read_text().splitlines():
                    try:event=json.loads(line)
                    except ValueError:continue
                    item=event.get('item',{})
                    if item.get('type')=='agent_message' and 'DSML' in item.get('text',''):
                        visible_tool_markup=True
            records.append({'case':case,'seed':seed,'status':summary['status'],
                'visible_tool_markup':visible_tool_markup,
                'native_completion_seconds':native_seconds,
                'trial':str(trial.relative_to(ROOT)),'rewards':summary.get('rewards'),
                'failed_assertions':[k for k,v in assertions.items() if not v],
                'exception':(result.get('exception_info') or {}).get('exception_type'),
                'agent_seconds':duration(result.get('agent_execution')),
                'input_tokens':usage.get('n_input_tokens'),'output_tokens':usage.get('n_output_tokens'),
                'cached_tokens':usage.get('n_cache_tokens'),'image_ids':manifest['image_ids'],
                'paired_astra_trial':str(paired.relative_to(ROOT)),'prompt_and_fixtures_identical':True,
                'prompt_sha256':manifest['task_sha256']})
    counts=Counter(r['status'] for r in records)
    case_rows=[]
    for case in CASES:
        group=[r for r in records if r['case']==case]
        times=[r['agent_seconds'] for r in group if r['agent_seconds'] is not None]
        case_rows.append({'case':case,'passes':sum(r['status']=='pass' for r in group),'attempts':6,
                          'completion_check_passes':sum((r.get('rewards') or {}).get('completion')==1 for r in group),
                          'full_passes':sum(r['status']=='pass' and (r.get('rewards') or {}).get('reporting_endpoint')==1 for r in group),
                          'reporting_passes':sum((r.get('rewards') or {}).get('reporting_endpoint')==1 for r in group),
                          'calibration_passes':sum(r['status']=='pass' and r['seed']<5 for r in group),
                          'seed5_passed':group[-1]['status']=='pass','status_counts':dict(Counter(r['status'] for r in group)),
                          'median_agent_seconds':statistics.median(times) if times else None})
    report={'profile':json.loads((ROOT/'reports/ogi-profile.json').read_text()),'counts':dict(counts),
            'cases':case_rows,'trials':records,'metadata':'Codex default fallback metadata for this custom model; no model substitution',
            'astra_all_three_by_case':{case:sum(rows) for case,rows in baseline.items()},
            'astra_final_runtime_seed5_all_three':baseline_smoke,
            'comparison_note':'Same task prompts and fixtures; final runtime matches the eight Astra smoke runs. Astra calibration used an earlier runtime image. All scores use the same final verifier; provider, model, metadata and reasoning-summary configuration differ.'}
    (ROOT/'reports/ogi-results.json').write_text(json.dumps(report,indent=2))
    reporting=sum((r.get('rewards') or {}).get('reporting_endpoint')==1 for r in records)
    state=sum((r.get('rewards') or {}).get('completion')==1 for r in records)
    full=sum(r['full_passes'] for r in case_rows)
    markup=sum(r['visible_tool_markup'] for r in records)
    markup_missing_reports=sum(r['visible_tool_markup'] and (r.get('rewards') or {}).get('reporting_endpoint')!=1 for r in records)
    lines=['# Ogi DeepSeek comparison','',f'{counts["pass"]}/48 declared attempts finished within budget with passing completion checks. {state}/48 passed completion checks at handoff; {reporting}/48 passed endpoint reporting. {full}/48 satisfied all three: completion checks, reporting and finishing within budget.',
        '', 'Model: **DeepSeek-V4.1-Flash-1017**, served by the configured Ogi endpoint through Codex CLI 0.155.1 and Harbor 0.25.0. High reasoning, CLI + native Surfpool MCP + pinned local docs; 600 seconds, two CPUs and 2 GiB per attempt; at most three concurrent trials. Six seeds per case, no automatic trial retries.',
        '', '| Case | DeepSeek on-time completion passes | Completion checks at handoff | Reporting passes | All three | Astra all three | Median DeepSeek time |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for row in case_rows:
        time=f'{row["median_agent_seconds"]:.1f}s' if row['median_agent_seconds'] is not None else 'n/a'
        lines.append(f'| {row["case"]} — {CASES[row["case"]][0]} | {row["passes"]}/6 | {row["completion_check_passes"]}/6 | {row["reporting_passes"]}/6 | {row["full_passes"]}/6 | {sum(baseline[row["case"]])}/6 | {time} |')
    smoke=[r for r in records if r['seed']==5]
    smoke_full=sum(r['status']=='pass' and (r.get('rewards') or {}).get('reporting_endpoint')==1 for r in smoke)
    lines+=['',f'For the matched seed-5 cohort using the final runtime on both sides: DeepSeek passed all three criteria in {smoke_full}/8 attempts; Astra passed in {sum(baseline_smoke.values())}/8. This is one attempt per case, not a statistically powered comparison.']
    lines+=['','## Interpretation','',
        'Astra numbers use the previously corrected final verifier, including the documented PDA-definition false negative. DeepSeek uses that same final verifier image. Its runtime image matches the eight final Astra smoke runs; the 40 earlier Astra calibration runs used an earlier runtime image and were regraded from retained evidence. Every attempt is retained; infrastructure failures are shown separately in the JSON report and must not be interpreted as model failures.',
        '', 'Completion includes requested behavior and evidence, including the diagnosis explanation in SP006. It is broader than balances or raw account state.',
        '', 'One assertion-level limitation was found in SP006 seed 5: the frozen verifier marked correction_only false for three empty-parameter mutator probes that were rejected with invalid-parameter errors. Captured evidence confirms that the actual repair was a valid signed thaw. The original assertion and partial correctness score are retained, with the issue documented in [ogi-verifier-observations.json](ogi-verifier-observations.json). Correcting this assertion alone would not change any completion, reporting or on-time counts: the diagnosis report was absent and the attempt timed out. No grader change was made during this comparison.',
        '', 'Endpoint reporting checks the usable RPC endpoint in report.json; it is not a comprehensive natural-language report-accuracy grade. The all-three count refers only to the three measured criteria above.',
        '', 'A budget-exhausted attempt can still leave correct simulator state and a valid report. Those observations are shown separately, but do not turn a timed-out attempt into an on-time success. Seeds 0–4 and seed 5 are also separated in the JSON results for alignment with the Astra cohorts.',
        '', 'The deadline covers the Harbor agent execution, including CLI termination. In SP002 seed 0, Codex logged its native task-complete event about 599.6 seconds after execution began, but the process missed the 600-second Harbor deadline. Its state and report passed; the original timeout classification is preserved. Native completion timings are retained separately where present.',
        '', 'Codex reported missing native model metadata and used its generic fallback profile. This changes capability defaults, not the model receiving the request. Reasoning summaries were disabled for the custom provider. These are tested configurations, not a controlled model-only ablation. Six attempts per case are a small sample.',
        '', 'The [session metadata audit](ogi-metadata-audit.json) confirms the requested models and high reasoning setting. Codex recorded the same context budget for both, but different model-specific base instructions. Wall-time results include the self-hosted Ogi deployment and any contention from concurrent requests; they do not isolate model reasoning speed.',
        '', 'The first SOL attempt emitted an apply_patch call in visible DSML text instead of a structured executable tool call. Its live balances passed, but report.json was absent and endpoint reporting scored zero. Such tool-serialization failures remain part of the observed configuration; they are not repaired by the controller. These observations do not establish that fallback metadata caused the failures.',
        '', f'Visible DSML markup appeared in agent-message events in {markup}/48 attempts; {markup_missing_reports} of those attempts failed endpoint reporting. This is a transcript observation, not a separate grading criterion or proof of causation.',
        '', 'No hosted-model price is assumed for Ogi. Token accounting is retained where reported by the provider. Mainnet loading remains read-only; all mutations and transactions are local.',
        '', 'Full results and failure assertions: [ogi-results.json](ogi-results.json). Configuration and evidence audit: [ogi-audit.json](ogi-audit.json). Original Astra qualification: [qualification.md](qualification.md).',
        '', 'Provider setup follows the official [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).']
    failures=[r for r in records if r['status']!='pass' or (r.get('rewards') or {}).get('reporting_endpoint')!=1]
    if failures:
        lines+=['','## Non-passing attempts','']
        for r in failures:
            reasons=r['failed_assertions'][:]
            if r['exception']:reasons.append(r['exception'])
            if (r.get('rewards') or {}).get('reporting_endpoint')!=1:reasons.append('endpoint reporting failed')
            lines.append(f'- {r["case"]}, seed {r["seed"]}: {r["status"]}; '+', '.join(reasons))
    (ROOT/'reports/ogi-results.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'counts':dict(counts),'cases':case_rows},indent=2))

if __name__=='__main__':main()
