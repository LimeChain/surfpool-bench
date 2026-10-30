"""Harbor Docker adapter with fail-closed, family-specific nftables rules.

Upstream Harbor 0.25 requires NFT_FIB_INET; Docker Desktop provides the
IPv4 and IPv6 equivalents. The bundled sidecar enforces both families.
"""
import functools
import subprocess
from pathlib import Path
from harbor.environments.docker.docker import DockerEnvironment

class SurfbenchDockerEnvironment(DockerEnvironment):
    _EGRESS_CONTROL_SIDECAR_CONTEXT_PATH = Path(__file__).resolve().parents[2] / "images/egress-sidecar"
    _EGRESS_CONTROL_SIDECAR_DOCKER_NAME = "surfbench-egress:0.1.1"

    @classmethod
    @functools.cache
    def _egress_control_kernel_support(cls):
        # Build the sidecar before invoking the runner. Probe actual rule
        # installation, rather than trusting kernel configuration strings.
        try:
            result = subprocess.run(cls._engine_cmd(
                "run", "--rm", "--cap-add=NET_ADMIN", "--network=none",
                "--entrypoint", "/usr/local/bin/network-policy",
                cls._EGRESS_CONTROL_SIDECAR_DOCKER_NAME, "deny-all"),
                capture_output=True, text=True, timeout=30)
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False
