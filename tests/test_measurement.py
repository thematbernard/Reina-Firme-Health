"""Structural tests for the two measurement scripts — offline, no Redshift, no API.

These scripts produce the numbers in docs/verified-status.md. The risk is not
that they crash; it is that they silently stop measuring what they claim to.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "evals" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def iq():
    return load("identity_quality")


@pytest.fixture(scope="module")
def bench():
    return load("query_path_benchmark")


def test_recall_uses_the_shipped_matcher(iq):
    """The recall measurement must retarget pipeline/sql/01_identity_xwalk.sql,
    not a copy. If the matcher is refactored so the substitution anchors vanish,
    retarget_matcher must raise rather than silently measure nothing."""
    sql = iq.retarget_matcher("my_patients", "my_result")
    assert "FROM my_patients" in sql
    assert "CREATE OR REPLACE TABLE my_result AS" in sql
    # the real targets must be rewritten; the file's comment header still
    # mentions both names, which is harmless — check the statements, not the prose
    statements = "\n".join(
        ln for ln in sql.splitlines() if not ln.lstrip().startswith("--"))
    assert "raw.ehr_patients" not in statements
    assert "CREATE OR REPLACE TABLE marts.identity_xwalk" not in statements
    # the real matching logic must still be present
    assert "jaro_winkler_similarity" in sql
    assert "exact_tiebreak" in sql


def test_retarget_fails_loudly_on_refactor(iq, monkeypatch, tmp_path):
    """Negative control: if the anchor strings are gone, we must abort."""
    fake = tmp_path / "matcher.sql"
    fake.write_text("SELECT 1 -- no anchors here")
    monkeypatch.setattr(iq, "MATCHER_SQL", fake)
    with pytest.raises(SystemExit):
        iq.retarget_matcher("p", "r")


def test_corruptions_cover_the_real_failure_modes(iq):
    """Recall is only meaningful if the corruptions are the ones that actually
    happen: name typos, marriage, transposed DOB, missing zip, and a compound."""
    names = set(iq.CORRUPTIONS)
    assert {"lastname_typo", "firstname_typo", "married_name",
            "dob_day_transposed", "zip_missing"} <= names
    assert any("and" in n for n in names), "need at least one compound corruption"
    for name, expr in iq.CORRUPTIONS.items():
        # every corruption must still project the five matcher inputs
        for col in ("first_name", "last_name", "dob", "gender", "zip"):
            assert col in expr, f"{name} drops {col}"


def test_zip_corruption_is_varchar_typed(iq):
    """A bare NULL types the column INTEGER and makes DuckDB try to cast
    '95038-8587' to int, which aborts the run. Keep the explicit cast."""
    assert "CAST(NULL AS VARCHAR) AS zip" in iq.CORRUPTIONS["zip_missing"]


def test_benchmark_compares_the_same_question_three_ways(bench):
    """Each question needs a mart variant, a raw variant, and explicit Redshift
    SQL. A missing Redshift variant would silently drop the baseline."""
    assert set(bench.QUESTIONS) == set(bench.REDSHIFT_SQL)
    for name, v in bench.QUESTIONS.items():
        assert {"mart", "raw"} <= set(v)
        assert "marts." in v["mart"], f"{name} mart variant does not read a mart"
        assert "raw." in v["raw"], f"{name} raw variant does not read raw"
        assert "marts." not in v["raw"], f"{name} raw variant cheats via a mart"


def test_redshift_sql_is_redshift_dialect(bench):
    """Redshift has no FILTER (WHERE ...) and no pow(); using DuckDB dialect
    would fail at runtime and silently zero out the baseline column."""
    for name, sql in bench.REDSHIFT_SQL.items():
        assert "FILTER (" not in sql, f"{name} uses FILTER, unsupported on Redshift"
        assert "pow(" not in sql.lower() or "power(" in sql.lower()
        assert "raw." not in sql, f"{name} uses local raw.* names, not source schemas"


def test_benchmark_disables_redshift_result_cache(bench):
    """Without this the baseline reports cache hits (~40ms for a multi-million
    row scan) and the whole comparison is meaningless."""
    src = (ROOT / "evals" / "query_path_benchmark.py").read_text()
    assert "enable_result_cache_for_session TO off" in src


def test_readme_links_resolve():
    """A broken link in the front-door document is the cheapest possible own
    goal, and it happened once already while drafting."""
    import re

    readme = (ROOT / "README.md").read_text()
    missing = []
    for target in re.findall(r"\]\(([^)]+)\)", readme):
        if target.startswith(("http", "#", "mailto:")):
            continue
        if not (ROOT / target.split("#")[0]).exists():
            missing.append(target)
    assert not missing, f"README links to nonexistent paths: {missing}"
