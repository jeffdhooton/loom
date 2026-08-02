from setpoint import __version__
from setpoint.__main__ import main


def test_version():
    assert __version__ == "0.1.0"


def test_help_returns_zero(capsys):
    assert main(["--help"]) == 0
    out = capsys.readouterr().out
    assert "loop engine" in out
    assert "run" in out
