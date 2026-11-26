"""Configuração isolada da chave usada exclusivamente nos testes."""

import secrets

import pytest


@pytest.fixture(autouse=True)
def request_state_secret(monkeypatch):
    monkeypatch.setenv("REQUEST_STATE_SECRET", secrets.token_hex(32))
