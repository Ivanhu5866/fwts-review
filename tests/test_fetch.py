import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
GIT_ENV = {"GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@x.org",
           "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@x.org",
           "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}


def git(cwd, *args):
    env = {**os.environ, **GIT_ENV}
    return subprocess.run(["git", "-C", str(cwd), *args], env=env, check=True,
                          capture_output=True, text=True).stdout.strip()


def commit(repo, name, text="x\n"):
    (repo / name).write_text(text)
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", f"add {name}")
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def env(tmp_path):
    """origin.git (master + refs/pull/7/head), a clone 'repo' whose origin
    then moves on (new master commit, new tag), stub gh, isolated roots."""
    src = tmp_path / "src"
    src.mkdir()
    git(src, "init", "-q", "-b", "master")
    c1 = commit(src, "a")
    git(src, "checkout", "-q", "-b", "pr")
    pr = commit(src, "b")
    git(src, "checkout", "-q", "master")
    commit(src, "c")
    origin = tmp_path / "origin.git"
    git(tmp_path, "clone", "-q", "--bare", str(src), str(origin))
    git(tmp_path, "--git-dir", str(origin), "update-ref", "refs/pull/7/head", pr)
    repo = tmp_path / "repo"
    git(tmp_path, "clone", "-q", str(origin), str(repo))
    new_master = commit(src, "d")
    git(src, "tag", "v2")
    git(src, "push", "-q", str(origin), "master", "v2")
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "gh").write_text("#!/bin/sh\necho '{\"number\": 7}'\n")
    (bin_ / "gh").chmod(0o755)
    for d in ("root", "tmp"):
        (tmp_path / d).mkdir()
    e = {**os.environ, **GIT_ENV, "PATH": f"{bin_}:{os.environ['PATH']}",
         "FWTS_REVIEW_ROOT": str(tmp_path / "root"),
         "TMPDIR": str(tmp_path / "tmp")}
    return {"tmp": tmp_path, "repo": repo, "src": src, "env": e, "c1": c1,
            "pr": pr, "new_master": new_master, "scripts": SCRIPTS}


def run(env, *args):
    p = subprocess.run([str(env["scripts"] / "fetch.sh"), "--repo",
                        str(env["repo"]), *args], env=env["env"],
                       capture_output=True, text=True)
    vals = dict(ln.split("=", 1) for ln in p.stdout.splitlines() if "=" in ln)
    return p.returncode, vals, p.stderr


def other_refs(repo):
    return [r for r in git(repo, "for-each-ref", "--format=%(refname) %(objectname)")
            .splitlines() if not r.startswith("refs/fwts-review/")]


def test_pr_fetch_touches_only_review_refs(env):
    repo = env["repo"]
    before = other_refs(repo)
    rc, v, err = run(env, "7")
    assert rc == 0, err
    assert (v["ID"], v["HEAD"], v["BASE"]) == ("pr7", env["pr"], env["c1"])
    assert other_refs(repo) == before
    assert not (repo / ".git" / "FETCH_HEAD").exists()
    assert git(repo, "rev-parse", "refs/fwts-review/origin-master") == env["new_master"]
    assert Path(v["WT"], "b").exists()
    rc, _, _ = run(env, "--cleanup", "pr7")
    assert rc == 0 and not Path(v["WORK"]).exists()
    assert git(repo, "for-each-ref", "--format=%(refname)", "refs/fwts-review") == \
        "refs/fwts-review/origin-master"
    assert len(git(repo, "worktree", "list").splitlines()) == 1


def test_local_ranges_need_no_network_and_do_not_collide(env):
    repo = env["repo"]
    git(repo, "remote", "set-url", "origin", str(env["tmp"] / "gone.git"))
    rc1, v1, err = run(env, "HEAD~1..HEAD")
    assert rc1 == 0, err
    rc2, v2, err = run(env, "HEAD..HEAD")
    assert rc2 == 0, err
    assert v1["ID"] != v2["ID"]
    assert Path(v1["WT"]).is_dir() and Path(v2["WT"]).is_dir()
    for v in (v1, v2):
        run(env, "--cleanup", v["ID"])


@pytest.mark.parametrize("bad", ["../x", "a/b", "..", "x..y", "a b"])
def test_cleanup_rejects_bad_id(env, bad):
    rc, _, _ = run(env, "--cleanup", bad)
    assert rc == 2


def test_pr_bad_base_exits_3(env):
    rc, _, err = run(env, "--base", "no-such-ref", "7")
    assert rc == 3, err


@pytest.fixture
def ml_env(env):
    """fetch.sh copied next to a stub mbox_extract.py that 'extracts' a
    format-patch of a new commit on top of c1."""
    scripts = env["tmp"] / "scripts"
    scripts.mkdir()
    shutil.copy(SCRIPTS / "fetch.sh", scripts / "fetch.sh")
    git(env["src"], "checkout", "-q", "-b", "ml", env["c1"])
    commit(env["src"], "m")
    patch = env["tmp"] / "p.mbox"
    patch.write_text(git(env["src"], "format-patch", "--stdout", "-1") + "\n")
    (scripts / "mbox_extract.py").write_text(
        "import shutil, sys\n"
        f"shutil.copy({str(patch)!r}, sys.argv[2])\n"
        "print('MSGID=x@y')\nprint('PATCHES=1')\n")
    return {**env, "scripts": scripts}


ML = "https://lists.ubuntu.com/archives/fwts-devel/2025-August/014058.html"


def test_ml_applies_on_cached_origin_master(ml_env):
    rc, v, err = run(ml_env, ML)
    assert rc == 0, err
    assert v["BASE"] == ml_env["new_master"]
    assert not os.listdir(ml_env["env"]["TMPDIR"])
    run(ml_env, "--cleanup", v["ID"])


def test_ml_bad_base_exits_3(ml_env):
    rc, _, err = run(ml_env, "--base", "no-such-ref", ML)
    assert rc == 3, err


def test_ml_fetch_failure_leaves_no_temp_files(ml_env):
    git(ml_env["repo"], "remote", "set-url", "origin", str(ml_env["tmp"] / "gone.git"))
    rc, _, _ = run(ml_env, ML)
    assert rc == 3
    assert not os.listdir(ml_env["env"]["TMPDIR"])
