from eval.stress import run


def test_stress_set_regression():
    ok, n, md = run()
    assert ok == n, md
