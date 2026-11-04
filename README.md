# fwts-review

A GitHub Copilot CLI skill that reviews [fwts](https://github.com/fwts/fwts) (Firmware Test Suite) changes:

- GitHub PRs (`52`, a PR URL, or a PR commit URL)
- fwts-devel mailing-list patches (lists.ubuntu.com archive URL)
- local commit ranges (`A..B`)

It runs four phases and writes `~/work/fwts-reviews/<ID>/report.md` and `reply.md`. It never posts to GitHub and never sends mail.

1. **Style**: `scripts/style_check.py` checks fwts coding-style rules on the added lines and on the commit message.
2. **Spec content**: `scripts/spec_lookup.sh` looks up the ACPI, UEFI, SMBIOS, TCG and Arm specs. It reads only a local document library and never goes online. If a spec is missing or outdated, it prints `UPDATE-SPEC:` and the review asks you to add the document.
3. **Build**: gcc on every commit, plus clang and cppcheck when they are installed.
4. **Test**: `make check`, the fixtures under `fwts-test/`, and regression checks.

## Install

```bash
git clone https://github.com/Ivanhu5866/fwts-review ~/.copilot/skills/fwts-review
```

Then ask Copilot CLI something like `review https://github.com/fwts/fwts/pull/52`.

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
