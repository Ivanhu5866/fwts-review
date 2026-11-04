import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import style_check as sc  # noqa: E402

C = "src/foo/foo.c"


def rules(added):
    return [f[2] for f in sc.check_added(added)]


CASES = [
    (C, "x = 1;   ", "trailing-ws"),
    (C, "\tx = 1;\r", "cr"),
    (C, "#define A(x) \\ ", "ws-after-backslash"),
    (C, "\t/* caf\u00e9 */", "non-ascii"),
    (C, "\tx = 1;\x07", "control-char"),
    (C, "\t#ifdef FOO", "indented-preproc"),
    (C, "    x = 1;", "space-indent"),
    (C, " \tx = 1;", "space-before-tab"),
    (C, '\tfwts_log_info(fw, "%"PRIu32, x);', "pri-space"),
    (C, '\tfwts_log_info(fw, "%lx", x);', "pct-l"),
    ("src/foo/foo.h", "#define _FOO_H", "header-guard"),
    (C, '\tfwts_log_info(fw, "value \\n");', "space-before-nl"),
    (C, '\tfwts_log_info(fw, "value\\n");', "log-newline"),
    (C, '\tfwts_failed(fw, LOG_LEVEL_HIGH, "bad value", "x");', "label-camel"),
    (C, "\t/*text */", "comment-space"),
    (C, "\t/* text", "comment-open-text"),
    (C, "\tx = 1; // note", "cpp-comment"),
    (C, "\tif(x)", "kw-space"),
    (C, "\tif (x){", "brace-space"),
    (C, "\tn = sizeof (x);", "sizeof-space"),
    (C, "\tfoo( x);", "paren-space"),
    (C, "\tfoo(a,b);", "comma-space"),
    (C, "\tx ++;", "incdec-space"),
    (C, "\treturn (x);", "return-paren"),
    (C, "\tfor (int i = 0; i < n; i++)", "c99-for-decl"),
    (C, "\tchar* p;", "star-with-type"),
    (C, "\tu32 x;", "nonstd-int"),
    (C, "\tunsigned x;", "bare-unsigned"),
    (C, "static int x __attribute__((unused));", "unused-attr"),
    (C, "\t(void)fw;", "void-cast-unused"),
    (C, "static int foo()", "empty-params"),
    (C, "static int foo(int x) {", "func-brace-same-line"),
    (C, '\tsprintf(buf, "x");', "unsafe-string"),
    (C, "\tfoo (x);", "call-space"),
    (C, '\tprintf("x");', "printf-in-test"),
    (C, "\texit(1);", "exit-in-test"),
]


@pytest.mark.parametrize("path,line,rule", CASES, ids=[c[2] for c in CASES])
def test_rule_fires(path, line, rule):
    assert rule in rules([(path, 1, line)])


CLEAN = '''/*
 * Copyright (C) 2026 Canonical
 */
#include "fwts.h"

#define FOO_MAX		(16)

/*
 *  foo_test1()
 *	check values
 */
static int foo_test1(fwts_framework *fw)
{
	uint32_t i;
	char *p = NULL;

	FWTS_UNUSED(p);
	for (i = 0; i < FOO_MAX; i++) {
		if (i == 3) {
			fwts_log_info(fw, "Value %" PRIu32 " ok", i);
		} else {
			fwts_failed(fw, LOG_LEVEL_HIGH, "FooBadValue",
				"Value 0x%8.8" PRIx32 " bad", i);
		}
	}
	if (sizeof(i) != 4)
		return FWTS_ERROR;

	return FWTS_OK;
}

static fwts_framework_minor_test foo_tests[] = {
	{ foo_test1, "Test foo." },
	{ NULL, NULL }
};

static fwts_framework_ops foo_ops = {
	.description = "Foo test.",
	.minor_tests = foo_tests
};

FWTS_REGISTER("foo", &foo_ops, FWTS_TEST_ANYTIME, FWTS_FLAG_BATCH)
'''


def test_clean_code_has_no_findings():
    added = [(C, i + 1, l) for i, l in enumerate(CLEAN.split("\n")[:-1])]
    assert sc.check_added(added) == []


def test_else_newline():
    assert "else-newline" in rules([(C, 1, "\t}"), (C, 2, "\telse {")])


def test_decl_blank_missing():
    src = ["static int f(void)", "{", "\tint x;", "\tx = 1;", "\treturn x;", "}"]
    fs = sc.check_added([(C, i + 1, l) for i, l in enumerate(src)])
    assert [(f[1], f[2]) for f in fs] == [(4, "decl-blank")]


def test_decl_blank_multiline_decl_ok():
    src = ["{", "\tstatic const char *n[] = {", '\t\t"a",', "\t};", "",
           "\treturn 0;", "}"]
    assert rules([(C, i + 1, l) for i, l in enumerate(src)]) == []


def test_acpica_reported_once_and_nothing_else():
    added = [("src/acpica/source/x.c", 1, "x ++;  "),
             ("src/acpica/source/x.c", 2, "if(x)")]
    assert rules(added) == ["acpica-modified"]


def test_expected_log_skipped():
    assert rules([("fwts-test/foo-0001/foo-0001.log", 1, "x  ")]) == []


def test_generated_fixture_skipped():
    assert rules([("fwts-test/disassemble-0001/SSDT3.dsl.original", 1, "x  ")]) == []


@pytest.mark.parametrize("path", [
    "fwts-test/klog-0001/klog.txt", "fwts-test/dmi-0001/dmi.dat"])
def test_fwts_test_fixtures_skipped(path):
    assert rules([(path, 1, "x  \u00e9")]) == []


@pytest.mark.parametrize("path", [
    "fwts-test/foo-0001/test-0001.sh", "fwts-test/Makefile.am"])
def test_fwts_test_scripts_checked(path):
    assert {"trailing-ws", "non-ascii"} <= set(rules([(path, 1, "x \u00e9 ")]))


@pytest.mark.parametrize("path", [
    "src/foo/foo.h", "Makefile.am", "src/Makefile.am", "configure.ac",
    "scripts/x.sh"])
def test_non_ascii_in_code_and_build_files(path):
    assert "non-ascii" in rules([(path, 1, "# caf\u00e9")])


@pytest.mark.parametrize("path", ["doc/fwts.1", "debian/changelog", "README"])
def test_non_ascii_allowed_in_docs(path):
    assert "non-ascii" not in rules([(path, 1, "Andr\u00e9 Name")])


WRAP = "\tfwts_failed(fw, LOG_LEVEL_HIGH,"


@pytest.mark.parametrize("first", [
    WRAP, "\tfwts_failed(fw, fwts_level(LOG_LEVEL_MEDIUM),"])
def test_label_camel_wrapped(first):
    assert "label-camel" in rules(
        [(C, 1, first), (C, 2, '\t\t"bad value", "x");')])


@pytest.mark.parametrize("second", [
    '\t\t"FooBadValue", "x %s", s);', '\t\ttmp, "bad value");'])
def test_label_camel_wrapped_ok(second):
    assert "label-camel" not in rules([(C, 1, WRAP), (C, 2, second)])


def test_label_camel_wrapped_needs_adjacent_line():
    assert "label-camel" not in rules(
        [(C, 1, WRAP), (C, 5, '\t\t"bad value", "x");')])


def test_utilities_may_printf():
    assert "printf-in-test" not in rules(
        [("src/utilities/kernelscan.c", 1, '\tprintf("x");')])


def test_parse_diff():
    diff = ("diff --git a/x.c b/x.c\n--- a/x.c\n+++ b/x.c\n"
            "@@ -1,0 +2,2 @@\n+a\n++b\n"
            "diff --git a/y.c b/y.c\ndeleted file mode 100644\n"
            "--- a/y.c\n+++ /dev/null\n@@ -1 +0,0 @@\n-z\n")
    assert sc.parse_diff(diff) == [("x.c", 2, "a"), ("x.c", 3, "+b")]


def test_file_ends():
    added = [("a.c", 2, ""), ("b.c", 1, "x"), ("c.c", 1, "\ufeffx")]
    blobs = {"a.c": b"x\n\n", "b.c": b"x", "c.c": "\ufeffx\n".encode()}
    got = {(f[0], f[2]) for f in sc.check_file_ends(added, blobs.get)}
    assert got == {("a.c", "blank-line-eof"), ("b.c", "no-final-newline"),
                   ("c.c", "bom")}


def test_file_ends_ignores_untouched_end():
    assert sc.check_file_ends([("a.c", 1, "x")], {"a.c": b"x\ny\n\n"}.get) == []


def msg_rules(msg, email="a@b.c"):
    return {f[2] for f in sc.check_commit_msg(msg, email)}


def test_commit_msg_ok():
    assert msg_rules("acpi: iort: fix length check\n\nCheck the length "
                     "first.\n\nSigned-off-by: A B <a@b.c>\n") == set()


def test_commit_msg_bad():
    assert msg_rules("Fix stuff \n\nSigned-off-by: X <x@y.z>\n") == {
        "subject-format", "empty-body", "signoff-author", "msg-trailing-ws"}


def test_commit_msg_long_no_signoff():
    assert msg_rules("acpi: " + "x" * 80 + "\n\nBody.\n") == {
        "subject-length", "no-signoff"}


def test_commit_msg_revert_exempt():
    assert msg_rules('Revert "acpi: foo"\n\nThis reverts commit abc.\n\n'
                     "Signed-off-by: A <a@b.c>\n") == set()


def _git(repo, *a):
    subprocess.run(["git", "-C", str(repo), *a], check=True,
                   capture_output=True)


def _repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@e.com")
    _git(tmp_path, "config", "user.name", "T")
    _git(tmp_path, "config", "core.autocrlf", "false")
    return tmp_path


MSG = "t: add t\n\nBody.\n\nSigned-off-by: T <t@e.com>"


def _commit(repo, path, data):
    f = repo / path
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(data.encode())
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", MSG)


def test_run_reports_only_new_lines(tmp_path):
    repo = _repo(tmp_path)
    _commit(repo, "src/t/t.c", "x = 1;  \n")
    _commit(repo, "src/t/t.c", "x = 1;  \n\ty = 2; \n")
    got = [(x.path, x.line, x.rule) for x in sc.run(str(repo), "HEAD~1", "HEAD")]
    assert got == [("src/t/t.c", 2, "trailing-ws")]


def test_run_crlf(tmp_path):
    repo = _repo(tmp_path)
    _commit(repo, "src/t/t.c", "\tx = 1;\n")
    _commit(repo, "src/t/t.c", "\tx = 1;\n\ty = 2;\r\n")
    got = [(x.path, x.line, x.rule) for x in sc.run(str(repo), "HEAD~1", "HEAD")]
    assert got == [("src/t/t.c", 2, "cr")]


@pytest.mark.parametrize("call", [
    '\tfwts_failed(fw, LOG_LEVEL_HIGH, "TBad", "x");\n',
    '\tfwts_failed(fw, LOG_LEVEL_HIGH,\n\t\t"TBad", "x");\n'],
    ids=["single-line", "wrapped"])
def test_run_label_dup(tmp_path, call):
    repo = _repo(tmp_path)
    _commit(repo, "src/t/t.c", call)
    _commit(repo, "src/t/t.c", call + call)
    got = [x.rule for x in sc.run(str(repo), "HEAD~1", "HEAD")]
    assert got == ["label-dup"]


def test_empty_range_is_an_error(tmp_path, capsys):
    repo = _repo(tmp_path)
    _commit(repo, "src/t/t.c", "\tx = 1;\n")
    _commit(repo, "src/t/t.c", "\tx = 2;\n")
    assert sc.main(["--repo", str(repo), "HEAD", "HEAD~1"]) == 2
    assert "style_check: no commits in HEAD..HEAD~1" in capsys.readouterr().err
