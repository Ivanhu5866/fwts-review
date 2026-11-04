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
