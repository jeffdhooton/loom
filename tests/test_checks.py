from setpoint.gates.checks import run_checks


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


def test_contain_checks_accept_bare_strings():
    # A bare string must be treated as one needle, not iterated char-by-char.
    r = run_checks("alpha beta", [{"must_not_contain": "zeta"}])
    assert all(c.passed for c in r)
    r2 = run_checks("alpha beta", [{"must_contain": "alpha"}, {"must_not_contain": "beta"}])
    assert [c.passed for c in r2] == [True, False]


def test_judge_diff_uses_merge_base_when_maker_committed(tmp_path):
    import subprocess
    from setpoint.gates.judge import JudgeGate

    def git(*args, cwd):
        subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)

    repo = tmp_path / "repo"
    repo.mkdir()
    git("init", "-b", "develop", cwd=repo)
    git("config", "user.email", "t@t", cwd=repo)
    git("config", "user.name", "t", cwd=repo)
    (repo / "f.txt").write_text("original\n")
    git("add", "-A", cwd=repo)
    git("commit", "-m", "base", cwd=repo)
    git("checkout", "-b", "loop/x", cwd=repo)
    (repo / "f.txt").write_text("changed\n")
    git("commit", "-am", "maker work", cwd=repo)  # committed => `git diff HEAD` empty

    gate = JudgeGate(client=None, model="m", rubric_text="r", threshold=0.8,
                     artifact="@diff", diff_base="develop")
    text = gate._read_artifact(repo)
    assert "changed" in text  # sees committed work via merge-base

    bare = JudgeGate(client=None, model="m", rubric_text="r", threshold=0.8,
                     artifact="@diff")
    assert bare._read_artifact(repo) == "[empty diff]"  # old HEAD-only behavior
