from evals.run_eval import run_eval


def test_run_eval_passes_on_bundled_scenarios() -> None:
    assert run_eval() == 0


def test_run_eval_filters_by_id() -> None:
    assert run_eval(only="triage-bug-crash-on-startup") == 0


def test_run_eval_errors_on_unknown_id() -> None:
    assert run_eval(only="does-not-exist") == 2
