# fwts-review

A GitHub Copilot CLI skill that reviews [fwts](https://github.com/fwts/fwts) (Firmware Test Suite) changes:

- GitHub PRs (`52`, a PR URL, or a PR commit URL)
- fwts-devel mailing-list patches (lists.ubuntu.com archive URL)
- local commit ranges (`A..B`)

It runs four phases and writes `~/work/fwts-reviews/<ID>/report.md` and `reply.md`. It never posts to GitHub and never sends mail.

1. **Style**: `scripts/style_check.py` checks fwts coding-style rules on the added lines and on the commit message.
2. **Spec content**: `scripts/spec_lookup.sh` looks up the ACPI, UEFI, SMBIOS, TCG and Arm specs. It reads only a local document library and never goes online. If a spec is missing or outdated, it prints `UPDATE-SPEC:` and the review asks you to add the document.
3. **Build**: review every patch, then build only the final tree with all patches applied, using gcc plus clang and cppcheck when installed. Intermediate commits are not built.
4. **Test**: `make check`, the fixtures under `fwts-test/`, and regression checks.

## Install

```bash
git clone https://github.com/Ivanhu5866/fwts-review ~/.copilot/skills/fwts-review
```

## Usage

Ask Copilot CLI, for example:

| Request | Reviews |
|---|---|
| `review PR 52` or `review https://github.com/fwts/fwts/pull/52` | the whole PR |
| `review https://github.com/fwts/fwts/pull/48/changes/8b93f97bf0cb53ae0ba2e97acb481f2bdd3ce70c` | one commit of a PR, against its parent (`/commits/<sha>` and short SHAs also work) |
| `review https://lists.ubuntu.com/archives/fwts-devel/2025-August/014058.html` | a mailing-list patch |
| `review HEAD~3..HEAD` | a local commit range in `~/work/fwts` |

## Requirements

- An fwts checkout at `~/work/fwts`. It is only read; all work happens in `/tmp/fwts-review-<ID>/` git worktrees.
- `git`, `gh` (logged in), `python3`, `pdftotext` (poppler-utils), and fwts build dependencies.
- Spec library: `~/CloudStation/Document/<ACPI|UEFI|SMBIOS|TPM|ARM|...>/`. Override with `SPEC_DOC_DIR`. See `references/spec-map.md` for the expected layout.

Optional overrides:

- `fetch.sh --repo PATH`: fwts checkout, instead of `~/work/fwts`
- `FWTS_REPO`: fwts checkout used by `spec_lookup.sh actbl`
- `FWTS_REVIEW_ROOT`: work directory, instead of `/tmp`
- `SPEC_CACHE_DIR`: cache for converted spec text

## Layout

| Path | Contents |
|---|---|
| `SKILL.md` | Skill entry point and workflow |
| `references/` | Review checklist, coding-style rules, spec map |
| `scripts/` | `fetch.sh`, `build_test.sh`, `style_check.py`, `spec_lookup.sh`, `mbox_extract.py` |
| `tests/` | pytest suite (`python3 -m pytest -q tests`) |
| `docs/` | Design and implementation plan |
