# Run with Codex

Complete the [installation and image builds](README.md#install-and-build-once), activate `.venv`, and work from the repository root.

```sh
codex login status
harbor run -c codex.yaml
```

If needed, use `codex login` on the host first. This preset uses the existing ChatGPT login in `~/.codex/auth.json`; Harbor forwards it into each isolated Docker trial. Credentials are not embedded in the YAML. See [OpenAI authentication documentation](https://learn.chatgpt.com/docs/auth).

The default is **GPT-6.1 Terra**, **high effort**, **Codex CLI 0.164.0**, eight tasks once each, three concurrent trials, and ten minutes per agent attempt. The CLI inside Docker is separate from your host installation. Terra requires CLI 0.159.0 or later ([model requirements](https://learn.chatgpt.com/docs/models)).

```sh
# One scenario
harbor run -c codex.yaml -p tasks-harbor-codex/SP001

# Three attempts of every scenario
harbor run -c codex.yaml -k 3

# Stored fixture variant 3
SURFBENCH_FIXTURE_SEED=3 harbor run -c codex.yaml
```

Answer `Y` to Harbor's fixture environment-variable prompt, or add `--yes`. Edit `codex.yaml` to select a different supported model, effort, or concurrency. Repetitions use the same selected fixture variant.

Results are in `jobs/`. See [score interpretation](README.md#results-and-scores). Codex and Claude use matching scenario instructions, fixtures, solutions, and verifier; their agent images and provider network hosts differ.
