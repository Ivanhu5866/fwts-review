## fwts patch / PR review checklist

**Commit**
- [ ] Subject line: `component: subcomponent: summary`
- [ ] `Signed-off-by:` on every commit
- [ ] Commit body explains why; the reasoning isn't only in the PR description
- [ ] `BugLink:` line for related issues
- [ ] One logical change per commit; fix-ups squashed; unrelated changes split out
- [ ] Every commit builds on its own
- [ ] Correct copyright and GPL header on new or changed files

**Build**
- [ ] Builds with `-Wall -Wextra -Werror`, with no new GCC or Clang warnings
- [ ] `make check` passes
- [ ] Parsing code run under ASan or valgrind

**Style**
- [ ] K&R style with tabs, no trailing whitespace, continuation lines aligned
- [ ] `/* */` comments only, no `//`
- [ ] No unused variables or includes, no extra blank lines, no stray `"\n"` in log messages
- [ ] `fwts_` prefix for library APIs; test code and unexported code `static`
- [ ] Structs `typedef`'d, no `typedef` of `void *`, fixed-width integer types
- [ ] No clever macros; comments where the logic isn't obvious

**Correctness**
- [ ] Format specifiers match the types (`PRIx8`, `PRIu32`, `PRIx64`, ...)
- [ ] Bounds and lengths checked before reading; no off-by-ones; firmware lengths not trusted
- [ ] The field logged is the field checked
- [ ] Return values of system calls, library calls and ACPICA calls checked
- [ ] Null checks before dereferences; no unaligned access to mapped tables
- [ ] No leaks of memory, file descriptors or `DIR`s on any path

**Test results**
- [ ] No false PASS from error paths, failed lookups or "nothing found"
- [ ] Severity fits; no CRITICAL or HIGH for guesses
- [ ] No pass or fail on values that come from emulated hardware regions
- [ ] Generic tests' behaviour unchanged; profile checks (SBBR, BRS-I, ...) in their own tests
- [ ] Unique CamelCase failure labels with helpful `fwts_advice()`
- [ ] Existing `fwts_acpi_*` helpers reused; shared code moved into the library

**Framework**
- [ ] No `exit()` or `printf()` in tests; `fwts_log_*` used instead
- [ ] No logging from option handlers
- [ ] `FWTS_ERROR` means the test couldn't run; failures reported with `fwts_failed()`
- [ ] Root privilege declared correctly
- [ ] ACPICA sources not modified

**Tests and docs**
- [ ] Regression test in `fwts-test/` for fixes and new parsing code, added to `TESTS` in `Makefile.am`
- [ ] Expected logs updated when output changes
- [ ] New options documented in `doc/fwts.1` and the `arg-help` expected logs
- [ ] Spec section or rule cited where useful
