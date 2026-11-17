# fwts coding style: checkable rules

Sources:
- **[DOC]** README_SOURCE.txt
- **[BUILD]** src/Makefile.am and src/lib/src/Makefile.am flags
- **[DE FACTO]** measured over about 99k lines of fwts C code (ACPICA excluded), plus past "coding style" cleanup commits (00003a40, a5cbe72c, 849bea66, d1cc48c0, 1178dcb0, 9bc5a83d, 08c21ba1, f592eca4, 653ee1e3, b8f0b002, dbf17e66)

How to check:
- **auto**: grep or script
- **cc**: compiler
- **manual**: by eye

## 1. Compiler-enforced [BUILD] (cc)
- [ ] `-Wall -Werror -Wextra` (`--disable-werror` exists, but patches must build clean)
- [ ] `-Wshadow`: no variable shadowing
- [ ] `-Wmissing-declarations`: non-static functions need a prototype in a header, so make them `static`
- [ ] `-Wredundant-decls`, `-Wcast-qual` (don't cast away `const`), `-Wfloat-equal`
- [ ] Also build with clang; fwts has had several clang-only fixes
- [ ] Optional: `./cppcheck.sh` and `./smatchify.sh` should report no new warnings

## 2. Whitespace and indentation (auto)
- [ ] Indent with tabs only, 8 wide [DOC: kernel K&R] (947 space-indented lines, mostly psci.c and fwts_log_scan.c, which are legacy)
- [ ] No trailing spaces or tabs [DOC] (8 in the tree; d289e94f cleaned these up)
- [ ] No space before a tab in indentation
- [ ] No double blank lines; no blank line straight after `{` or straight before `}`
- [ ] One blank line between the declarations and the first statement (849bea66; 1079 vs 168)
- [ ] File ends with a newline
- [ ] Line length: no hard limit (about 8k lines over 80 columns), but wrap long code; never split user-visible strings

## 2a. Trailing bytes and file hygiene (auto)
Quick check: `git diff --check <base>..HEAD` (or `git show --check`) flags trailing whitespace, a space before a tab, and blank lines at the end of a file.
- [ ] No trailing spaces or tabs at the end of a line, in any file the patch touches: `.c`, `.h`, `Makefile.am`, `fwts-test/*.sh` (57 legacy `test-*.sh` files, mostly the license line). In `fwts-test/` only `*.sh` and Makefiles are checked; every other file there (expected `.log`, iasl `*.original`, `klog.txt`, `.dat`, ...) is a fixture that mirrors tool output and is exempt (308 legacy `.log` files carry trailing blanks)
- [ ] No whitespace after a line-continuation `\` (macros, Makefile.am)
- [ ] No blank lines at the end of a file (3 legacy files: clog.c, fwts_json.c, fwts_pipeio.c)
- [ ] File ends with exactly one `\n`
- [ ] LF line endings only, no CR/CRLF (none in the tree today)
- [ ] No UTF-8 BOM and no control characters other than tab and newline
- [ ] ASCII only in code and comments (`*.c`, `*.h`) and build files (`Makefile.am`, `configure.ac`, `*.sh`); don't paste smart quotes, `®` or `–` from the spec PDF (9 legacy lines). Docs and packaging (`doc/fwts.1`, `debian/changelog`) may carry non-ASCII contributor names
- [ ] No space before `\n` in strings, and no trailing space at the end of a log message
- [ ] No trailing whitespace in the commit message

## 3. Braces (auto)
- [ ] Function opening `{` on its own line (2147 vs 3)
- [ ] Control-statement `{` on the same line: `if (x) {` (22 exceptions)
- [ ] Cuddled else: `} else {` and `} else if (...) {` (580 vs 21 with `}` and `else` on separate lines)
- [ ] Single-statement bodies have no braces; if one branch of an if/else has braces, both get them
- [ ] Space before `{`: `){` is wrong

## 4. Spacing (auto)
- [ ] `if (`, `for (`, `while (`, `switch (`: keyword, then a space (6715 vs 29)
- [ ] No space between a function name and `(`: `foo(x)`, not `foo (x)`
- [ ] `sizeof(x)`: parentheses, no space (1521 vs about 14)
- [ ] No spaces inside parentheses: `( x )` is wrong
- [ ] A space after every comma (`,x` is wrong)
- [ ] Spaces around binary operators: `a + b`, `mem + i` (653ee1e3)
- [ ] No space before `++` or `--`: `failures++` (f592eca4)
- [ ] `return x;`, not `return (x);`
- [ ] `case` at the same indent as `switch` (185 vs 48)

## 5. Pointers and types [DOC and DE FACTO] (auto or manual)
- [ ] The `*` goes next to the name: `char *p`, not `char* p` (5010 vs 23; 1178dcb0)
- [ ] All structs `typedef`'d [DOC]
- [ ] No `typedef` of `void *` [DOC]
- [ ] Use `uint8_t`, `uint16_t`, `uint32_t` and `uint64_t`, not `u32`, `UINT32` or a bare `unsigned` [DOC]
- [ ] `bool` with `true` and `false`; don't compare with `== true` or `== false`
- [ ] `size_t` for lengths (29279c70)
- [ ] `const` on read-only pointer arguments and read-only scalar arguments (the 2021 constify series)
- [ ] `static const` for lookup tables that are never modified
- [ ] Declare variables at the top of a block. Exception: a C99 loop declaration such as `for (uint32_t i = 0; ...)` is accepted (used in aspt, mpam, ras2, skvl, uniqueid, viot and tpmevlog); don't flag it
- [ ] Give variables the smallest scope (3bf81fd1, 6bcbca54, bf8602dc)
- [ ] No unused variables, redundant initialisation or redundant null checks (ae2f7e3a, 71f5091f, dc77b438)

## 6. Expressions (manual)
- [ ] No assignment inside a condition with a double assignment: `if ((a = b = calloc(..)) == NULL)` (d1cc48c0)
- [ ] Parenthesise sub-expressions in `&&`/`||` chains: `if ((p == NULL) || (*p == '\0'))` (08c21ba1)
- [ ] Null checks may use `!p` or `p == NULL`, but be consistent within a function
- [ ] Cast constants that are shifted: `1UL << n` (70d34cdb)
- [ ] "NO clever macros", "No smart tricks" [DOC]

## 7. Comments [DOC: "Comments are not optional!"] (auto or manual)
- [ ] `/* */` only; no `//` (47 legacy instances)
- [ ] Multi-line comment: `/*` on its own line, ` * text` lines, ` */` on its own line (a5cbe72c; 1464 vs 21)
- [ ] A space after `/*` and before `*/`
- [ ] Library functions start with a header comment:
  ```
  /*
   *  fwts_foo()
   *	what it does
   */
  ```
- [ ] Cite the spec section for spec checks

## 8. Preprocessor and headers (auto)
- [ ] `#if`, `#ifdef` and `#endif` in column 0, never indented (a5cbe72c)
- [ ] `#define` values aligned with tabs (00003a40, dbf17e66)
- [ ] Header guard: `#ifndef __FWTS_NAME_H__` (69 vs 2)
- [ ] New library APIs: a header in `src/lib/include`, included from `fwts.h` [DOC]
- [ ] Packed structs: `__attribute__ ((packed))` (both spellings are used; follow the file)
- [ ] Unused parameters: `FWTS_UNUSED(x)` (285 uses), not `(void)x` or `__attribute__((unused))`
- [ ] A function with no parameters is declared `(void)`, not `()`

## 9. Naming and linkage [DOC] (auto or manual)
- [ ] Every library function starts with `fwts_`
- [ ] Every test function and variable is `static`; nothing is exported from a test
- [ ] Test names have no spaces (they are stringified)
- [ ] Shared code goes in the library, not copied between tests

## 10. Return and error conventions [DOC] (manual)
- [ ] `FWTS_OK` means success, `FWTS_ERROR` means a generic failure, negative values are errors, and `NULL` is an error
- [ ] A minor test returns `FWTS_ERROR` only when it could not run; otherwise it reports a failure with `fwts_failed()`
- [ ] Always check the return values of system calls and library calls

## 11. Test-file layout (manual; see src/example/blank/blank.c)
- [ ] GPL-2.0-or-later copyright header with `Copyright (C) <year>-<year> <owner>`
- [ ] `#include "fwts.h"`
- [ ] Order: `init`, `deinit`, minor tests, a `fwts_framework_minor_test x_tests[]` table ending in `{ NULL, NULL }`, `fwts_framework_ops x_ops`, then `FWTS_REGISTER(...)` as the last statement
- [ ] `.init` and `.deinit` return only `FWTS_OK` or `FWTS_ERROR`
- [ ] `FWTS_REGISTER` flags fit the test (`FWTS_FLAG_ROOT_PRIV`, `_ACPI`, `_SBBR`, ...)

## 12. Logging (auto or manual)
- [ ] No `printf()` or `exit()` in tests [DOC]
- [ ] Use `fwts_log_*`, `fwts_passed`, `fwts_failed`, `fwts_warning`, `fwts_skipped`, `fwts_advice`
- [ ] No trailing `"\n"` in log messages (91 existing)
- [ ] `fwts_failed(fw, LOG_LEVEL_x, "CamelCaseLabel", ...)`: the label is CamelCase with no spaces or colons and is unique
- [ ] Integer formats: `"%" PRIx32`, with a space on each side of `PRI*` (966 vs 13); no `%d` or `%x` for `uint*_t`, and no `%lx`
- [ ] Hex output: `0x%8.8" PRIx32` (zero-padded width) is the most common style (440 vs 305 for plain)
- [ ] Use `snprintf` rather than `sprintf`, and avoid `strcpy`/`strcat` (86 legacy instances)

## 13. Out of scope
- [ ] Don't touch `src/acpica/`: it is upstream ACPICA [DOC]
- [ ] Leave legacy style alone unless the commit is a dedicated "minor code style clean-ups, no functional changes" commit
