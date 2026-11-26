"""Startup falha fechado e não expõe a configuração inválida."""

import os
import subprocess
import sys

import pytest

from central_salas.paths import PROJECT_ROOT


@pytest.mark.parametrize("secret", [None, "z" * 64, "aa" * 31, "a" * 65])
def test_invalid_secret_stops_startup_without_echo(secret):
    env = os.environ.copy()
    if secret is None:
        env.pop("REQUEST_STATE_SECRET", None)
    else:
        env["REQUEST_STATE_SECRET"] = secret
    process = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "servidor-mcp" / "main.py")],
        env=env, capture_output=True, text=True, timeout=10,
    )
    assert process.returncode != 0
    assert "REQUEST_STATE_SECRET" in process.stderr
    if secret:
        assert secret not in process.stderr and secret not in process.stdout
