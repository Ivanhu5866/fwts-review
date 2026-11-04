#!/bin/bash
# fwts-review: build every commit, make check, clang, cppcheck, fixture runs.
#   build_test.sh WORK BASE HEAD
# WORK is /tmp/fwts-review-<ID> from fetch.sh (WORK/wt must exist).
# Writes WORK/logs/*; prints a summary; always exits 0 unless usage error.
set -uo pipefail
[ $# -eq 3 ] || { sed -n '2,5p' "$0" >&2; exit 2; }
WORK=$(cd "$1" && pwd) || exit 2
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
	if ! git -C "$WT" checkout -q --detach "$c"; then
		GCC[$c]="FAIL: checkout"; echo "gcc ${c:0:8}: ${GCC[$c]}"; continue
	fi
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
runfw() {	# TREE TEST DUMP (same invocation and owner filter as fwts-test/*/test-*.sh)
	LC_ALL=C "$1/src/fwts" --log-format="%line %owner " -w 80 -j "$1/data" \
		--dumpfile="$3" "$2" - 2>&1 | cut -c7- | grep "^$2 "
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
