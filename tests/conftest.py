"""Les tests ne consomment jamais les compteurs persistants de la démo."""
import pytest


@pytest.fixture(autouse=True)
def isolated_identifiers(tmp_path, monkeypatch):
    monkeypatch.setenv('GREENMIND_IDENTIFIERS_PATH', str(tmp_path / 'identifiers.sqlite'))
