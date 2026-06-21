from loom import __version__
from loom.__main__ import main


def test_version():
    assert __version__ == "0.1.0"


def test_help_returns_zero(capsys):
    assert main(["--help"]) == 0
    assert "loop engine" in capsys.readouterr().out
