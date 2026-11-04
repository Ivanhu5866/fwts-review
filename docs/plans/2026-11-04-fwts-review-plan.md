# fwts-review skill: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to carry out this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `fwts-review` Copilot CLI skill. It reviews fwts GitHub PRs, fwts-devel mailing-list patches and local commit ranges, covering coding style, spec content, build and test. Its output is a report and a draft reply. It never posts anything.

**Architecture:** Approach A from the design. Scripts do the mechanical work:
- `fetch.sh` + `mbox_extract.py`: input → isolated worktree
- `style_check.py`: style checks on added lines, per commit
- `spec_lookup.sh`: spec text search
- `build_test.sh`: builds, `make check`, clang, cppcheck, fixture runs

`SKILL.md` drives the model through the phases and the judgement items in `references/review-checklist.md`.

**Tech stack:** bash, Python 3.12 (stdlib only), pytest 7.4, git, gh, pdftotext, awk (mawk-safe: no `{m,n}` intervals).

**Spec:** `docs/2026-11-04-fwts-review-design.md`

Deviations from the spec, all intentional:
1. Script names use underscores (`style_check.py`, `spec_lookup.sh`, `build_test.sh`) so tests can import them. There is one new helper, `mbox_extract.py`.
2. Style checks run **per commit** (`git diff -U0 c^ c`), not once over the whole range, because fwts keeps every commit.
3. `git show --check` is dropped. Our rules already cover trailing whitespace, a space before a tab, and blank lines at the end of a file.
4. `spec_lookup.sh pdf` searches every file that matches an optional name glob, rather than only the newest file. `SKILL.md` tells the model to pass a glob such as `'*IORT*'`. It also reads `.docx`, `.odt` and `.txt` files, because many table specs in `~/CloudStation/Document/ACPI/` are `.docx`.
5. `BugLink:`/`Fixes:`-when-the-PR-references-an-issue is a judgement item in SKILL.md, not a script rule, because the script doesn't see PR metadata.

Environment facts:
- clang and cppcheck are **not installed** and there is no sudo, so `build_test.sh` must report SKIP for them.
- `origin` is https://github.com/fwts/fwts.
- `~/.copilot/skills` is not a git repo; Task 1 makes `fwts-review/` its own repo.

## File map

```
~/.copilot/skills/fwts-review/
  SKILL.md                         Task 6
  .gitignore                       Task 1
  references/review-checklist.md   Task 1 (copy)
  references/coding-style.md       Task 1 (copy)
  references/spec-map.md           Task 1
  scripts/style_check.py           Task 2
  scripts/spec_lookup.sh           Task 3
  scripts/mbox_extract.py          Task 4
  scripts/fetch.sh                 Task 4
  scripts/build_test.sh            Task 5
  tests/test_style_check.py        Task 2
  tests/test_spec_lookup.py        Task 3
  tests/test_mbox_extract.py       Task 4
```

Run the tests with `cd ~/.copilot/skills/fwts-review && python3 -m pytest -q tests`.

Every commit ends with the trailer `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`.

---

## Task 1: scaffold, references and spec map

**Files:** create `.gitignore`, `references/review-checklist.md`, `references/coding-style.md` and `references/spec-map.md`.

- [ ] **Step 1: init the repo and copy the references**

```bash
cd ~/.copilot/skills/fwts-review
git init -q
mkdir -p references scripts tests
printf '__pycache__/\n.pytest_cache/\n' > .gitignore
cp ~/work/fwts/fwts-review-checklist.md references/review-checklist.md
cp ~/work/fwts/fwts-coding-style.md references/coding-style.md
```

- [ ] **Step 2: write `references/spec-map.md`**

````markdown
# Spec map: subject → source

Lookup order: 1) ACPI_spec RST → 2) local document library → 3) URL cited in the fwts source or commit → 4) ask the user (mark the finding **unverified** until then).
Always cross-check table layouts with `spec_lookup.sh actbl <SIG>` (ACPICA `actbl*.h`).

| Subject (how to spot it in the diff) | Source | Lookup |
|---|---|---|
| ACPI tables defined in the ACPI spec: FADT, MADT, DSDT/SSDT, FACS, RSDP/XSDT, BERT, BGRT, CPEP, ECDT, EINJ, ERST, FPDT, GTDT, HEST, MSCT, MPST, NFIT, PCCT, PDTT, PHAT, PMTT, PPTT, RASF, RAS2, SBST, SDEV, SLIT, SRAT, MISC, CCEL (`src/acpi/<sig>/`, `fwts_acpi_table_<sig>`) | ACPI_spec RST | `spec_lookup.sh acpi '<SIG>'`, then `view` the file at the reported line |
| ACPI objects and methods: `_BST`, `_PSS`, `_CST`, `_OSC`, `_DSM` … (`src/acpi/method/`) | ACPI_spec RST | `spec_lookup.sh acpi '_BST'` |
| ACPI opcodes, operation regions, PCC/FFH/GPIO/SMBus address spaces (`src/libfwtsacpica/`) | ACPI_spec RST (chapters 5 and 19) | `spec_lookup.sh acpi 'PCC.*Operation Region'` |
| ASPT (AMD) | `Document/ACPI/AMD/` | `pdf ACPI/AMD 'ASPT' '*ASPT*'` |
| CEDT (CXL) | `Document/ACPI/` CXL spec | `pdf ACPI '<term>' '*CEDT*'` |
| CDAT | `Document/ACPI/` | `pdf ACPI '<term>' '*CDAT*'` |
| IORT (Arm) | `Document/ACPI/IORT/` (DEN0049, newest rev E.f) | `pdf ACPI/IORT '<term>' '*E.f*'` |
| MPAM (Arm) | `Document/ACPI/` DEN0065 | `pdf ACPI '<term>' '*MPAM*2.0*'` |
| AEST (Arm RAS) | `Document/ACPI/` DEN0085 | `pdf ACPI '<term>' '*AEST*'` |
| APMT, SDEI, BSA, SBBR, PSCI (Arm) | `Document/ARM/` | `list ARM`, then `pdf ARM '<term>' '*<name>*'` |
| SPCR, DBG2, DBGP, WSMT, SLIC, WDAT (Microsoft) | `Document/ACPI/` (`.doc`/`.docx`/`.odt`) and `Document/Microsoft/` | `pdf ACPI '<term>' '*SPCR*'` (`.doc` is unsupported: convert with `libreoffice --headless --convert-to docx`) |
| TPM2, TCPA (TCG ACPI) | `Document/ACPI/TCG_ACPIGeneralSpecification*` and `Document/TPM/` | `pdf ACPI '<term>' '*TCG*'` |
| TPM event log, PCRs, `tpmevlog` | `Document/TPM/` (TCG PC Client Platform Firmware Profile) | `pdf TPM '<term>' '*Firmware*Profile*'` |
| DMAR (Intel VT-d) | `Document/ACPI/vt-directed-io-spec(DMAR).pdf` | `pdf ACPI '<term>' '*DMAR*'` |
| IVRS (AMD IOMMU) | `Document/ACPI/IVRS.pdf.pdf` | `pdf ACPI '<term>' '*IVRS*'` |
| HPET | `Document/ACPI/software-developers-hpet-spec-1-0a.pdf` | `pdf ACPI '<term>' '*hpet*'` |
| MCFG (PCI firmware) | `Document/ACPI/MCFG/`, `Document/PCIE/` | `pdf ACPI/MCFG '<term>'` |
| SVKL (TDX) | `Document/ACPI/TDX*` | `pdf ACPI '<term>' '*SVKL*'` |
| iBFT, BDAT, BOOT | `Document/ACPI/` | `pdf ACPI '<term>' '*iBFT*'` |
| SMBIOS types, `dmicheck`, `src/dmi/` | `Document/SMBIOS/` (newest DSP0134) | `list SMBIOS`, then `pdf SMBIOS '<term>' '*DSP0134*'` |
| UEFI variables, runtime services, `src/uefi/`, `uefirt*`, `esrt`, `securebootcert` | `Document/UEFI/` | `list UEFI`, then `pdf UEFI '<term>' '*UEFI*Spec*'` |
| RISC-V (RHCT, SBI) | `Document/RISC-V/` | `pdf RISC-V '<term>'` |
| PCIe (AER, ASPM, `src/pci/`) | `Document/PCIE/`, `Document/PCIE3.0.pdf` | `pdf PCIE '<term>'` |
| Intel-specific (`msr`, `mtrr`, `microcode`) | `Document/Intel/` | `pdf Intel '<term>'` |
| AMD-specific | `Document/AMD/` | `pdf AMD '<term>'` |

URLs cited in fwts source: run `git -C ~/work/fwts grep -nE 'https?://' -- src/<area>` and fetch them with `web_fetch`. Note that uefi.org returns 403 to both `web_fetch` and `curl`, so use the local copies instead.
````

- [ ] **Step 3: commit**

```bash
git add -A && git commit -q -m "fwts-review: scaffold, references and spec map

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---
## Task 2: `scripts/style_check.py` (TDD)

**Files:** create `tests/test_style_check.py` and `scripts/style_check.py`.

Interfaces (tests depend on these):
- `parse_diff(text) -> list[(path, lineno, line)]`: the added lines of a `-U0` diff.
- `check_added(added) -> list[(path, line, rule, msg)]`: line, sequence and ACPICA rules.
- `check_file_ends(added, get_blob) -> list[(path, line, rule, msg)]`, where `get_blob(path) -> bytes | None`.
- `check_commit_msg(msg, author_email) -> list[("COMMIT_MSG", line, rule, msg)]`.
- `run(repo, base, head) -> list[Finding]`, where `Finding(commit, path, line, rule, message)`.

- [ ] **Step 1: write the failing tests** in `tests/test_style_check.py`

```python
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


def test_run_reports_only_new_lines(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@e.com")
    _git(tmp_path, "config", "user.name", "T")
    f = tmp_path / "src/t/t.c"
    f.parent.mkdir(parents=True)
    f.write_text("x = 1;  \n")
    msg = "t: add t\n\nBody.\n\nSigned-off-by: T <t@e.com>"
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", msg)
    base = subprocess.run(["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    f.write_text("x = 1;  \n\ty = 2; \n")
    _git(tmp_path, "commit", "-q", "-am", msg)
    got = [(x.path, x.line, x.rule) for x in sc.run(str(tmp_path), base, "HEAD")]
    assert got == [("src/t/t.c", 2, "trailing-ws")]


def test_run_label_dup(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@e.com")
    _git(tmp_path, "config", "user.name", "T")
    f = tmp_path / "src/t/t.c"
    f.parent.mkdir(parents=True)
    line = '\tfwts_failed(fw, LOG_LEVEL_HIGH, "TBad", "x");\n'
    f.write_text(line)
    msg = "t: add t\n\nBody.\n\nSigned-off-by: T <t@e.com>"
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", msg)
    f.write_text(line + line)
    _git(tmp_path, "commit", "-q", "-am", msg)
    got = [x.rule for x in sc.run(str(tmp_path), "HEAD~1", "HEAD")]
    assert got == ["label-dup"]
```

- [ ] **Step 2: run the tests and confirm they fail**

Run: `python3 -m pytest -q tests/test_style_check.py`
Expected: an import error, `ModuleNotFoundError: No module named 'style_check'`.

- [ ] **Step 3: write `scripts/style_check.py`**

```python
#!/usr/bin/env python3
"""fwts-review: mechanical fwts coding-style checks on lines added per commit.

Usage: style_check.py [--repo DIR] [--json FILE] BASE HEAD

Prints "<sha8> <path>:<line> <rule> <message>" for each finding.
Exit status: 0 on success (with or without findings), 2 on git error.
The rules come from references/coding-style.md. Findings are hints: the
reviewer drops false positives before writing the report.
"""
import argparse
import dataclasses
import json
import re
import subprocess
import sys


@dataclasses.dataclass
class Finding:
    commit: str
    path: str
    line: int
    rule: str
    message: str

    def text(self):
        return f"{self.commit[:8]} {self.path}:{self.line} {self.rule} {self.message}"


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True,
                       text=True, errors="replace")
    if check and r.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def blob(repo, commit, path):
    r = subprocess.run(["git", "-C", repo, "show", f"{commit}:{path}"],
                       capture_output=True)
    return r.stdout if r.returncode == 0 else None


HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def parse_diff(text):
    """Return [(path, lineno, line)] for every added line of a -U0 diff."""
    out, path, ln, in_hdr = [], None, 0, False
    for raw in text.split("\n"):
        if raw.startswith("diff --git "):
            in_hdr, path = True, None
            continue
        if in_hdr:
            if raw.startswith("+++ "):
                p = raw[4:]
                path = None if p == "/dev/null" else (p[2:] if p.startswith("b/") else p)
                continue
            if not raw.startswith("@@"):
                continue
            in_hdr = False
        m = HUNK_RE.match(raw)
        if m:
            ln = int(m.group(1))
            continue
        if path and raw.startswith("+"):
            out.append((path, ln, raw[1:]))
            ln += 1
    return out


NON_TEST_DIRS = ("src/lib/", "src/utilities/", "src/libfwtsacpica/",
                 "src/libfwtsiasl/")
ACPICA_TYPES_OK = ("src/libfwtsacpica/", "src/libfwtsiasl/")


def is_acpica(p):
    return p.startswith("src/acpica/")


def is_c(p):
    return p.endswith((".c", ".h")) and not is_acpica(p)


def is_test_src(p):
    return is_c(p) and p.startswith("src/") and not p.startswith(NON_TEST_DIRS)


def is_textual(p):
    return not (p.startswith("fwts-test/") and p.endswith(".log"))


def rx(s):
    return re.compile(s)


TEXT_RULES = [
    ("trailing-ws", rx(r"[ \t]+\r?$"), "trailing whitespace"),
    ("cr", rx(r"\r"), "CR character; use LF line endings"),
    ("ws-after-backslash", rx(r"\\[ \t]+\r?$"),
     "whitespace after line-continuation backslash"),
    ("non-ascii", rx(r"[^\x00-\x7f]"),
     "non-ASCII character (smart quote or symbol pasted from a spec?)"),
    ("control-char", rx(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"),
     "control character"),
]

RAW_C_RULES = [
    ("indented-preproc",
     rx(r"^\s+#\s*(?:if|ifdef|ifndef|elif|else|endif|include|define|undef)\b"),
     "preprocessor directive must start in column 0"),
    ("space-indent", rx(r"^ +(?!\*)\S"), "indent with tabs, not spaces"),
    ("space-before-tab", rx(r"^[ \t]* \t"), "space before tab in indentation"),
    ("pri-space", rx(r'"PRI[diouxX]|\bPRI[diouxX]\w*"'),
     'put spaces around PRI* macros: "%" PRIx32 " "'),
    ("space-before-nl", rx(r'[ \t]\\n"'), "whitespace before \\n in a string"),
    ("log-newline",
     rx(r'\bfwts_(?:log_\w+|failed|passed|warning|skipped|advice|infoonly)'
        r'\s*\(.*\\n"\s*[,)]'),
     "fwts log messages must not end with \\n"),
]

CODE_RULES = [
    ("kw-space", rx(r"\b(?:if|for|while|switch)\("), "space after keyword: 'if ('"),
    ("brace-space", rx(r"\)\{|\belse\{"), "space before '{'"),
    ("sizeof-space", rx(r"\bsizeof\s+\("), "sizeof(x), no space"),
    ("paren-space", rx(r"\(\s+[^\s\\]|[^\s(]\s+\)"), "no spaces inside parentheses"),
    ("comma-space", rx(r",(?=\S)"), "space after comma"),
    ("incdec-space", rx(r"\w\s+(?:\+\+|--)\s*[;)\],]"), "no space before ++/--"),
    ("return-paren", rx(r"\breturn\s*\([^()]*\)\s*;"), "'return x;', not 'return (x);'"),
    ("c99-for-decl",
     rx(r"\bfor\s*\(\s*(?:const\s+)?(?:(?:unsigned|signed|struct)\s+)?\w+\s+\**\w+\s*="),
     "declare loop variables at the top of the block"),
    ("star-with-type",
     rx(r"\b(?:char|int|void|long|short|bool|float|double|\w+_t)\*+\s+\w"),
     "'*' goes next to the name: 'char *p'"),
    ("bare-unsigned", rx(r"\bunsigned\s+(?!(?:int|char|long|short)\b)[A-Za-z_]"),
     "bare 'unsigned'; use uintN_t or 'unsigned int'"),
    ("unused-attr", rx(r"__attribute__\s*\(\(\s*(?:__)?unused"),
     "use FWTS_UNUSED(x)"),
    ("void-cast-unused", rx(r"^\s*\(void\)\s*\w+\s*;"),
     "use FWTS_UNUSED(x) instead of (void)x"),
    ("empty-params",
     rx(r"^(?:(?:static|inline|const|extern)\s+)*(?:struct\s+)?\w+[\s*]+\w+\(\)\s*[;{]?\s*$"),
     "use (void) for an empty parameter list"),
    ("func-brace-same-line",
     rx(r"^(?!(?:typedef|struct|union|enum|if|for|while|switch|do|else)\b)"
        r"[A-Za-z_][\w\s*,]*\b\w+\s*\([^;=]*\)\s*\{\s*$"),
     "function '{' goes on its own line"),
    ("unsafe-string", rx(r"\b(?:sprintf|vsprintf|strcpy|strcat|gets)\s*\("),
     "use snprintf/strlcpy/strlcat"),
]
NONSTD_INT = ("nonstd-int", rx(r"\b(?:[us](?:8|16|32|64)|U?INT(?:8|16|32|64)|BOOLEAN)\b"),
              "use uint8_t/uint16_t/uint32_t/uint64_t/bool")
TEST_ONLY_RULES = [
    ("printf-in-test", rx(r"\b(?:printf|fprintf|vprintf|puts|putchar)\s*\("),
     "no printf() in tests; use fwts_log_*()"),
    ("exit-in-test", rx(r"\b(?:exit|_exit|abort)\s*\("),
     "no exit() in tests; return FWTS_ERROR"),
]

STR_RE = rx(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
PCT_L = rx(r"%[-+ #0]*\d*(?:\.\d+)?l{1,2}[diouxX]")
LABEL_RE = rx(r'\bfwts_failed\s*\(\s*\w+\s*,\s*\w+\s*,\s*"([^"]*)"')
CAMEL_RE = rx(r"^[A-Z][A-Za-z0-9]*$")
GUARD_RE = rx(r"^#\s*define\s+(\w*_H_*)\s*$")
FWTS_GUARD_RE = rx(r"^__FWTS_[A-Z0-9_]+_H__$")
COMMENT_SPACE_RE = rx(r"/\*[^\s*/]|[^\s*/]\*/")
COMMENT_OPEN_RE = rx(r"^\s*/\*\s*\S")
COMMENT_BODY_RE = rx(r"^\s*\*(?:\s|/|$)")
CALL_SPACE_RE = rx(r"\b([A-Za-z_]\w*)\s+\(")
NOT_CALLS = {
    "if", "for", "while", "switch", "return", "sizeof", "else", "do", "case",
    "defined", "__attribute__", "__attribute", "typeof", "__typeof__", "asm",
    "__asm__", "void", "char", "int", "long", "short", "unsigned", "signed",
    "float", "double", "bool", "const", "static", "struct", "enum", "union",
    "volatile", "inline", "extern", "goto",
}
FUNC_OPEN_RE = rx(r"^\{\s*$")
DECL_RE = rx(
    r"^\t(?!(?:return|goto|break|continue|case|default|if|for|while|switch|do|else)\b)"
    r"(?:(?:static|const|volatile|register|unsigned|signed|struct|enum|union|long|short)\s+)*"
    r"[A-Za-z_]\w*(?:\s+|\s*\*+\s*)\**[A-Za-z_]\w*\s*(?:\[[^\]]*\]\s*)*(?:[=;,]|$)")


def strip_strings(s):
    return STR_RE.sub(lambda m: m.group(0)[0] * 2, s)


def check_c(path, lines):
    """Rules for added lines of one C file; lines = [(lineno, text)]."""
    out = []

    def add(ln, rule, msg):
        out.append((path, ln, rule, msg))

    header = path.endswith(".h")
    in_comment = False
    prev_ln = prev_code = decl_state = None
    saw_decl = in_cont = False
    for ln, raw in lines:
        if prev_ln is None or ln != prev_ln + 1:
            in_comment, prev_code, decl_state = False, None, None
        prev_ln = ln
        line = raw.rstrip("\r")

        for rule, r, msg in RAW_C_RULES:
            if r.search(line):
                add(ln, rule, msg)
        if any(PCT_L.search(lit) for lit in STR_RE.findall(line)):
            add(ln, "pct-l", "use PRI* macros (or %zu for size_t) instead of %l")
        m = LABEL_RE.search(line)
        if m and not CAMEL_RE.match(m.group(1)):
            add(ln, "label-camel", f'fwts_failed label "{m.group(1)}" must be CamelCase')
        if header:
            m = GUARD_RE.match(line)
            if m and not FWTS_GUARD_RE.match(m.group(1)):
                add(ln, "header-guard", "header guard should be __FWTS_<NAME>_H__")

        s = strip_strings(line)
        if COMMENT_SPACE_RE.search(s):
            add(ln, "comment-space", "space after '/*' and before '*/'")
        if not in_comment and COMMENT_OPEN_RE.match(s) and "*/" not in s:
            add(ln, "comment-open-text", "multi-line comment: put '/*' on its own line")

        if in_comment or COMMENT_BODY_RE.match(s):
            if "*/" not in s:
                continue
            in_comment = False
            s = s.split("*/", 1)[1]
        code = re.sub(r"/\*.*?\*/", " ", s)
        if "/*" in code:
            code, in_comment = code.split("/*", 1)[0], True
        if "//" in code:
            add(ln, "cpp-comment", "use /* */ comments, not //")
            code = code.split("//", 1)[0]
        st = code.strip()

        if st and not st.startswith("#"):
            for rule, r, msg in CODE_RULES:
                if r.search(code):
                    add(ln, rule, msg)
            if not path.startswith(ACPICA_TYPES_OK) and NONSTD_INT[1].search(code):
                add(ln, NONSTD_INT[0], NONSTD_INT[2])
            for name in CALL_SPACE_RE.findall(code):
                if name not in NOT_CALLS and not name.endswith("_t"):
                    add(ln, "call-space", f"no space between '{name}' and '('")
                    break
            if is_test_src(path):
                for rule, r, msg in TEST_ONLY_RULES:
                    if r.search(code):
                        add(ln, rule, msg)

        if re.match(r"else\b", st) and prev_code == "}":
            add(ln, "else-newline", "use '} else {' on one line")

        if not line.strip():
            decl_state = None
        elif st:
            if FUNC_OPEN_RE.match(line):
                decl_state, saw_decl, in_cont = "decls", False, False
            elif decl_state:
                if in_cont:
                    in_cont = not st.endswith(";")
                elif DECL_RE.match(code):
                    saw_decl, in_cont = True, not st.endswith(";")
                else:
                    if saw_decl:
                        add(ln, "decl-blank",
                            "blank line needed between declarations and code")
                    decl_state = None
            prev_code = st
    return out


def check_added(added):
    out, by_path = [], {}
    for path, ln, line in added:
        by_path.setdefault(path, []).append((ln, line))
    for path, lines in by_path.items():
        if is_acpica(path):
            out.append((path, lines[0][0], "acpica-modified",
                        "src/acpica is upstream ACPICA; changes must come from ACPICA"))
            continue
        if is_textual(path):
            for ln, line in lines:
                for rule, r, msg in TEXT_RULES:
                    if r.search(line):
                        out.append((path, ln, rule, msg))
        if is_c(path):
            out += check_c(path, lines)
    return out


def check_file_ends(added, get_blob):
    out, touched = [], {}
    for path, ln, _ in added:
        touched.setdefault(path, set()).add(ln)
    for path, lns in touched.items():
        if is_acpica(path) or not is_textual(path):
            continue
        data = get_blob(path)
        if not data or b"\0" in data:
            continue
        text = data.decode("utf-8", "replace")
        last = text.count("\n") + (0 if text.endswith("\n") else 1)
        if last in lns:
            if not text.endswith("\n"):
                out.append((path, last, "no-final-newline", "file must end with a newline"))
            elif text.endswith("\n\n"):
                out.append((path, last, "blank-line-eof", "blank line at end of file"))
        if 1 in lns and data.startswith(b"\xef\xbb\xbf"):
            out.append((path, 1, "bom", "UTF-8 BOM"))
    return out


SUBJECT_RE = rx(r"^(?:[\w.+/-]+(?: [\w.+/-]+)*: )+\S")
TRAILER_RE = rx(r"^[A-Z][\w-]*: ")


def check_commit_msg(msg, author_email):
    out = []

    def add(i, rule, m):
        out.append(("COMMIT_MSG", i, rule, m))

    lines = msg.rstrip("\n").split("\n")
    subj = lines[0]
    if not subj.startswith('Revert "') and not SUBJECT_RE.match(subj):
        add(1, "subject-format", "subject should be 'component: [sub: ]summary'")
    if len(subj) > 75:
        add(1, "subject-length", f"subject is {len(subj)} chars (max 75)")
    if not [l for l in lines[1:] if l.strip() and not TRAILER_RE.match(l)]:
        add(1, "empty-body", "commit message has no body")
    sobs = [l for l in lines if l.startswith("Signed-off-by:")]
    if not sobs:
        add(len(lines), "no-signoff", "missing Signed-off-by")
    elif not any(author_email.lower() in l.lower() for l in sobs):
        add(len(lines), "signoff-author", f"no Signed-off-by for author <{author_email}>")
    for i, l in enumerate(lines, 1):
        if l != l.rstrip():
            add(i, "msg-trailing-ws", "trailing whitespace in commit message")
    return out


def run(repo, base, head):
    findings, labels = [], {}
    commits = git(repo, "rev-list", "--reverse", "--no-merges",
                  f"{base}..{head}").split()
    for c in commits:
        diff = git(repo, "diff", "-M", "-U0", "--no-color", "--no-ext-diff",
                   f"{c}^", c)
        added = parse_diff(diff)
        fs = check_added(added)
        fs += check_file_ends(added, lambda p, c=c: blob(repo, c, p))
        fs += check_commit_msg(git(repo, "log", "-1", "--format=%B", c),
                               git(repo, "log", "-1", "--format=%ae", c).strip())
        findings += [Finding(c, *f) for f in fs]
        for path, ln, line in added:
            m = LABEL_RE.search(line) if is_c(path) else None
            if m:
                labels.setdefault(m.group(1), (c, path, ln))
    for label, (c, path, ln) in labels.items():
        hits = git(repo, "grep", "-F", "-n", f'"{label}"', head, "--", "src",
                   check=False).splitlines()
        if len(hits) > 1:
            findings.append(Finding(c, path, ln, "label-dup",
                                    f'fwts_failed label "{label}" appears {len(hits)} times in the tree'))
    return findings


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--json")
    ap.add_argument("base")
    ap.add_argument("head")
    a = ap.parse_args(argv)
    try:
        fs = run(a.repo, a.base, a.head)
    except RuntimeError as e:
        print(f"style_check: {e}", file=sys.stderr)
        return 2
    for f in fs:
        print(f.text())
    if a.json:
        with open(a.json, "w") as fh:
            json.dump([dataclasses.asdict(f) for f in fs], fh, indent=1)
    print(f"# {len(fs)} findings", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: run the tests and confirm they pass**

Run: `chmod +x scripts/style_check.py && python3 -m pytest -q tests/test_style_check.py`
Expected: all tests pass. If a rule regex misfires on `CLEAN`, fix the regex, not the test.

- [ ] **Step 5: smoke-test on fwts history** (a pure style-cleanup commit and a normal one)

```bash
scripts/style_check.py --repo ~/work/fwts a5cbe72c^ a5cbe72c | head -20
scripts/style_check.py --repo ~/work/fwts HEAD~5 HEAD | head -40
```

Expected:
- exit 0
- the output looks plausible
- a cleanup commit produces few or no findings on its own added lines

If a rule fires on more than about 30% of the lines in a normal commit, it is too noisy: tighten it and add a negative case to `CASES`, or a clean line to `CLEAN`.

- [ ] **Step 6: commit**

```bash
git add scripts/style_check.py tests/test_style_check.py
git commit -q -m "fwts-review: add style_check.py

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 3: `scripts/spec_lookup.sh` (TDD)

**Files:** create `tests/test_spec_lookup.py` and `scripts/spec_lookup.sh`.

Interface:
- `update`
- `acpi REGEX`: prints `file.rst:LINE [Heading] text`
- `list SUBDIR`
- `pdf SUBDIR REGEX [NAME_GLOB]`: prints `relpath p.N: text` for paged files (`.pdf`, `.txt`) and `relpath l.N: text` for `.docx`/`.odt`
- `actbl SIG`

Matching is case-insensitive. Output is capped at `$MAX` lines (default 40).

Environment overrides: `ACPI_SPEC_DIR`, `SPEC_DOC_DIR`, `SPEC_CACHE_DIR`, `FWTS_REPO`, `MAX`.

- [ ] **Step 1: write the failing tests** in `tests/test_spec_lookup.py`

```python
import glob
import os
import subprocess
import zipfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "spec_lookup.sh"


def run(*args, **env):
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True,
                          text=True, env={**os.environ, **env})


def test_acpi_heading(tmp_path):
    src = tmp_path / "source"
    src.mkdir()
    (src / "05_Tables.rst").write_text(
        "Intro\n=====\n\ntext\n\n"
        "IO Remapping Table\n------------------\n\n"
        "The IORT signature is 'IORT'.\n")
    r = run("acpi", "iort signature", ACPI_SPEC_DIR=str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == \
        "05_Tables.rst:9 [IO Remapping Table] The IORT signature is 'IORT'."


def test_actbl(tmp_path):
    inc = tmp_path / "src/acpica/source/include"
    inc.mkdir(parents=True)
    (inc / "actbl2.h").write_text(
        "typedef struct acpi_table_foo\n{\n    UINT32 A;\n} ACPI_TABLE_FOO;\n\n"
        "typedef struct acpi_table_bar\n{\n} ACPI_TABLE_BAR;\n\n"
        "typedef struct acpi_foo_node\n{\n    UINT8 Type;\n} ACPI_FOO_NODE;\n")
    r = run("actbl", "FOO", FWTS_REPO=str(tmp_path))
    assert "ACPI_TABLE_FOO" in r.stdout and "ACPI_FOO_NODE" in r.stdout
    assert "BAR" not in r.stdout


def test_paged_text_page_numbers(tmp_path):
    d = tmp_path / "docs/TPM"
    d.mkdir(parents=True)
    (d / "spec.txt").write_text("page one\n\fpage two\n  TPM2 Start Method\n")
    r = run("pdf", "TPM", "start method", SPEC_DOC_DIR=str(tmp_path / "docs"),
            SPEC_CACHE_DIR=str(tmp_path / "cache"))
    assert r.stdout.strip() == "spec.txt p.2: TPM2 Start Method"


def test_docx_and_glob(tmp_path):
    d = tmp_path / "docs/ACPI"
    d.mkdir(parents=True)
    with zipfile.ZipFile(d / "SPCR(SPCR).docx", "w") as z:
        z.writestr("word/document.xml",
                   "<w:document><w:p><w:r><w:t>Intro</w:t></w:r></w:p>"
                   "<w:p><w:r><w:t>Interface Type &amp; Baud</w:t></w:r></w:p>"
                   "</w:document>")
    (d / "other.txt").write_text("Interface Type here too\n")
    r = run("pdf", "ACPI", "interface type", "*SPCR*",
            SPEC_DOC_DIR=str(tmp_path / "docs"),
            SPEC_CACHE_DIR=str(tmp_path / "cache"))
    assert r.stdout.strip() == "SPCR(SPCR).docx l.2: Interface Type & Baud"


REAL = glob.glob(os.path.expanduser(
    "~/CloudStation/Document/ACPI/TCG_ACPIGeneralSpecification*.pdf"))


@pytest.mark.skipif(not REAL, reason="TCG ACPI spec PDF not available")
def test_real_pdf(tmp_path):
    r = run("pdf", "ACPI", "start method", "*TCG_ACPI*",
            SPEC_CACHE_DIR=str(tmp_path / "cache"))
    assert " p." in r.stdout
```

- [ ] **Step 2: run them and confirm they fail**

Run: `python3 -m pytest -q tests/test_spec_lookup.py`
Expected: failures, because the script is missing (bash exits 127).

- [ ] **Step 3: write `scripts/spec_lookup.sh`**

```bash
#!/bin/bash
# fwts-review spec lookup helper.
#   spec_lookup.sh update                         git pull ~/work/ACPI_spec
#   spec_lookup.sh acpi REGEX                     search ACPI spec RST (file:line [heading] text)
#   spec_lookup.sh list SUBDIR                    list documents in the spec library
#   spec_lookup.sh pdf SUBDIR REGEX [NAME_GLOB]   search pdf/docx/odt/txt documents (page or line)
#   spec_lookup.sh actbl SIG                      print ACPICA actbl*.h structs for a table
# Case-insensitive. Env: ACPI_SPEC_DIR SPEC_DOC_DIR SPEC_CACHE_DIR FWTS_REPO MAX
set -u
ACPI_SPEC_DIR=${ACPI_SPEC_DIR:-$HOME/work/ACPI_spec}
SPEC_DOC_DIR=${SPEC_DOC_DIR:-$HOME/CloudStation/Document}
SPEC_CACHE_DIR=${SPEC_CACHE_DIR:-$HOME/.cache/fwts-review/specs}
FWTS_REPO=${FWTS_REPO:-$HOME/work/fwts}
MAX=${MAX:-40}

die() { echo "spec_lookup: $*" >&2; exit 2; }
usage() { sed -n '2,9p' "$0" >&2; exit 2; }

cmd_update() {
	git -C "$ACPI_SPEC_DIR" pull --ff-only -q 2>&1 ||
		echo "WARNING: ACPI_spec pull failed; using local copy" >&2
	git -C "$ACPI_SPEC_DIR" log -1 --format='ACPI_spec at %h (%cs) %s'
}

cmd_acpi() {
	[ -d "$ACPI_SPEC_DIR/source" ] || die "no $ACPI_SPEC_DIR/source"
	awk -v re="$1" '
		FNR == 1 { head = ""; prev = "" }
		/^(=+|-+|~+|\^+|"+|\*+|#+)$/ && length($0) >= 3 && prev !~ /^[ \t]*$/ {
			head = prev; prev = $0; next
		}
		tolower($0) ~ tolower(re) {
			n = split(FILENAME, p, "/")
			printf "%s:%d [%s] %s\n", p[n], FNR, head, $0
		}
		{ prev = $0 }' "$ACPI_SPEC_DIR"/source/*.rst | head -n "$MAX"
}

list_docs() {	# SUBDIR [GLOB]
	[ -d "$SPEC_DOC_DIR/$1" ] || die "no $SPEC_DOC_DIR/$1"
	find "$SPEC_DOC_DIR/$1" -type f -iname "${2:-*}" \
		\( -iname '*.pdf' -o -iname '*.docx' -o -iname '*.odt' -o -iname '*.txt' \) |
		sort -V -r
}

to_text() {	# FILE -> prints cache path
	local f=$1 key out
	key=$(printf '%s:%s' "$f" "$(stat -c %Y "$f")" | sha1sum | cut -c1-40)
	out=$SPEC_CACHE_DIR/$key.txt
	mkdir -p "$SPEC_CACHE_DIR"
	if [ ! -s "$out" ]; then
		case "${f,,}" in
		*.pdf) pdftotext -layout "$f" "$out" 2>/dev/null || { rm -f "$out"; return 1; } ;;
		*.docx|*.odt) python3 - "$f" "$out" <<'EOF' || return 1
import html, re, sys, zipfile
f, out = sys.argv[1], sys.argv[2]
name = "content.xml" if f.lower().endswith(".odt") else "word/document.xml"
x = zipfile.ZipFile(f).read(name).decode("utf-8", "replace")
x = re.sub(r"</(?:w:p|text:p|text:h)>", "\n", x)
x = re.sub(r"<(?:w:tab|text:tab)/>", "\t", x)
x = re.sub(r"<[^>]+>", "", x)
open(out, "w").write(html.unescape(x))
EOF
			;;
		*) cp "$f" "$out" ;;
		esac
	fi
	echo "$out"
}

cmd_pdf() {	# SUBDIR REGEX [GLOB]
	local f txt rel paged
	list_docs "$1" "${3:-*}" | while IFS= read -r f; do
		txt=$(to_text "$f") || { echo "WARNING: cannot convert $f" >&2; continue; }
		rel=${f#"$SPEC_DOC_DIR/$1/"}
		case "${f,,}" in *.docx|*.odt) paged=0 ;; *) paged=1 ;; esac
		awk -v re="$2" -v fn="$rel" -v paged="$paged" '
			BEGIN { p = 1 }
			{ p += gsub(/\f/, "") }
			tolower($0) ~ tolower(re) {
				sub(/^[ \t]+/, "")
				if (paged) printf "%s p.%d: %s\n", fn, p, $0
				else printf "%s l.%d: %s\n", fn, FNR, $0
			}' "$txt"
	done | head -n "$MAX"
}

cmd_actbl() {
	local sig
	sig=$(printf '%s' "$1" | tr 'A-Z' 'a-z')
	awk -v sig="$sig" '
		/^typedef struct acpi_/ {
			keep = ($3 == "acpi_table_" sig || index($3, "acpi_" sig "_") == 1)
			if (keep) printf "%s:%d\n", FILENAME, FNR
		}
		keep { print }
		keep && /^}/ { keep = 0; print "" }' \
		"$FWTS_REPO"/src/acpica/source/include/actbl*.h
}

case "${1:-}" in
update) cmd_update ;;
acpi)	[ $# -ge 2 ] || usage; cmd_acpi "$2" ;;
list)	[ $# -ge 2 ] || usage; list_docs "$2" ;;
pdf)	[ $# -ge 3 ] || usage; cmd_pdf "$2" "$3" "${4:-}" ;;
actbl)	[ $# -ge 2 ] || usage; cmd_actbl "$2" ;;
*)	usage ;;
esac
```

Note: `cmd_pdf` passes `"${4:-}"` and then uses `${3:-*}`, so an empty glob falls back to `*`.

- [ ] **Step 4: run the tests and confirm they pass**

Run: `chmod +x scripts/spec_lookup.sh && python3 -m pytest -q tests/test_spec_lookup.py`
Expected: all pass. `test_real_pdf` passes, or is skipped if the PDF is absent.

- [ ] **Step 5: smoke-test against the real sources**

```bash
scripts/spec_lookup.sh update
scripts/spec_lookup.sh acpi 'Platform Communications Channel Table' | head -5
scripts/spec_lookup.sh actbl IORT | head -20
scripts/spec_lookup.sh pdf ACPI/IORT 'Root Complex' '*E.f*' | head -5
```

Expected: every command prints matches.

- [ ] **Step 6: commit**

```bash
git add scripts/spec_lookup.sh tests/test_spec_lookup.py
git commit -q -m "fwts-review: add spec_lookup.sh

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 4: `scripts/mbox_extract.py` (TDD) and `scripts/fetch.sh`

**Files:** create `tests/test_mbox_extract.py`, `scripts/mbox_extract.py` and `scripts/fetch.sh`.

What we verified in the pipermail raw mbox (`YYYY-Month.txt.gz`):
- It keeps `Message-ID`, `In-Reply-To` and `References`, and it keeps tabs.
- `From:` is obfuscated (`alkorv at posteo.uk (Al Korv)`).
- The HTML page holds its own id as `In-Reply-To=%3C<urlencoded-id>%3E`.
- **Replies can keep the `[PATCH]` subject without `Re:`**, so a series candidate must also contain a diff.

- [ ] **Step 1: write the failing tests** in `tests/test_mbox_extract.py`

```python
import email
import mailbox
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import mbox_extract as mx  # noqa: E402

DIFF = "---\n x.c | 1 +\ndiff --git a/x.c b/x.c\n--- a/x.c\n+++ b/x.c\n"


def mk(mid, subject, irt=None, body=DIFF):
    hdr = f"From: a at b.c (A B)\nSubject: {subject}\nMessage-ID: <{mid}>\n"
    if irt:
        hdr += f"In-Reply-To: <{irt}>\n"
    return email.message_from_string(hdr + "\n" + body)


def ids(msgs):
    return [mx.clean_id(m["Message-ID"]) for m in msgs]


def test_norm_from():
    assert mx.norm_from("alkorv at posteo.uk (Al Korv)") == "Al Korv <alkorv@posteo.uk>"
    assert mx.norm_from("A <a@b.c>") == "A <a@b.c>"


def test_msgid_from_html():
    page = '<a href="mailto:x?Subject=y&In-Reply-To=%3C1-a%40b.uk%3E">'
    assert mx.msgid_from_html(page) == "1-a@b.uk"


def test_single_patch_ignores_reply_with_same_subject():
    msgs = [mk("p", "[PATCH] [v4] fwts: x"),
            mk("r", "[PATCH] [v4] fwts: x", irt="p", body="looks good\n")]
    assert ids(mx.select_series(msgs, "p")) == ["p"]


def test_series_with_cover_from_middle_patch():
    msgs = [mk("c", "[PATCH 0/2] cover", body="cover\n"),
            mk("p1", "[PATCH 1/2] a: one", irt="c"),
            mk("p2", "[PATCH 2/2] a: two", irt="c"),
            mk("re", "Re: [PATCH 1/2] a: one", irt="p1")]
    assert ids(mx.select_series(msgs, "p2")) == ["p1", "p2"]
    assert ids(mx.select_series(msgs, "c")) == ["p1", "p2"]


def test_series_without_cover_skips_older_version():
    msgs = [mk("o1", "[PATCH 1/2] a: one"),
            mk("o2", "[PATCH 2/2] a: two", irt="o1"),
            mk("n1", "[PATCH v2 1/2] a: one", irt="o1"),
            mk("n2", "[PATCH v2 2/2] a: two", irt="n1")]
    assert ids(mx.select_series(msgs, "n2")) == ["n1", "n2"]


def test_incomplete_series_raises():
    msgs = [mk("p1", "[PATCH 1/3] a: one"), mk("p2", "[PATCH 2/3] a: two", irt="p1")]
    with pytest.raises(mx.IncompleteSeries):
        mx.select_series(msgs, "p1")


def test_next_month():
    assert mx.next_month("2025", "December") == ("2026", "January")
    assert mx.next_month("2025", "August") == ("2025", "September")


def test_write_mbox_normalises_from(tmp_path):
    out = tmp_path / "s.mbox"
    mx.write_mbox([mk("p", "[PATCH] a: x")], str(out))
    (m,) = list(mailbox.mbox(str(out)))
    assert m["From"] == "A B <a@b.c>"
```

- [ ] **Step 2: run them and confirm they fail**

Run: `python3 -m pytest -q tests/test_mbox_extract.py`
Expected: `ModuleNotFoundError: No module named 'mbox_extract'`.

- [ ] **Step 3: write `scripts/mbox_extract.py`**

```python
#!/usr/bin/env python3
"""Extract a patch (or the whole [PATCH n/m] series) from the fwts-devel
pipermail archive into an mbox that `git am` can apply.

Usage: mbox_extract.py URL OUT_MBOX
  URL: https://lists.ubuntu.com/archives/fwts-devel/YYYY-Month/NNNNNN.html
Prints MSGID=<id> and PATCHES=<n>. Exit 2 usage, 3 fetch/lookup failure.
"""
import gzip
import mailbox
import re
import sys
import tempfile
import urllib.parse
import urllib.request

ARCHIVE = "https://lists.ubuntu.com/archives/fwts-devel"
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
URL_RE = re.compile(r"/fwts-devel/(\d{4})-([A-Za-z]+)/\d+\.html")
LEAD_RE = re.compile(r"^((?:\[[^\]]*\]\s*)+)")
NM_RE = re.compile(r"(\d+)/(\d+)")


class IncompleteSeries(Exception):
    pass


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def clean_id(v):
    return str(v or "").strip().strip("<>").strip()


def norm_from(value):
    m = re.match(r"\s*(\S+) at (\S+) \((.*)\)\s*$", str(value))
    return f"{m.group(3)} <{m.group(1)}@{m.group(2)}>" if m else str(value)


def msgid_from_html(text):
    m = re.search(r"In-Reply-To=%3C(.*?)%3E", text)
    return urllib.parse.unquote(m.group(1)) if m else None


def subject(msg):
    return " ".join(str(msg.get("Subject", "")).split())


def has_diff(msg):
    body = msg.get_payload(decode=False)
    body = body if isinstance(body, str) else str(body)
    return "diff --git " in body or "\n+++ " in body


def patch_info(msg):
    """(key, n, m) for a [PATCH] subject, n/m None for single patches."""
    s = subject(msg)
    if s.lower().startswith("re:"):
        return None
    m = LEAD_RE.match(s)
    if not m or "PATCH" not in m.group(1).upper():
        return None
    lead = m.group(1)
    nm = NM_RE.search(lead)
    key = " ".join(NM_RE.sub("", lead).split())
    return (key, int(nm.group(1)), int(nm.group(2))) if nm else (key, None, None)


def select_series(msgs, target):
    by_id = {clean_id(m["Message-ID"]): m for m in msgs}
    t = by_id.get(target)
    if t is None:
        raise LookupError(f"message <{target}> not found in archive")
    info = patch_info(t)
    if info is None:
        raise LookupError("target is not a [PATCH] message")
    key, n, total = info
    if n is None:
        return [t]
    cands = {}
    for mid, m in by_id.items():
        i = patch_info(m)
        if i and i[0] == key and i[2] == total and (i[1] == 0 or has_diff(m)):
            cands[mid] = (i[1], clean_id(m["In-Reply-To"]))
    group, seen_n = {target}, {n}
    changed = True
    while changed:
        changed = False
        member_irts = {cands[g][1] for g in group if g in cands}
        for mid, (cn, irt) in cands.items():
            if mid in group or cn in seen_n:
                continue
            if irt in group or mid in member_irts:
                group.add(mid)
                seen_n.add(cn)
                changed = True
    got = sorted((cands[g][0], g) for g in group if cands[g][0] != 0)
    if [x[0] for x in got] != list(range(1, total + 1)):
        raise IncompleteSeries(f"have {[x[0] for x in got]} of {total}")
    return [by_id[g] for _, g in got]


def next_month(year, month):
    i = MONTHS.index(month)
    return (str(int(year) + 1), MONTHS[0]) if i == 11 else (year, MONTHS[i + 1])


def load_month(year, month):
    data = fetch(f"{ARCHIVE}/{year}-{month}.txt.gz")
    try:
        data = gzip.decompress(data)
    except OSError:
        pass
    with tempfile.NamedTemporaryFile(suffix=".mbox", delete=False) as f:
        f.write(data)
    return list(mailbox.mbox(f.name))


def write_mbox(msgs, out):
    box = mailbox.mbox(out, create=True)
    box.lock()
    try:
        for m in msgs:
            frm = norm_from(m["From"])
            del m["From"]
            m["From"] = frm
            box.add(m)
        box.flush()
    finally:
        box.unlock()
        box.close()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    url, out = argv
    m = URL_RE.search(url)
    if not m:
        print("mbox_extract: not a fwts-devel pipermail message URL", file=sys.stderr)
        return 2
    year, month = m.groups()
    try:
        target = msgid_from_html(fetch(url).decode("utf-8", "replace"))
        if not target:
            raise LookupError("no Message-ID in page")
        msgs = load_month(year, month)
        try:
            series = select_series(msgs, target)
        except IncompleteSeries:
            msgs += load_month(*next_month(year, month))
            series = select_series(msgs, target)
    except Exception as e:  # network, lookup, incomplete series
        print(f"mbox_extract: {e}", file=sys.stderr)
        return 3
    write_mbox(series, out)
    print(f"MSGID={target}")
    print(f"PATCHES={len(series)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: run the tests and confirm they pass**

Run: `chmod +x scripts/mbox_extract.py && python3 -m pytest -q tests/test_mbox_extract.py`
Expected: all pass.

- [ ] **Step 5: write `scripts/fetch.sh`**

```bash
#!/bin/bash
# fwts-review: put the change under review into an isolated worktree.
#   fetch.sh [--repo DIR] [--base REF] INPUT
#   fetch.sh [--repo DIR] --cleanup ID
# INPUT: PR number | https://github.com/fwts/fwts/pull/N[/changes|commits/<sha>]
#        | https://lists.ubuntu.com/archives/fwts-devel/YYYY-Month/NNNNNN.html | A..B
# Prints ID= KIND= BASE= HEAD= WORK= WT= (also saved to WORK/fetch.env).
# Exit: 0 ok, 2 usage, 3 fetch/apply failure (run --cleanup ID afterwards).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$HOME/work/fwts
BASE_REF=origin/master
CLEANUP=
while [ $# -gt 0 ]; do
	case "$1" in
	--repo) REPO=$2; shift 2 ;;
	--base) BASE_REF=$2; shift 2 ;;
	--cleanup) CLEANUP=$2; shift 2 ;;
	-h|--help) sed -n '2,9p' "$0"; exit 0 ;;
	*) break ;;
	esac
done
g() { git -C "$REPO" "$@"; }
fail() { echo "fetch: $*" >&2; exit 3; }

cleanup() {
	local id=$1 work=/tmp/fwts-review-$1 w
	for w in wt wt-base wt-clang; do
		if [ -d "$work/$w" ]; then g worktree remove --force "$work/$w" || true; fi
	done
	g worktree prune
	g update-ref -d "refs/fwts-review/$id" 2>/dev/null || true
	rm -rf "$work"
	echo "CLEANED=$id"
}

if [ -n "$CLEANUP" ]; then cleanup "$CLEANUP"; exit 0; fi
[ $# -eq 1 ] || { sed -n '2,9p' "$0" >&2; exit 2; }
IN=$1
SHA= N= MBOX=

# 1. classify the input and compute ID (before fetching, so cleanup is exact)
if [[ $IN =~ lists\.ubuntu\.com/archives/fwts-devel/ ]]; then
	KIND=ml
	MBOX=$(mktemp --suffix=.mbox)
	python3 "$HERE/mbox_extract.py" "$IN" "$MBOX" > "$MBOX.out" ||
		fail "could not extract the patch from $IN"
	MSGID=$(sed -n 's/^MSGID=//p' "$MBOX.out")
	ID=ml-$(printf '%s' "$MSGID" | sha1sum | cut -c1-8)
elif [[ $IN =~ ^([0-9]+)$ ]] ||
     [[ $IN =~ github\.com/fwts/fwts/pull/([0-9]+)(/(changes|commits)/([0-9a-f]{7,40}))? ]]; then
	KIND=pr
	N=${BASH_REMATCH[1]}
	SHA=${BASH_REMATCH[4]:-}
	ID=pr$N
	[ -n "$SHA" ] && ID=pr$N-${SHA:0:8}
elif [[ $IN == *..* ]]; then
	KIND=local
else
	sed -n '2,9p' "$0" >&2; exit 2
fi

g fetch -q origin || fail "git fetch origin failed"

# 2. resolve BASE/HEAD
case $KIND in
local)
	BASE=$(g rev-parse --verify "${IN%%..*}^{commit}") || fail "bad base ${IN%%..*}"
	HEAD=$(g rev-parse --verify "${IN##*..}^{commit}") || fail "bad head ${IN##*..}"
	ID=local-${HEAD:0:8}
	;;
esac
WORK=/tmp/fwts-review-$ID
if [ -e "$WORK" ]; then cleanup "$ID" > /dev/null; fi
mkdir -p "$WORK/logs"

case $KIND in
pr)
	g fetch -q origin "+pull/$N/head:refs/fwts-review/$ID" || fail "cannot fetch PR $N"
	gh pr view "$N" -R fwts/fwts \
		--json number,title,body,author,baseRefName,headRefName,commits,files,url \
		> "$WORK/pr.json" || echo "WARNING: gh pr view failed" >&2
	if [ -n "$SHA" ]; then
		g rev-parse -q --verify "$SHA^{commit}" > /dev/null ||
			g fetch -q origin "$SHA" || fail "commit $SHA not found"
		HEAD=$(g rev-parse "$SHA^{commit}")
		g merge-base --is-ancestor "$HEAD" "refs/fwts-review/$ID" ||
			echo "WARNING: $SHA is not in the current PR head (force-pushed?)" >&2
		BASE=$(g rev-parse "$HEAD^")
	else
		HEAD=$(g rev-parse "refs/fwts-review/$ID")
		BASE=$(g merge-base "$BASE_REF" "$HEAD")
	fi
	g worktree add -q --detach "$WORK/wt" "$HEAD"
	;;
local)
	g worktree add -q --detach "$WORK/wt" "$HEAD"
	;;
ml)
	mv "$MBOX" "$WORK/series.mbox"
	rm -f "$MBOX.out"
	BASE=$(g rev-parse "$BASE_REF")
	g worktree add -q --detach "$WORK/wt" "$BASE"
	if ! git -C "$WORK/wt" am -3 "$WORK/series.mbox" > "$WORK/logs/am.log" 2>&1; then
		git -C "$WORK/wt" am --abort > /dev/null 2>&1 || true
		cat "$WORK/logs/am.log" >&2
		fail "git am failed on $BASE_REF; retry with --base <older ref>"
	fi
	HEAD=$(git -C "$WORK/wt" rev-parse HEAD)
	g update-ref "refs/fwts-review/$ID" "$HEAD"
	;;
esac

tee "$WORK/fetch.env" <<EOF
ID=$ID
KIND=$KIND
BASE=$BASE
HEAD=$HEAD
WORK=$WORK
WT=$WORK/wt
EOF
```

- [ ] **Step 6: smoke-test all three input kinds, then clean up**

```bash
S=~/.copilot/skills/fwts-review/scripts
$S/fetch.sh HEAD~2..HEAD && $S/fetch.sh --cleanup local-$(git -C ~/work/fwts rev-parse --short=8 HEAD)
$S/fetch.sh 52 && $S/fetch.sh --cleanup pr52
$S/fetch.sh https://lists.ubuntu.com/archives/fwts-devel/2025-August/014058.html; echo "exit=$?"
git -C ~/work/fwts worktree list; git -C ~/work/fwts for-each-ref refs/fwts-review
```

Expected:
- local and PR: `ID=… BASE=… HEAD=…` is printed and `WT` exists.
- ml: either the mbox applies, printing `ID=ml-…`, or it exits 3 with an `am` error because the patch is old. Exit 3 is acceptable. Retry with `--base <commit from Aug 2025>`, e.g. `--base $(git -C ~/work/fwts rev-list -1 --before=2025-08-02 origin/master)`, and expect that retry to apply.
- After `--cleanup <ID>` for each run, `worktree list` shows only the main tree and `for-each-ref` prints nothing.

- [ ] **Step 7: commit**

```bash
git add scripts/mbox_extract.py scripts/fetch.sh tests/test_mbox_extract.py
git commit -q -m "fwts-review: add fetch.sh and mbox_extract.py

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 5: `scripts/build_test.sh`

**Files:** create `scripts/build_test.sh`. It is validated by a smoke run rather than pytest, because a build takes minutes.

Outputs in `WORK/logs/`:
- `build-<sha8>.log`
- `make-check.log`
- `clang.log`
- `cppcheck-{base,head,new}.txt`
- `build-base.log`
- `fx-{base,head}-*`
- `fixtures.txt`
- `regression.txt`
- `matrix.tsv`

It also writes a summary to stdout.

- [ ] **Step 1: write `scripts/build_test.sh`**

```bash
#!/bin/bash
# fwts-review: build every commit, make check, clang, cppcheck, fixture runs.
#   build_test.sh WORK BASE HEAD
# WORK is /tmp/fwts-review-<ID> from fetch.sh (WORK/wt must exist).
# Writes WORK/logs/*; prints a summary; always exits 0 unless usage error.
set -uo pipefail
[ $# -eq 3 ] || { sed -n '2,5p' "$0" >&2; exit 2; }
WORK=$1
WT=$WORK/wt
LOGS=$WORK/logs
J=$(nproc)
mkdir -p "$LOGS"
BASE=$(git -C "$WT" rev-parse "$2") || exit 2
HEAD=$(git -C "$WT" rev-parse "$3") || exit 2

full_build() {	# DIR LOG [CC]
	( cd "$1" && git clean -qfdx && autoreconf -ivf && CC=${3:-gcc} ./configure &&
	  make -j"$J" ) > "$2" 2>&1
}
incr_build() { ( cd "$1" && make -j"$J" ) > "$2" 2>&1; }
first_err() { grep -m1 -E 'error:|Error [0-9]+|configure: error' "$1" | cut -c1-160; }
add_wt() {	# NAME REV
	if [ -d "$WORK/$1" ]; then git -C "$WT" worktree remove --force "$WORK/$1"; fi
	git -C "$WT" worktree add -q --detach "$WORK/$1" "$2"
}

# 1. per-commit gcc build (bisectability)
declare -A GCC
first=1
COMMITS=$(git -C "$WT" rev-list --reverse --no-merges "$BASE..$HEAD")
for c in $COMMITS; do
	log=$LOGS/build-${c:0:8}.log
	if ! git -C "$WT" checkout -q --detach "$c"; then GCC[$c]="FAIL: checkout"; continue; fi
	if [ $first = 1 ]; then
		full_build "$WT" "$log"; rc=$?; first=0
	else
		incr_build "$WT" "$log"; rc=$?
		if [ $rc -ne 0 ]; then full_build "$WT" "$log"; rc=$?; fi
	fi
	if [ $rc -eq 0 ]; then GCC[$c]=PASS; else GCC[$c]="FAIL: $(first_err "$log")"; fi
	echo "gcc ${c:0:8}: ${GCC[$c]}"
done
git -C "$WT" checkout -q --detach "$HEAD"
HEAD_OK=0
[ "${GCC[$HEAD]:-}" = PASS ] && HEAD_OK=1

# 2. make check at HEAD
if [ $HEAD_OK = 1 ]; then
	( cd "$WT" && make check -j"$J" ) > "$LOGS/make-check.log" 2>&1; rc=$?
	sum=$(grep -E '^# (TOTAL|PASS|SKIP|XFAIL|FAIL|XPASS|ERROR):' "$LOGS/make-check.log" |
		sed 's/^# //; s/ \+/ /g' | paste -sd, -)
	failing=$(grep -E '^(FAIL|ERROR):' "$LOGS/make-check.log" | awk '{print $2}' | paste -sd' ' -)
	if [ $rc -eq 0 ]; then MC="PASS ($sum)"; else MC="FAIL ($sum) $failing"; fi
else
	MC="SKIP (head build failed)"
fi
echo "make check: $MC"

# 3. clang at HEAD
if ! command -v clang > /dev/null; then
	CL="SKIP (clang not installed)"
else
	add_wt wt-clang "$HEAD"
	if full_build "$WORK/wt-clang" "$LOGS/clang.log" clang; then CL=PASS
	else CL="FAIL: $(first_err "$LOGS/clang.log")"; fi
fi
echo "clang: $CL"

# 4. cppcheck: new warnings only, in changed non-ACPICA .c files
CHANGED_C=$(git -C "$WT" diff --name-only --diff-filter=AM "$BASE" "$HEAD" -- '*.c' |
	grep -v '^src/acpica/' || true)
run_cpp() {	# REV OUT
	local tmp f
	tmp=$(mktemp -d)
	for f in $CHANGED_C; do
		mkdir -p "$tmp/$(dirname "$f")"
		git -C "$WT" show "$1:$f" > "$tmp/$f" 2> /dev/null || rm -f "$tmp/$f"
	done
	( cd "$tmp" && cppcheck --enable=warning,style,portability --quiet \
		--suppress=missingIncludeSystem --template='{file}:{line}:{id}:{message}' . ) 2> "$2"
	rm -rf "$tmp"
}
norm() { sed -E 's/^([^:]*):[0-9]+:/\1::/' "$1" | sort -u; }
if ! command -v cppcheck > /dev/null; then
	CP="SKIP (cppcheck not installed)"
elif [ -z "$CHANGED_C" ]; then
	CP="N/A (no .c changes)"
else
	run_cpp "$BASE" "$LOGS/cppcheck-base.txt"
	run_cpp "$HEAD" "$LOGS/cppcheck-head.txt"
	comm -13 <(norm "$LOGS/cppcheck-base.txt") <(norm "$LOGS/cppcheck-head.txt") \
		> "$LOGS/cppcheck-new.txt"
	CP="$(wc -l < "$LOGS/cppcheck-new.txt") new"
fi
echo "cppcheck: $CP"

# 5. fixture runs for touched tests, base vs head
runfw() {	# TREE TEST DUMP
	"$1/src/fwts" --log-format="%line %owner " -w 80 --dumpfile="$3" "$2" - 2>&1 | cut -c7-
}
fsum() { grep -oE '[0-9]+ passed, [0-9]+ failed, [0-9]+ warning, [0-9]+ aborted' "$1" | tail -1; }
TOUCHED=$(for f in $(git -C "$WT" diff --name-only "$BASE" "$HEAD" -- 'src/*.c' |
		grep -vE '^src/(lib|acpica|libfwtsacpica|libfwtsiasl|utilities)/'); do
		[ -f "$WT/$f" ] && sed -n 's/^FWTS_REGISTER[A-Z_]*("\([^"]*\)".*/\1/p' "$WT/$f"
	done | sort -u)
: > "$LOGS/fixtures.txt"
if [ -z "$TOUCHED" ]; then
	FX="N/A (no test source touched)"
elif [ $HEAD_OK = 0 ]; then
	FX="SKIP (head build failed)"
else
	add_wt wt-base "$BASE"
	BASE_OK=0
	full_build "$WORK/wt-base" "$LOGS/build-base.log" && BASE_OK=1
	nfx=0 nchg=0
	for t in $TOUCHED; do
		dumps=$(ls "$WT"/fwts-test/"$t"-[0-9]*/acpidump-*.log 2> /dev/null)
		if [ -z "$dumps" ]; then echo "$t: no fixture coverage" >> "$LOGS/fixtures.txt"; continue; fi
		for d in $dumps; do
			rel=${d#"$WT"/}
			tag=$(echo "$rel" | tr '/' '_')
			runfw "$WT" "$t" "$d" > "$LOGS/fx-head-$tag"
			nfx=$((nfx + 1))
			if [ $BASE_OK = 1 ]; then
				runfw "$WORK/wt-base" "$t" "$d" > "$LOGS/fx-base-$tag"
				nd=$(diff "$LOGS/fx-base-$tag" "$LOGS/fx-head-$tag" | grep -c '^[<>]')
				[ "$nd" -gt 0 ] && nchg=$((nchg + 1))
				echo "$rel: base[$(fsum "$LOGS/fx-base-$tag")] head[$(fsum "$LOGS/fx-head-$tag")] diff=$nd lines" >> "$LOGS/fixtures.txt"
			else
				echo "$rel: head[$(fsum "$LOGS/fx-head-$tag")] (base build failed)" >> "$LOGS/fixtures.txt"
			fi
		done
	done
	FX="$nfx run, $nchg changed vs base"
fi
echo "fixtures: $FX"
sed 's/^/  /' "$LOGS/fixtures.txt"

# 6. regression-test presence
CHANGED=$(git -C "$WT" diff --name-only "$BASE" "$HEAD")
REG=$LOGS/regression.txt
: > "$REG"
if echo "$CHANGED" | grep -qE '^src/.*\.[ch]$' && ! echo "$CHANGED" | grep -q '^fwts-test/'; then
	echo "NO-FWTS-TEST-CHANGE: src/ changed but nothing under fwts-test/" >> "$REG"
fi
for s in $(git -C "$WT" diff --name-only --diff-filter=A "$BASE" "$HEAD" -- 'fwts-test/*/test-*.sh'); do
	grep -qF "$s" "$WT/Makefile.am" || echo "NOT-IN-TESTS: $s missing from TESTS in Makefile.am" >> "$REG"
done
if git -C "$WT" diff "$BASE" "$HEAD" -- src |
	grep -qE '^\+[[:space:]]*\{[[:space:]]*"[a-z][a-z0-9-]*",[[:space:]]*"'; then
	echo "$CHANGED" | grep -q '^doc/fwts.1' ||
		echo "OPTION-NO-MANPAGE: new option? doc/fwts.1 not updated" >> "$REG"
	echo "$CHANGED" | grep -q '^fwts-test/arg-help' ||
		echo "OPTION-NO-ARG-HELP: new option? fwts-test/arg-help-* not updated" >> "$REG"
fi
echo "regression checks:"
if [ -s "$REG" ]; then sed 's/^/  /' "$REG"; else echo "  none"; fi

# 7. matrix
{
	printf 'commit\tsubject\tgcc\tclang\tmake_check\tcppcheck_new\tfixtures\n'
	for c in $COMMITS; do
		subj=$(git -C "$WT" log -1 --format=%s "$c" | cut -c1-60)
		if [ "$c" = "$HEAD" ]; then
			printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "${c:0:8}" "$subj" "${GCC[$c]}" "$CL" "$MC" "$CP" "$FX"
		else
			printf '%s\t%s\t%s\t-\t-\t-\t-\n' "${c:0:8}" "$subj" "${GCC[$c]}"
		fi
	done
} > "$LOGS/matrix.tsv"
echo "matrix: $LOGS/matrix.tsv"
```

- [ ] **Step 2: syntax check**

Run: `bash -n scripts/build_test.sh && chmod +x scripts/build_test.sh`
Expected: no output.

- [ ] **Step 3: smoke run** on a two-commit local range that touches a test with fixtures

```bash
S=~/.copilot/skills/fwts-review/scripts
R=$(git -C ~/work/fwts log --format=%h -1 -- src/acpi/iort/iort.c)
eval "$($S/fetch.sh "$R~1..$R")"
$S/build_test.sh "$WORK" "$BASE" "$HEAD"
column -t -s $'\t' "$WORK/logs/matrix.tsv"
$S/fetch.sh --cleanup "$ID"
```

Expected:
- `gcc <sha>: PASS`
- `make check: PASS (TOTAL: …)`
- `clang: SKIP (clang not installed)`
- `cppcheck: SKIP (cppcheck not installed)`
- `fixtures: N run, 0 changed vs base` (or a non-zero count, if that commit changed the output)
- a matrix with one row

It takes several minutes, so run it in async mode.

- [ ] **Step 4: commit**

```bash
git add scripts/build_test.sh
git commit -q -m "fwts-review: add build_test.sh

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 6: `SKILL.md`

**Files:** create `SKILL.md`.

- [ ] **Step 1: write `SKILL.md`**

````markdown
---
name: fwts-review
description: Review fwts (Firmware Test Suite) changes: GitHub PRs on github.com/fwts/fwts, fwts-devel mailing-list patches on lists.ubuntu.com/archives/fwts-devel, or a local fwts commit range. Checks coding style, verifies the content against the ACPI/UEFI/SMBIOS/Arm/TCG specs, builds every commit, runs make check and fixture tests, then writes a review report and a draft reply. Activate whenever the user asks to review, check or ack an fwts PR, patch or commit, or pastes a github.com/fwts/fwts/pull URL or an fwts-devel archive URL, even without the word "skill".
---

# fwts-review

Review an fwts change in four phases (style → spec → build → test). The output is `~/work/fwts-reviews/<ID>/report.md` plus `reply.md`.

**Never** post to GitHub or send mail. **Never** modify `~/work/fwts` (work only in `/tmp/fwts-review-<ID>/`). **Always** run the cleanup step, even after an error.

Scripts are in `~/.copilot/skills/fwts-review/scripts/` (`$S` below). References:
- `references/review-checklist.md`: the judgement checklist; walk every item
- `references/coding-style.md`: the rule source and its rationale
- `references/spec-map.md`: subject → spec source

## Phase 0: fetch

```bash
S=~/.copilot/skills/fwts-review/scripts
$S/fetch.sh '<PR number | PR URL | fwts-devel URL | A..B>'
```

Parse `ID KIND BASE HEAD WORK WT` from the output. If it exits 3:
- for an ml patch that doesn't apply: retry with `--base $(git -C ~/work/fwts rev-list -1 --before=<patch date> origin/master)`
- otherwise: report the error and stop, after running cleanup

For a PR, read `$WORK/pr.json` (title, body, author, commits, files, linked issues).

## Phase 3+4 first: start build/test in the background

It takes minutes, so start it now and do phases 1–2 while it runs:

```bash
$S/build_test.sh "$WORK" "$BASE" "$HEAD" > "$WORK/logs/build_test.out" 2>&1
```

Use bash `mode: "async"`. Read the output when you're notified that it has finished.

## Phase 1: style

```bash
$S/style_check.py --repo "$WT" --json "$WORK/logs/style.json" "$BASE" "$HEAD"
```

Triage every finding against the code. Drop false positives, for example:
- `printf` in `src/utilities/`
- `nonstd-int` where ACPICA types are required (`ACPI_STATUS`, `UINT32` passed to ACPICA APIs)
- `pct-l` on a genuine `long`
- `call-space` on a macro or cast

Group the rest:
- **Should fix**: `acpica-modified` (unless it's an ACPICA import), `no-signoff`, `signoff-author`, `label-dup`, `printf-in-test`, `exit-in-test`, `unsafe-string`, `c99-for-decl`
- **Nit**: everything else

Also read the diff for style the script can't see:
- braces on single-statement bodies
- `bool` compared with `== true`
- `const` on read-only args
- spec section cited in comments
- library functions prefixed `fwts_` and documented with a header comment
- test layout as in `src/example/blank/blank.c`
- `FWTS_REGISTER` flags

If the PR references an issue, the commit should carry `BugLink:` or `Fixes:`.

## Phase 2: spec content

1. `$S/spec_lookup.sh update` (a warning is OK).
2. Identify the subjects in the diff:
   - table signatures and `src/acpi/<sig>/`
   - `_XXX` methods
   - SMBIOS types, UEFI variables, TPM structures
   - spec URLs in comments or the commit message
3. Resolve each subject through `references/spec-map.md`:
   - ACPI: `$S/spec_lookup.sh acpi '<regex>'`, then `view` the `.rst` file around the reported line to read the full table
   - others: `$S/spec_lookup.sh pdf <SUBDIR> '<regex>' '<name glob>'` (use `list <SUBDIR>` to choose the newest version)
   - layout cross-check: `$S/spec_lookup.sh actbl <SIG>`
4. Verify:
   - offsets and widths in fwts structs (`src/lib/include/fwts_acpi.h`) against the spec and ACPICA
   - length and revision checks
   - reserved-must-be-zero fields
   - allowed values and enums
   - flag bit positions
   - version gating (which revision added a field)
   - must vs should, and so the severity: CRITICAL/HIGH only for "must" violations
   - section numbers cited
5. If you can't find a source, try the URL cited in the source or the commit message with `web_fetch` (uefi.org returns 403, so use the local copies). Otherwise mark the claim **unverified** and ask the user for the document with `ask_user`.

Every claim gets a row in the report: `claim | source (file + heading/line or pdf + page) | ✅ / ❌ / unverified`.

## Judgement

Walk every item in `references/review-checklist.md`. Mark each ✅, ❌ or N/A, with `file:line` for each ❌. Pay particular attention to:
- format specifiers against types
- bounds and length checks before every read
- the logged field being the field checked
- unchecked returns
- leaks on error paths
- false PASS from error paths
- `FWTS_ERROR` (could not run) vs `fwts_failed()` (firmware bug)
- pass/fail decided on emulated-region values (PCC/FFH/EC handlers in libfwtsacpica): the result must not depend on fake values
- generic-test behaviour changes affecting other platforms
- `FWTS_FLAG_ROOT_PRIV`

Build/test results (from `build_test.out` and `logs/matrix.tsv`):
- any gcc FAIL or `make check` FAIL → **Blocking**
- cppcheck-new warnings → triage
- fixture diffs → explain, and require the expected `.log` files to be updated in the series
- every `regression.txt` line → **Should fix**, unless it is clearly not applicable (for example, a doc-only change)

Verdict:
- **Request changes**: any Blocking finding, or a Should-fix finding that affects correctness
- **Approve with nits**: only nits
- **Approve**: clean

## Outputs: `~/work/fwts-reviews/<ID>/`

```bash
mkdir -p ~/work/fwts-reviews/$ID && cp -r "$WORK/logs" ~/work/fwts-reviews/$ID/
```

`report.md`:

```
# fwts review: <ID> — <title/subject>
Input: <url or range> | Base: <sha8> | Head: <sha8> | Author: <name> | Date: <today>
## Verdict: <Approve | Approve with nits | Request changes>
## Summary            (2-4 sentences)
## Blocking           (- path:line — issue — why)
## Should fix
## Nits
## Spec verification  (| claim | source | result |)
## Build/test matrix  (from logs/matrix.tsv; note SKIPs)
## Checklist          (every item from review-checklist.md: ✅/❌/N/A)
```

`reply.md`:
- **GitHub** (KIND=pr): a review body (verdict and summary, then numbered points), then `### Inline comments` with lines of the form `path:line — comment`, ready to paste.
- **Mailing list** (KIND=ml or a local range under ml review): plain text, no markdown. Quote the relevant diff lines with `> ` and put each comment below its quote. End with `Acked-by: Ivan Hu <ivan.hu@canonical.com>` **only** for Approve or Approve with nits.

Tone: concise, specific, cite `file:line` and the spec section, and suggest the fix.

## Cleanup (always)

```bash
$S/fetch.sh --cleanup "$ID"
```

Tell the user the verdict, the counts (blocking, should-fix, nits) and the paths to `report.md` and `reply.md`.
````

- [ ] **Step 2: check the frontmatter parses and the referenced paths exist**

```bash
cd ~/.copilot/skills/fwts-review
head -4 SKILL.md | grep -q '^name: fwts-review$' && echo name-ok
for f in references/review-checklist.md references/coding-style.md references/spec-map.md \
         scripts/fetch.sh scripts/style_check.py scripts/spec_lookup.sh scripts/build_test.sh; do
	[ -e "$f" ] || echo "MISSING $f"; done
```

Expected: `name-ok` and no `MISSING` lines.

- [ ] **Step 3: commit**

```bash
git add SKILL.md && git commit -q -m "fwts-review: add SKILL.md

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 7: end-to-end validation

Run the full skill as a user would, in a fresh session or by following SKILL.md exactly.

- [ ] **Step 1: run the full unit suite**

Run: `cd ~/.copilot/skills/fwts-review && python3 -m pytest -q tests`
Expected: all pass (the real-PDF test may be skipped).

- [ ] **Step 2: dry-run on PR #54** with `review https://github.com/fwts/fwts/pull/54`.
  - Expected verdict: **Request changes**.
  - The report must mention:
    - the `fwts_evaluate_found_method()` behaviour change
    - the lock-imbalance branch that can never trigger
    - the test-only public API
    - the missing skip guard in `test-0002`
  - Any of these that is missing is a SKILL.md gap: fix the instructions, not the report.

- [ ] **Step 3: dry-run on PR #52.**
  - Expected: **Approve** once a regression test is added. The `regression.txt` file should contain `NO-FWTS-TEST-CHANGE` (unless the PR has since added a test), and the report should include the duplicated hash-size table nit.

- [ ] **Step 4: dry-run on a mailing-list patch:** `https://lists.ubuntu.com/archives/fwts-devel/2025-August/014058.html`.
  - Expected: the mbox applies (possibly with `--base` at the patch date), and the reply is plain text with `> ` quotes and an `Acked-by` only if approved.

- [ ] **Step 5: confirm cleanup**

Run: `git -C ~/work/fwts worktree list; git -C ~/work/fwts for-each-ref refs/fwts-review; ls -d /tmp/fwts-review-* 2>/dev/null`
Expected: the main tree only, no refs and no directories.

- [ ] **Step 6: commit any SKILL.md or script fixes from the dry runs**

```bash
git add -A && git commit -q -m "fwts-review: fixes from end-to-end dry runs

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

## Spec coverage (self-review)

| Spec section | Task |
|---|---|
| 3 Layout | 1, 6 |
| 4 Fetch (PR, PR commit, pipermail series, local range; worktree; ID; cleanup) | 4 |
| 5 Style (added lines only; all rule groups; commit metadata; JSON output; model triage) | 2, 6 |
| 6 Spec (ACPI_spec pull and RST search; PDF library with cache and page numbers; actbl cross-check; URL fallback; unverified + ask; evidence table) | 1, 3, 6 |
| 7 Build/test (three worktrees; per-commit build; make check; clang/cppcheck with SKIP; fixture base vs head; regression presence) | 5 |
| 8 Judgement | 6 |
| 9 Outputs (report, reply GitHub/ml, logs, never post) | 6 |
| 10 Error handling (fetch/am failure exit 3; build failure → Blocking and continue; SKIPs; pull warning; cleanup always) | 4, 5, 6 |
| 11 Validation | 2–5 (unit tests and smokes), 7 |
