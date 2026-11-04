# fwts-review skill: design

Date: 2026-11-04
Owner: Ivan Hu (@Ivanhu5866)
Status: design approved; implementation not started

## 1. Purpose

A Copilot CLI skill that reviews fwts changes (GitHub PRs and fwts-devel mailing-list patches) in four phases:
1. coding style
2. content against the specs
3. build
4. test

It produces a review report and a draft reply. Nothing is ever posted automatically.

The source of truth for the checks is `/home/ivanhu/work/fwts/fwts-review-checklist.md` together with `/home/ivanhu/work/fwts/fwts-coding-style.md`.

## 2. Non-goals

- Posting reviews to GitHub or sending mail
- Running fwts live on hardware as root (this box has no sudo) or on remote SSH targets
- ASan or fuzz runs (can be added later)
- Fixing the patch under review

## 3. Layout

```
~/.copilot/skills/fwts-review/
  SKILL.md                    trigger description, phase workflow, judgement rules
  docs/2026-11-04-fwts-review-design.md   (this file)
  references/
    review-checklist.md       copy of fwts-review-checklist.md
    coding-style.md           copy of fwts-coding-style.md
    spec-map.md               subject -> spec source mapping (section 6)
  scripts/
    fetch.sh                  input -> branch in an isolated worktree
    style-check.py            mechanical style checks on added lines only
    build-test.sh             per-commit builds, make check, clang, cppcheck, fixture runs
    spec-lookup.sh            spec text search (ACPI_spec RST, PDF text cache)
```

Trigger: "review" combined with a fwts PR or patch link, a github.com/fwts/fwts URL, a lists.ubuntu.com fwts-devel URL, or a local fwts commit range.

## 4. Inputs and fetch (`fetch.sh`)

| Input | Handling |
|-------|----------|
| GitHub PR URL or number, including `/pull/N/changes/<sha>` | `gh pr view N --json title,body,author,baseRefName,commits,files`; `git fetch origin pull/N/head:review-N`. If a specific commit is given, the head is that sha. |
| fwts-devel pipermail URL (`lists.ubuntu.com/archives/fwts-devel/YYYY-Month/NNNNNN.html`) | Read the Subject and Message-ID from the HTML. Download `YYYY-Month.txt.gz`, extract the matching messages (the whole `[PATCH n/m]` series) into an mbox, then `git am` it. Raw text keeps the tabs, so style checks stay accurate; never apply a patch scraped from the HTML page. |
| Local range `base..head` in `/home/ivanhu/work/fwts` | Use as is. |

- Workspace: `git worktree add /tmp/fwts-review-<id>/wt <base>`, where the base defaults to `origin/master` after a fetch. The user's working tree is never modified.
- `<id>` is `pr<N>`, `ml-<msgid-short>` or `local-<shortsha>`.
- Output prints `BASE=<sha> HEAD=<sha> WT=<path> ID=<id>` so later steps can parse it.
- If fetching fails or `git am` doesn't apply cleanly, the review stops and reports the error.
- All worktrees (`wt`, `wt-base`, `wt-clang`; see section 7) are removed at the end, even after an error, unless `--keep` is given.

## 5. Phase 1: style (`style-check.py <base> <head>`)

- Parses `git diff -U0 <base>..<head>` and checks **only added lines** in non-ACPICA `.c`, `.h`, `Makefile.am` and `fwts-test/**` files. Lines under `src/acpica/` are reported as the "ACPICA modified" rule instead.
- Runs `git show --check <c>` for every commit.
- Rules are the mechanically checkable items from `coding-style.md`:
  - **Whitespace and trailing bytes**: space indentation, trailing whitespace, a space before a tab, whitespace after `\`, blank lines or a missing newline at the end of a file, CR characters, BOMs, control characters, non-ASCII characters.
  - **Braces and spacing**: a function `{` on the same line; `){`; `}` and `else` on separate lines; a keyword without a space before `(`; `foo (`; `sizeof (`; `( x )`; `,x`; `x ++`; `return (x)`.
  - **Types**: `char* p`; `u32`/`UINT32`; a bare `unsigned`; C99 `for (int`; `()` instead of `(void)`; `(void)x` or `__attribute__((unused))` instead of `FWTS_UNUSED`.
  - **Comments and preprocessor**: `//`; text on the `/*` line of a multi-line comment; no space after `/*` or before `*/`; indented `#if`; a header guard other than `__FWTS_X_H__`.
  - **Logging**: `printf(` or `exit(` in `src/` test code; `"\n"` at the end of an `fwts_log_*`/`fwts_failed`/`fwts_passed`/etc. string; `"PRIx`/`PRIx"` without spaces; `%l[dux]`; a `fwts_failed` label that isn't CamelCase; a new label already used elsewhere in the tree; `sprintf`/`strcpy`/`strcat`.
  - **Missing blank line** between declarations and the first statement in a new function.
- **Commit metadata**:
  - subject matches `^[a-z0-9_/ -]+: .+` (`component: [sub: ]summary`) and is 75 characters or fewer
  - non-empty body
  - `Signed-off-by:` present and matching the author
  - no trailing whitespace
  - `BugLink:` or `Fixes:` present when the PR references an issue
- Output: `logs/style.json` plus a text listing `commit file:line rule message`. The model removes false positives (for example, a `printf` in `src/utilities`) before anything goes into the report.

## 6. Phase 2: spec content (model, using `spec-lookup.sh`)

Steps:
1. **Identify the subject** from the diff:
   - table signatures (`"IORT"`, `fwts_acpi_table_iort`, `src/acpi/<table>/`)
   - method names (`_BST`, `_PSS`, …)
   - SMBIOS types, UEFI variables and TPM structures
   - spec URLs in comments in the touched files
2. **Resolve** each subject through `references/spec-map.md`, in this order:
   1. ACPI tables, objects and methods defined in the ACPI spec: `git -C ~/work/ACPI_spec pull --ff-only` (failure is only a warning), then `spec-lookup.sh acpi <term>`, which greps `~/work/ACPI_spec/source/*.rst` and prints the matching file, the section heading and the surrounding table rows.
   2. Non-ACPI specs (Arm IORT/AEST/APMT/MPAM/SDEI/BSA/SBBR, Microsoft SPCR/DBG2/WSMT, TCG TPM2/TCPA, SMBIOS, UEFI, RISC-V, PCIe): `spec-lookup.sh pdf <subdir> <term>` searches `~/CloudStation/Document/<ARM|Microsoft|TPM|SMBIOS|UEFI|RISC-V|PCIE|ACPI>/`. It picks the newest version by filename, converts it once with `pdftotext -layout` into `~/.cache/fwts-review/specs/<sha1>.txt` (keyed by path and mtime), then greps the text and reports the page number from form feeds.
   3. The spec URL cited in the fwts source or in the commit message, via `web_fetch`.
   4. Otherwise, ask the user for the document. Until it's provided, findings are marked **unverified**.
3. **Cross-check** layouts against the ACPICA header struct for the table in `src/acpica/source/include/actbl*.h`: field order, widths and total size.
4. **What to verify**:
   - offsets and widths in fwts structs (`src/lib/include/fwts_acpi.h`)
   - length and revision checks
   - reserved fields required to be zero
   - enum and allowed values
   - flag bit positions
   - whether the spec says "must" or "should" (and so whether HIGH/CRITICAL severity is justified)
   - which spec revision introduced a field (version gating)
   - spec section numbers cited in the commit or comments
5. **Evidence**: each claim in the report has a row `claim | source (rst file + heading, or pdf + page) | ✅ / ❌ / unverified`.

`spec-map.md` holds a table `subject pattern -> source type -> location hint`, seeded from the spec URLs already cited in fwts and the CloudStation subfolders.

## 7. Phase 3 and 4: build and test (`build-test.sh <wt> <base> <head>`)

It runs in the background (async) while Phase 2 continues. Logs go to `/tmp/fwts-review-<id>/logs/`.

It uses three worktrees under `/tmp/fwts-review-<id>/`, so builds never clobber each other:
- `wt`: head, gcc
- `wt-base`: base, gcc; built only when fixture runs are needed
- `wt-clang`: head, clang

1. **Per-commit build** (bisectability): for each commit in `base..head`, check it out in the worktree and run `autoreconf -i && ./configure && make -j$(nproc)` with gcc and `-Werror` (the default). Record pass or fail and the first error.
2. **At HEAD**:
   - `make check`: record the pass, fail and skip counts and the names of failing tests
   - clang in `wt-clang`: `autoreconf -i && CC=clang ./configure && make -j`, skipped with a note if clang is missing
   - cppcheck: `cppcheck --enable=warning,style,portability --quiet` on the changed `.c` files at base and at head; report only warnings that are new (matched on file, message and normalised line), skipped with a note if cppcheck is missing
3. **Touched-test fixture runs**:
   - Map each changed `src/<area>/<test>/` to its fwts test name, using the `FWTS_REGISTER("<name>"` in the file.
   - For each `fwts-test/<name>-*/acpidump-*.log`, run the base (`wt-base`) and head (`wt`) binaries with `fwts --log-format="%line %owner " -w 80 --dumpfile=<log> <name> -`.
   - Diff the two outputs and summarise PASS/FAIL/WARN/ABORT changes per fixture.
   - Tests without fixtures are noted as "no fixture coverage".
4. **Regression-test presence**:
   - A fix, or a new or changed parser, without a new or updated `fwts-test/<name>-NNNN/` is a **Should fix** finding.
   - New test scripts must be in `TESTS` in the top-level `Makefile.am`.
   - If the fixture output changed, the expected `.log` files must be updated in the same series.
   - New command-line options must update `doc/fwts.1` and `fwts-test/arg-help-*/`.

Build failures do not stop the review. They are reported as **Blocking**.

## 8. Judgement (model, using `references/review-checklist.md`)

The model goes through every checklist item: commit, build, style, correctness, test results, framework, and tests and docs. It uses the script outputs and reads the diff, paying particular attention to:
- format specifiers against types
- bounds and length checks before reads
- the field logged being the field checked
- unchecked returns
- leaks on error paths
- false PASS from error paths
- severity choice
- pass/fail decided on emulated-region values
- generic-test behaviour changes
- `FWTS_ERROR` versus `fwts_failed()`
- root-privilege flags

## 9. Outputs (`~/work/fwts-reviews/<id>/`)

- `report.md`:
  - header: input, base and head, author, date
  - **verdict**: Approve, Approve with nits, or Request changes
  - Summary
  - Blocking, Should fix and Nits (each with `file:line` and the reason)
  - Spec verification table
  - Build/test matrix (rows are commits; columns are gcc, clang, `make check`, cppcheck-new, fixtures)
  - the full checklist with ✅ / ❌ / N/A per item
- `reply.md`:
  - **GitHub**: a review body, then a list of inline comments formatted as `path:line — comment`, ready to paste.
  - **Mailing list**: a plain-text reply that quotes the relevant diff lines with `> ` and puts comments underneath, ending with `Acked-by: Ivan Hu <ivan.hu@canonical.com>` only if the verdict is Approve or Approve with nits.
- `logs/`: the raw script outputs.
- Nothing is posted or mailed.

## 10. Error handling

| Situation | Behaviour |
|-----------|-----------|
| gh not authenticated, or pipermail fetch fails | stop, report the cause |
| `git am` conflict | stop, report the failing patch, suggest the base |
| `autoreconf`/`configure` fails | Blocking finding; skip the later build steps but continue with the style and spec phases |
| clang or cppcheck not installed | skip with a note in the matrix |
| ACPI_spec pull fails | warn and use the local copy |
| spec not found locally or online | mark unverified, ask the user |
| any exit | remove the worktree (`trap`), unless `--keep` |

## 11. Validation of the skill

- Unit-check `style-check.py` on a crafted diff that contains one violation per rule, plus a clean diff (expect zero findings).
- Dry-run the full skill on PR #54 and PR #52. Expected results:
  - #54: Request changes, including the `fwts_evaluate_found_method()` behaviour change, the never-triggered lock-imbalance branch, the test-only public API, and the missing skip guard in `test-0002`.
  - #52: Approve after a regression test is added under `fwts-test`, plus the duplicated hash-size table nit.
- Dry-run on one fwts-devel pipermail patch to exercise the mbox path.
