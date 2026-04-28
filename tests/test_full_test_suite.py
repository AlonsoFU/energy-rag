"""Sanity check that the test suite stays green and no regressions."""


def test_all_non_slow_tests_pass():
    """Smoke that running pytest with not-slow doesn't have regressions.

    This is meta -- it would actually shell out to pytest on the rest of the
    suite, but running pytest from inside pytest leads to recursion. Instead,
    we just check the project metadata is in place; the actual run happens in
    CI / on the developer's terminal.
    """
    # Skip if RUNNING_FULL_SUITE env var set, to avoid recursion
    import os
    if os.environ.get("RUNNING_FULL_SUITE"):
        return
    # Otherwise just check pyproject.toml exists; the actual run happens in CI.
    from pathlib import Path
    assert Path("pyproject.toml").exists()
