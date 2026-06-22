from loom.gates.checks import run_checks


def _passed(results):
    return {r.name: r.passed for r in results}


def test_max_words_fails_when_over():
    text = " ".join(["w"] * 664)
    r = run_checks(text, [{"max_words": 400}])
    assert _passed(r) == {"max_words": False}
    assert "664" in r[0].detail


def test_max_words_passes_when_under():
    text = " ".join(["w"] * 100)
    assert _passed(run_checks(text, [{"max_words": 400}])) == {"max_words": True}


def test_must_contain_and_not_contain():
    r = run_checks("alpha beta", [{"must_contain": ["alpha"]}, {"must_not_contain": ["zeta"]}])
    assert all(x.passed for x in r)
    r2 = run_checks("alpha beta", [{"must_contain": ["gamma"]}])
    assert r2[0].passed is False


def test_unknown_check_is_skipped_as_pass():
    r = run_checks("x", [{"bogus": 1}])
    assert r[0].passed is True
