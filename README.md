# Surfpool Bench

Eight isolated Surfpool developer tasks for [Harbor](https://github.com/harbor-framework/harbor), with Codex and Claude Code presets. Agents receive the Surfpool CLI, its native MCP server, and pinned local documentation. Each trial uses fresh Docker containers.

**Run with `harbor run`.** Environment setup, protected evidence collection, verification, and scoring are all part of Harbor's lifecycle. No post-run scoring script is required.

## Install and build once

Requirements: Git, [uv](https://docs.astral.sh/uv/), Python 3.12 (uv can install it), and a running Docker Engine/Desktop with Compose. Linux and macOS are supported; Apple Silicon runs the pinned amd64 Surfpool binary through Docker emulation.

```sh
git clone https://github.com/LimeChain/surfpool-bench.git
cd surfpool-bench
uv venv --python 3.12 .venv
uv pip sync --python .venv/bin/python requirements/controller.lock
uv pip install --python .venv/bin/python --no-deps -e .
source .venv/bin/activate

docker info
python scripts/build_native.py
python scripts/prepare_native_codex.py
```

`build_native.py` builds the runtime, verifier, network sidecar, mainnet proxy, and Claude image. It downloads Surfpool 1.7.0 and checks the archive SHA-256. `prepare_native_codex.py` adds the pinned Codex CLI image and prepares its task profile. Skip that second build if you only want Claude or reference solutions. Keep Docker images unchanged during a comparison; build manifests are written to `reports/`.

The fixed fixtures, native tasks, and compiled counter fixture are already included. You do not need to generate fixtures or compile a Solana program.

## Run

Activate `.venv` in each new terminal, then run from the repository root.

### Codex: GPT-6.1 Terra

Use an existing Codex CLI ChatGPT login (`codex login`) stored in `~/.codex/auth.json`:

```sh
harbor run -c codex.yaml
```

The preset uses **GPT-6.1 Terra, high effort, Codex CLI 0.164.0**. Harbor forwards the host login into each trial; the agent runs inside Docker. Updating your host Codex CLI does not update the pinned container CLI. See [Codex instructions](RUN_WITH_CODEX.md).

### Claude Code: Sonnet

Supply credentials in your terminal. For API billing, set `ANTHROPIC_API_KEY`. For a Claude subscription, run `claude setup-token`, set its result as `CLAUDE_CODE_OAUTH_TOKEN`, and set `CLAUDE_FORCE_OAUTH=1`.

```sh
harbor run -c claude.yaml
```

The preset uses **Sonnet, high effort, Claude Code 2.1.314**. `sonnet` is a moving alias; edit `model_name` in `claude.yaml` to pin a supported exact model ID. See [Claude instructions](RUN_WITH_CLAUDE.md).

### Reference solutions: no model credentials

```sh
harbor run -c reference.yaml
```

Reference runs exercise startup, task solutions, collection, and grading. They validate the harness, not model performance.

## Attempts and fixtures

Each preset runs **all eight tasks once**, at most **three concurrently**, with a **600-second agent limit**. Trials are independent and do not share a Surfpool instance. Automatic trial retries are disabled by default.

```sh
# One Codex task
harbor run -c codex.yaml -p tasks-harbor-codex/SP001

# One Claude task
harbor run -c claude.yaml -p tasks-harbor/SP001

# Three attempts per task: 24 trials
harbor run -c codex.yaml -k 3

# Another stored fixture variant, from 0 through 5
SURFBENCH_FIXTURE_SEED=3 harbor run -c codex.yaml
```

The default fixture seed is 0. Harbor asks whether it may read `SURFBENCH_FIXTURE_SEED` from your environment; answer `Y`, or add `--yes` for unattended runs. Repetitions reuse the selected variant; they do not cycle seeds. For paired comparisons, use the same seed, attempt count, resource limits, and scoring version.

Six synthetic fixture variants are stored in `fixtures/variants/`. The index and manifests contain checksums, checked before the agent starts. Each container receives its own copy. Synthetic keypairs are public test data and must never be used with real funds. SP012 uses fixed public account addresses and live mainnet reads, so those remote values can change between trials.

## Scenarios

| ID | Agent task | Verification |
|---|---|---|
| SP001 | Set Alice and Bob's SOL balances | Exact lamports and a live simulator after handoff |
| SP002 | Set existing TEST token balances | Mint identity, decimals, balances, authorities, unchanged sentinel |
| SP003 | Load a base snapshot and then an overlay | Account fields, fixture hashes, startup order |
| SP004 | Use custom RPC/WebSocket ports | Listener ownership, actual WebSocket notification, existing service continuity |
| SP005 | Deploy and exercise a counter program | Program bytes, confirmed invocations, independent counter challenge |
| SP006 | Diagnose and repair a failed token transfer | Original failure, permitted correction, successful transfer, replay |
| SP011 | Execute a Surfpool price Scenario | Scheduler registration, observed transition, untouched fields, clean replay |
| SP012 | Load remote mainnet accounts | Exact recorded upstream responses, account identities, read-only access |

The numbering preserves the original case IDs. SP007–SP010 are not included. Seven tasks run offline; SP012 reaches mainnet through a separate read-only recording proxy.

## Results and scores

Harbor saves each job in `jobs/<job-name>/`:

- `result.json`: aggregate progress and scores.
- `<trial>/result.json`: agent configuration, timing, rewards, exceptions.
- `<trial>/agent/`: agent transcript and trajectory.
- `<trial>/verifier/assertions.json`: individual checks.
- `<trial>/verifier/reward.json`: the scores Harbor reads.
- `<trial>/artifacts/trusted/`: captured state, observations, packets, fixture manifest, collection marker, and upstream records where applicable.

The verifier emits named scores:

| Score | Meaning |
|---|---|
| `completion` | 1 if all functional assertions pass; otherwise 0 |
| `correctness` | Fraction of applicable assertions that pass |
| `reporting_endpoint` | 1 if the reported local RPC endpoint is valid and usable |
| `infrastructure_error` | 1 if the grader identifies an infrastructure failure |

A fully successful trial has `completion=1`, `reporting_endpoint=1`, `infrastructure_error=0`, and **no Harbor exception**. Startup or collection failures may produce no reward file. Inspect exceptions as well as averages; CLI exit success alone does not mean every task passed.

In Harbor's progress display, `4/8` means four trials finished. `Completion: 0.500` means the average completion score is 0.5 across scored trials, not that the job is half finished.

## Verification lifecycle

1. Harbor starts an isolated runtime. Startup validates and copies fixed fixtures and starts the protected observer.
2. The agent works as an unprivileged user with CLI, MCP, and local docs.
3. At handoff, the task's `[[verifier.collect]]` hook records live state and performs challenges before the runtime stops.
4. Harbor transfers declared artifacts, including proxy records for SP012, to a separate offline verifier container.
5. The verifier requires a collection-completion marker, runs the assertions, and writes the reward file for Harbor.

The agent cannot edit the root-owned evidence, collection marker, or grader code. It has no Docker socket. Process-memory restrictions, network controls, and binary checks support this boundary. It is a tested benchmark boundary, not a general-purpose hostile-code security guarantee.

## Troubleshooting and limitations

- **`No module named surfbench`:** use the virtual environment above. If you prefer a uv-installed global Harbor, add this package with `uv tool install harbor==0.25.0 --with-editable . --force`. Build scripts still need an environment with the suite's dependencies.
- **Claude says `Not logged in`:** the host's interactive Claude login is not automatically copied. Supply one of the credential variables described above, or use `--env-file /absolute/path/to/claude.env`. Never commit that file.
- **`network_mode='allowlist' is not supported`:** first run `docker info`. An unresponsive Docker daemon or a failed firewall probe can surface as this message. If Docker returns HTTP 500 or hangs, restart Docker Desktop, then retry. Restarting interrupts other containers. Keep the configured environment adapter; do not disable the network policy to hide the failure.
- **Agent reports success, verifier says no live Surfpool:** a foreground process can disappear when the agent's command session ends. Tasks that ask to leave a network running require it to survive handoff. Surfpool's `--daemon` option is one supported approach. Historical scores are not rewritten when diagnosing such failures.
- **SP012 provider errors:** the default public RPC can rate-limit or fail. `SURFBENCH_UPSTREAM_RPC` selects an alternative upstream; record that change for comparisons. Avoid credential-bearing URLs in shared configurations or logs.
- **Diagnosis scope:** SP006 uses a known frozen-account fixture. Its correction-only check is conservative and can reject invalid-parameter mutator probes even when they made no state change. Review individual assertions and traces before interpreting model comparisons.

The frozen task instructions and local agent docs have not been amended with the process-lifetime guidance in this README. This repository preserves the existing evaluation contract.

## Development

```sh
python -m pytest -q
```

The regression suite includes fixture checksums and independence, positive reference evidence, deliberately corrupted evidence, transaction and RPC decoding, proxy write rejection, and native task contracts. The source suite passed 113 regression tests and an eight-case reference run before publication; those results are not a claim that every model passes every task.

Edit task definitions in `src/surfbench/specs.py`, then regenerate profiles with `scripts/generate_tasks.py`, `scripts/generate_native_tasks.py`, and `scripts/prepare_native_codex.py` as appropriate. `scripts/store_fixtures.py` is a one-time authoring tool and refuses to overwrite the checked-in store.

Legacy controller, audit, and optional provider-profile scripts remain available under `scripts/`. They are not needed for the native `harbor run` workflow. Historical local run logs, generated reports, cached release archives, credentials, and private provider configurations are not included in this repository.

Source provenance and license notices are in [THIRD_PARTY.md](THIRD_PARTY.md), `docs/provenance.json`, `fixtures/PROVENANCE.json`, and `licenses/`.
