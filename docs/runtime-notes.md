# Surfpool 1.7.0 qualified runtime notes

These notes supplement the pinned source and CLI help, not task-specific solutions.

- `surfnet_writeProgram` takes program ID, unprefixed hex bytes, byte offset, optional authority. The release source examples show `0x`, but the implementation rejects that prefix.
- Query slots and account state at the same commitment when coordinating scheduled changes.
- A native MCP `create_scenario` call stages a Studio link. Execution requires registration with the running network.
- Synthetic offline accounts already exist locally. Set `fetchBeforeUse: false` on their scenario overrides; the upstream Pyth example's remote fetch setting is intended for live accounts.
- Counter fixture ABI is in `/fixtures/counter-abi.json` when supplied. `surfbench-client initialize`, `increment`, and `read-counter` use the supplied payer and counter keypairs. Funding the local payer through state controls is allowed.
- `surfbench-client transfer` uses the supplied sender, recipient, mint, payer and fixed amount; `simulate-transfer` simulates the same operation. Read its installed source for its ABI.

Source: https://github.com/solana-foundation/surfpool/tree/v1.7.0
