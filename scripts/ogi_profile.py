"""Opt-in Ogi connection; credentials stay in memory, never in task/config files."""
import json
import os
from pathlib import Path
import shutil
import ssl
import tomllib
import urllib.request
from urllib.parse import urlsplit
import certifi
from surfbench.specs import CASES

ROOT = Path(__file__).resolve().parents[1]
PROVIDER = 'ogi_deepseek'

def connection():
    config = tomllib.loads((Path.home()/'.codex/config.toml').read_text())
    provider = config['model_providers'][PROVIDER]
    token = provider.get('experimental_bearer_token')
    url = provider['base_url'].rstrip('/')
    request = urllib.request.Request(provider.get('model_catalog_url', url+'/models'),
                                     headers={'Authorization': 'Bearer '+token} if token else {})
    with urllib.request.urlopen(request, timeout=20, context=ssl.create_default_context(cafile=certifi.where())) as response:
        catalog = json.load(response)
    models = [item['id'] for item in catalog.get('data', [])]
    return url, token, models

def runtime_options(model):
    url, token, models = connection()
    slug = model.removeprefix('openai/')
    if slug not in models:
        raise RuntimeError(f'Requested Ogi model is unavailable: {slug}; available: {models}')
    profile = json.loads((ROOT/'reports/ogi-profile.json').read_text())
    if profile['base_url'] != url or profile['model'] != slug:
        raise RuntimeError('Prepared Ogi profile differs from requested runtime')
    # Harbor's Codex adapter expects a key; this provider can instead be
    # authenticated solely by its Tailscale network boundary.
    os.environ['SURFBENCH_OGI_API_KEY'] = token or 'tailscale-no-api-key'
    native = {'model_provider': PROVIDER, 'model_reasoning_summary': 'none',
              'model_providers': {PROVIDER: {'name': 'Ogi DeepSeek', 'base_url': url,
                  'env_key': 'SURFBENCH_OGI_API_KEY', 'wire_api': 'responses',
                  'requires_openai_auth': False, 'supports_websockets': False,
                  'request_max_retries': 1, 'stream_max_retries': 1,
                  'stream_idle_timeout_ms': 300000}}}
    return {'config': native, 'reasoning_summary': 'none'}, profile

def prepare():
    url, token, models = connection()
    if len(models) != 1 or 'deepseek' not in models[0].lower():
        raise RuntimeError(f'An unambiguous DeepSeek model is required: {models}')
    host = urlsplit(url).hostname
    destination = ROOT/'tasks-ogi'
    if destination.exists():
        raise FileExistsError('Ogi tasks already prepared; preserve the existing profile')
    shutil.copytree(ROOT/'tasks', destination)
    for case in CASES:
        path = destination/case/'task.toml'
        text = path.read_text()
        import re
        hosts = [host]+(['mainnet-proxy'] if case=='SP012' else [])
        text = re.sub(r'^allowed_hosts = .*$', 'allowed_hosts = '+json.dumps(hosts), text, flags=re.M)
        path.write_text(text)
    profile = {'provider': PROVIDER, 'model': models[0], 'base_url': url, 'wire_api': 'responses',
               'authentication': 'provider bearer credential' if token else 'Tailscale; non-secret adapter placeholder',
               'reasoning_effort': 'high', 'reasoning_summary': 'none',
               'harness': 'Codex CLI 0.155.1 / Harbor 0.25.0',
               'repetitions': 6, 'seeds': list(range(6)), 'timeout_seconds': 600,
               'concurrency': 3, 'automatic_trial_retries': 0,
               'note': 'Only provider connection and model egress host differ; prompts, fixtures and verifier remain identical.'}
    (ROOT/'reports/ogi-profile.json').write_text(json.dumps(profile, indent=2))
    print(json.dumps(profile, indent=2))

if __name__ == '__main__':
    prepare()
