"""Exercise final-tree builds with a series whose intermediate patch is broken."""
import csv
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_test.sh"


@pytest.mark.parametrize("case", ["fixed_head", "broken_head", "merge_head"])
def test_only_final_tree_is_built(tmp_path, case):
    for tool in ("git", "autoreconf", "automake", "gcc", "make"):
        if not shutil.which(tool):
            pytest.skip(f"{tool} is required for the build integration test")
    work = tmp_path / "review"
    work.mkdir()
    repo = work / "wt"
    repo.mkdir()

    def git(*args):
        return subprocess.check_output(
            ["git", "-C", str(repo), *args], text=True, stderr=subprocess.STDOUT
        ).strip()

    def commit(message):
        git("add", ".")
        git("commit", "-qm", message)
        return git("rev-parse", "HEAD")

    git("init", "-q", "-b", "main")
    git("config", "user.name", "Review Test")
    git("config", "user.email", "review@example.invalid")
    (repo / "configure.ac").write_text(
        "AC_INIT([review-probe], [1.0])\n"
        "AM_INIT_AUTOMAKE([foreign])\nAC_PROG_CC\n"
        "AC_CONFIG_FILES([Makefile])\nAC_OUTPUT\n"
    )
    (repo / "Makefile.am").write_text(
        "bin_PROGRAMS = probe\nprobe_SOURCES = main.c\n"
        "check-local:\n\t./probe\n"
    )
    source = repo / "main.c"
    source.write_text("int main(void) { return 0; }\n")
    base = commit("base")
    source.write_text("#error intermediate patch must not be built\n")
    intermediate = commit("first patch needs the rest of the series")
    source.write_text(
        "#error final tree is broken\n" if case == "broken_head"
        else "int main(void) { return 0; }\n"
    )
    head = commit("complete series")
    if case == "merge_head":
        git("checkout", "-qb", "side", base)
        (repo / "README").write_text("Side-branch change\n")
        commit("side patch")
        git("checkout", "-q", "main")
        git("merge", "--no-ff", "-qm", "merge complete series", "side")
        head = git("rev-parse", "HEAD")
    # The script must select the requested final tree, regardless of current checkout.
    git("checkout", "-q", "--detach", base)
    result = subprocess.run(
        ["bash", str(SCRIPT), str(work), base, head],
        text=True, capture_output=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert git("rev-parse", "HEAD") == head
    logs = work / "logs"
    assert sorted(p.name for p in logs.glob("build-*.log")) == [f"build-{head[:8]}.log"]
    assert intermediate[:8] not in result.stdout
    with (logs / "matrix.tsv").open() as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    assert len(rows) == 1
    assert rows[0]["commit"] == head[:8]
    if case == "broken_head":
        assert rows[0]["gcc"].startswith("FAIL:")
        assert rows[0]["make_check"] == "SKIP (head build failed)"
        assert not (logs / "make-check.log").exists()
    else:
        assert rows[0]["gcc"] == "PASS", result.stdout
        assert rows[0]["make_check"].startswith("PASS"), result.stdout
        assert (repo / "probe").is_file()
        assert "./probe" in (logs / "make-check.log").read_text()
