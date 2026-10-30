# Third-party material

- Local Surfpool documentation/source excerpts and schemas come from Surfpool v1.7.0, commit `9be726da6456b58a3b39c099885c6c5904da4543`. Per-file URLs and SHA-256 values are in `docs/provenance.json`; license in `licenses/Surfpool-LICENSE`.
- `images/egress-sidecar/` is adapted from Harbor 0.25.0, commit `fdba28fc411e47e8765420a1a063b4918fce3def`. This suite splits its nftables FIB rules into IPv4 and IPv6 tables and removes the blanket ICMP allowance. Its GOST image is pinned by digest. License in `licenses/Harbor-LICENSE`.
- `images/seccomp.json` derives from the Moby profiles default seccomp policy. Source revision is in `images/seccomp-source.json`; this suite removes ptrace, process_vm_readv, process_vm_writev and pidfd_getfd allowances. License in `licenses/Moby-Profiles-LICENSE`.
- `fixtures/counter.ld` is the SBF linker script from Agave v4.0.0. Counter source is an original minimal test fixture. Build provenance is in `fixtures/PROVENANCE.json`.

These notices concern bundled material. Surfpool, Codex, GOST, Debian, Python and installed packages retain their own licenses.
