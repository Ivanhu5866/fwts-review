---
name: fwts-review
description: Review fwts (Firmware Test Suite) changes: GitHub PRs on github.com/fwts/fwts, fwts-devel mailing-list patches on lists.ubuntu.com/archives/fwts-devel, or a local fwts commit range. Checks coding style, verifies the content against the ACPI/UEFI/SMBIOS/Arm/TCG specs, builds every commit, runs make check and fixture tests, then writes a review report and a draft reply. Activate whenever the user asks to review, check or ack an fwts PR, patch or commit, or pastes a github.com/fwts/fwts/pull URL or an fwts-devel archive URL, even without the word "skill".
---

# fwts-review

Review an fwts change in four phases (style → spec → build → test). The output is `~/work/fwts-reviews/<ID>/report.md` plus `reply.md`.

Rules:
- **Never** post to GitHub or send mail.
- **Never** touch the `~/work/fwts` working tree (no checkout, reset, am, commit there). The scripts only add worktrees and `refs/fwts-review/*` refs; all work happens in `/tmp/fwts-review-<ID>/` (`$WORK`; root overridable with `FWTS_REVIEW_ROOT`). Read-only `git -C ~/work/fwts grep/show/log` is fine.
- **Always** run the cleanup step, even after an error, but only after `build_test.sh` has finished.
- Shell state doesn't persist between bash calls: start each command with `S=~/.copilot/skills/fwts-review/scripts; . /tmp/fwts-review-<ID>/fetch.env` (sets `ID KIND BASE HEAD WORK WT`).

References (in `~/.copilot/skills/fwts-review/references/`):
- `review-checklist.md`: the judgement checklist; walk every item
- `coding-style.md`: the style rules and their rationale
- `spec-map.md`: subject → spec source and the exact lookup command

Specs: use **only** the local library `~/CloudStation/Document/`. Never search or fetch specs online (no `web_fetch`/`curl`).

## Phase 0: fetch

```bash
S=~/.copilot/skills/fwts-review/scripts
$S/fetch.sh '<PR number | PR URL | PR commit URL | fwts-devel URL | A..B>'
```

It prints `ID= KIND= BASE= HEAD= WORK= WT=` (also saved to `$WORK/fetch.env`). IDs: `pr54`, `pr54-<sha8>` (PR commit URL `…/pull/N/changes/<sha>` or `…/pull/N/commits/<sha>`: reviews only that commit, `BASE=HEAD^`), `ml-<hash>`, `local-<base8>-<head8>`. KIND is `pr`, `ml` or `local`. The default base is upstream master, fetched into `refs/fwts-review/origin-master`.

Exit codes: 0 ok, 2 usage (bad input; tell the user the accepted forms), 3 fetch/apply failure. On 3:
- ml patch didn't apply (`git am failed`): retry on the tree as of the patch date:
  ```bash
  D=$(sed -n 's/^Date: //p' /tmp/fwts-review-<ID>/series.mbox | head -1)
  $S/fetch.sh --base "$(git -C ~/work/fwts rev-list -1 --before="$D" refs/fwts-review/origin-master)" '<url>'
  ```
  Note the older base in the report.
- ml "has no diff (a reply?)" / "not a [PATCH] message": the URL is a reply. Ask the user for the `[PATCH]` message URL and stop.
- anything else: report the error and stop, after running the `--cleanup` command fetch printed (if any).

For KIND=pr, read `$WORK/pr.json` (number, title, body, author, baseRefName, headRefName, commits, files, url). Note issues referenced in the body (`#N`, `Fixes #N`).

## Start build/test in the background

It takes ~2–3 minutes, so start it now and do phases 1–2 while it runs. Use bash `mode: "async"`:

```bash
S=~/.copilot/skills/fwts-review/scripts; . /tmp/fwts-review-<ID>/fetch.env
$S/build_test.sh "$WORK" "$BASE" "$HEAD" > "$WORK/logs/build_test.out" 2>&1
```

Read `$WORK/logs/build_test.out` when notified it finished. Exit 2 = usage or "no commits in range" (wrong input; stop), 3 = no merge base.

## Phase 1: style

```bash
$S/style_check.py --repo "$WT" --json "$WORK/logs/style.json" "$BASE" "$HEAD" > "$WORK/logs/style.txt"
awk '{print $3}' "$WORK/logs/style.txt" | sort | uniq -c
```

Lines are `<sha8> <path>:<line> <rule> <message>` (`COMMIT_MSG:<n>` for commit-message rules). It checks only added lines, per non-merge commit. Exit 2 = git error or empty range.

ACPICA imports (subject `ACPICA: Update to version …`, wholesale `src/acpica/` changes) produce one `acpica-modified` finding per file: collapse them into a single "ACPICA import" note and don't count them. `acpica-modified` is Should-fix only in non-import commits.

Triage every finding against the code. Drop false positives, for example:
- `printf-in-test` / `exit-in-test` in non-test code such as `src/main.c`
- `nonstd-int` where ACPICA APIs require `UINT32`/`BOOLEAN` etc.
- `pct-l` on a genuine `long`
- `call-space` / `func-brace-same-line` / `empty-params` on macros or casts
- `decl-blank` on a misread declaration

Group the rest (real rule IDs only):
- **Should fix**: `acpica-modified` (non-import), `no-signoff`, `signoff-author`, `label-dup`, `printf-in-test`, `exit-in-test`, `unsafe-string`, `c99-for-decl`
- **Nit**: everything else (`trailing-ws`, `cr`, `ws-after-backslash`, `control-char`, `non-ascii`, `bom`, `no-final-newline`, `blank-line-eof`, `indented-preproc`, `space-indent`, `space-before-tab`, `pri-space`, `space-before-nl`, `log-newline`, `pct-l`, `label-camel`, `header-guard`, `comment-space`, `comment-open-text`, `cpp-comment`, `kw-space`, `brace-space`, `sizeof-space`, `paren-space`, `comma-space`, `incdec-space`, `return-paren`, `star-with-type`, `bare-unsigned`, `unused-attr`, `void-cast-unused`, `empty-params`, `func-brace-same-line`, `nonstd-int`, `call-space`, `else-newline`, `decl-blank`, `subject-format`, `subject-length`, `empty-body`, `msg-trailing-ws`)

Also read the diff (`git -C "$WT" log -p --reverse "$BASE..$HEAD"`) for style the script can't see:
- braces on single-statement bodies
- `bool` compared with `== true`
- `const` on read-only args
- spec section cited in comments
- library functions prefixed `fwts_` and documented with a header comment
- test layout as in `src/example/blank/blank.c`
- `FWTS_REGISTER` flags

If the PR or patch references an issue, the commit should carry `BugLink:` or `Fixes:`.

## Phase 2: spec content

1. Identify the subjects in the diff:
   - table signatures and `src/acpi/<sig>/`
   - `_XXX` methods
   - SMBIOS types, UEFI variables, TPM structures
   - spec URLs in comments or the commit message
2. Resolve each subject through `references/spec-map.md` (it gives the subdir and name glob per subject):
   - `$S/spec_lookup.sh pdf <SUBDIR> '<regex>' '<name glob>'`. **Always** pass the glob from spec-map (e.g. `'*IORT*'`); without one every document in the subdir gets converted. Use `list <SUBDIR>` (newest first) to choose a version. ACPI: `pdf ACPI '<regex>' '*ACPI_Spec_6.6*'` (the newest `ACPI_Spec_*`). Hits are `file p.N: text` (N = physical PDF page; read it with `pdftotext -layout -f N -l N '<file>' -`) or `file l.N: text` for `.docx`/`.odt`.
   - layout cross-check: `$S/spec_lookup.sh actbl <SIG|NAME>` (`APIC` or `MADT`, `FACP` or `FADT`, `TCPA`); exit 1 = no ACPICA struct.
   - Regex: POSIX ERE, case-insensitive (input is lowercased; write the regex in lowercase, `[a-z]` not `[A-Z]`). `\S`, `\w`, bracket classes work. Output is capped at 40 lines (`MAX=` env to change); narrow the regex rather than raising it.
3. Verify:
   - offsets and widths in fwts structs (`src/lib/include/fwts_acpi.h`) against the spec and ACPICA
   - length and revision checks
   - reserved-must-be-zero fields
   - allowed values and enums
   - flag bit positions
   - version gating (which revision added a field)
   - must vs should, and so the severity: CRITICAL/HIGH only for "must" violations
   - section numbers cited
4. Missing or outdated spec. This applies when:
   - `spec_lookup.sh` prints `UPDATE-SPEC:` (no directory, no document or no match), or
   - spec-map says **not in library**, or
   - the diff or commit cites a newer revision than the newest local copy (for example "ACPI 6.7" or "PFP 1.07").

   Do **not** go online. Mark the claim **unverified**. Use `ask_user` to tell the user which document and revision is needed and where to put it: `~/CloudStation/Document/<SUBDIR>/`. Rerun the lookup once they confirm. If they skip, keep the claim unverified and list it under "Specs to update" in the report.

Every claim gets a row in the report: `claim | source (file + heading/line, or pdf + page) | ✅ / ❌ / unverified`.

## Build/test results

`build_test.out` lines:
- `MERGE_BASE=<sha>`: BASE isn't an ancestor of HEAD; diffs, cppcheck and fixtures used the merge base.
- `gcc <sha8>: PASS | FAIL: <first error>`: one per commit (bisectability); log `logs/build-<sha8>.log`.
- `make check: PASS (TOTAL: …) | FAIL (…) <failing tests> | SKIP (head build failed)`: at HEAD; `logs/make-check.log`.
- `clang: …` and `cppcheck: N new | N/A (no .c changes)`: `SKIP (… not installed)` is **not** a failure; list the SKIPs in the report. New cppcheck warnings (changed non-ACPICA `.c` files, base vs head) are in `logs/cppcheck-new.txt`.
- `fixtures: N run, N changed vs base, N differ from expected`, then only the rows worth reading: `fwts-test/<t>/test-N.sh [not in TESTS] (<dump>): base[<summary>] head[<summary>] diff=<base-vs-head lines> exp=<head-vs-expected-.log lines | n/a>`, `no-summary`, or `dump file missing`; then a count line (tests without fixture coverage, klog-style ones covered by make check, unchanged). All rows: `logs/fixtures.txt`; outputs: `logs/fx-{base,head}-<tag>.log`.
- `regression checks:` then `none` or lines from `logs/regression.txt`: `NOT-IN-TESTS`, `OPTION-NO-MANPAGE`, `OPTION-NO-ARG-HELP`, `NO-FWTS-TEST-CHANGE (advisory)`.
- `matrix: …/logs/matrix.tsv` (commit, subject, gcc, clang, make_check, cppcheck_new, fixtures; a merge HEAD gets a `merge-head:` row).

Interpret:
- any gcc FAIL or `make check` FAIL → **Blocking**
- cppcheck new warnings → triage each against the code
- `diff>0` → explain the output change; require the expected `.log` files to be updated in the series
- `exp>0` on a fixture in TESTS → the series must update its expected `.log`
- `exp>0` on a `[not in TESTS]` fixture with `diff=0` → pre-existing upstream issue, not the patch's fault (mention at most as info)
- `no-summary` → the test produced no result line on that dump: investigate
- `NOT-IN-TESTS`, `OPTION-NO-*` → **Should fix** (check the option heuristic really hit a new fwts option)
- `NO-FWTS-TEST-CHANGE (advisory)` → judgement: Should fix for fixes and new parsing code where a fixture is feasible; N/A for license/comment-only changes, refactors with no output change, or hardware-only paths

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
## Spec verification  (| claim | source | result |; first line: the local spec files/versions used)
## Specs to update   (missing/outdated documents for ~/CloudStation/Document/, or "none")
## Build/test matrix  (from logs/matrix.tsv; note SKIPs)
## Checklist          (every item from review-checklist.md: ✅/❌/N/A)
```

`reply.md`:
- **GitHub** (KIND=pr): a review body (verdict and summary, then numbered points), then `### Inline comments` with lines of the form `path:line — comment`, ready to paste.
- **Mailing list** (KIND=ml, and KIND=local unless the user says it's for a PR): plain text, no markdown. Quote the relevant diff lines with `> ` and put each comment below its quote. End with `Acked-by: Ivan Hu <ivan.hu@canonical.com>` **only** for Approve or Approve with nits.

Tone: concise, specific, cite `file:line` and the spec section, and suggest the fix.

## Cleanup (always, after build_test.sh has finished)

```bash
~/.copilot/skills/fwts-review/scripts/fetch.sh --cleanup <ID>
```

Expect `CLEANED=<ID>`. Tell the user the verdict, the counts (blocking, should-fix, nits) and the paths to `report.md` and `reply.md`. If "Specs to update" is not empty, end with: `Please update these specs in ~/CloudStation/Document/: …`.
