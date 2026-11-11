import pytest


@pytest.fixture(autouse=True)
def agents_token(monkeypatch):
    """A real `crew run` reads the agents' token; tests never touch the real one."""
    monkeypatch.setattr("crew.cli.run_token", lambda config: "agents-token")
