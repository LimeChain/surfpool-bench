# Run with Claude Code

Complete the [installation and image build](README.md#install-and-build-once), activate `.venv`, and work from the repository root. Only `build_native.py` is required for Claude; the Codex-specific build is optional.

## Authenticate

Choose one method in the terminal that will run Harbor.

For Anthropic API billing:

```sh
export ANTHROPIC_API_KEY='your-key'
```

For a Claude subscription, run `claude setup-token` on your host, then set its returned token:

```sh
export CLAUDE_CODE_OAUTH_TOKEN='your-token'
export CLAUDE_FORCE_OAUTH=1
```

Harbor forwards the token into the container. It does not automatically copy the host's interactive Claude login. `CLAUDE_FORCE_OAUTH=1` selects subscription authentication when an API key is also present. Keep credentials out of source control and shared transcripts. Alternatively, store these variables in a local environment file and pass `--env-file /absolute/path/to/claude.env`.

## Run

```sh
harbor run -c claude.yaml
```

This runs eight scenarios once each, at most three concurrently, with a ten-minute agent budget. The preset uses **Sonnet**, **high effort**, and **Claude Code 2.1.314**. `sonnet` is a moving model alias; edit `agents[0].model_name` in `claude.yaml` for an exact supported model ID. In Harbor 0.25.0, CLI model overrides may not replace an agent already specified in YAML, so edit the YAML directly.

```sh
# Start with one scenario
harbor run -c claude.yaml -p tasks-harbor/SP001

# Three attempts per scenario
harbor run -c claude.yaml -k 3

# Check installation only, without inference or verification
harbor run -c claude.yaml -p tasks-harbor/SP001 --install-only
```

Answer `Y` to the fixture environment-variable prompt, or add `--yes`. Fixed fixture seed 0 is the default. Set `SURFBENCH_FIXTURE_SEED` to 0–5 to select another stored variant; repetitions do not cycle seeds.

Harbor handles collection and verification before reporting a score. Results are in `jobs/`; see [score interpretation](README.md#results-and-scores). An installation-only check does not validate model authentication or task performance.

References: [Claude authentication](https://code.claude.com/docs/en/authentication), [model configuration](https://code.claude.com/docs/en/model-config).
