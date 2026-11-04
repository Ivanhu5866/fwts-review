#!/bin/bash
# fwts-review: build every commit, make check, clang, cppcheck, fixture runs.
#   build_test.sh WORK BASE HEAD
# WORK is /tmp/fwts-review-<ID> from fetch.sh (WORK/wt must exist).
# Writes WORK/logs/*; prints a summary. Exit 0; 2 usage/empty range; 3 no merge base.
set -uo pipefail
[ $# -eq 3 ] || { sed -n '2,5p' "$0" >&2; exit 2; }
WORK=$(cd "$1" && pwd) || exit 2
WT=$WORK/wt
LOGS=$WORK/logs
J=$(nproc)
mkdir -p "$LOGS"
BASE=$(git -C "$WT" rev-parse "$2^{commit}") || exit 2
HEAD=$(git -C "$WT" rev-parse "$3^{commit}") || exit 2
if [ -z "$(git -C "$WT" rev-list -1 "$BASE..$HEAD")" ]; then
	echo "no commits in range ${BASE:0:8}..${HEAD:0:8}" >&2
	exit 2
fi
# Two-dot diffs use the merge base, so a BASE that is not an ancestor of HEAD
# does not pull unrelated upstream changes into the review.
MB=$(git -C "$WT" merge-base "$BASE" "$HEAD") || {
	echo "no merge base between ${BASE:0:8} and ${HEAD:0:8}" >&2
	exit 3
}
if [ "$MB" != "$BASE" ]; then echo "MERGE_BASE=$MB"; fi

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

# 1. per-commit gcc build (bisectability); a merge HEAD is built after the loop
declare -A GCC
first=1
build_at() {	# COMMIT: checkout and build in WT, set GCC[COMMIT], print it
	local c=$1 log=$LOGS/build-${1:0:8}.log rc
	if ! git -C "$WT" checkout -q --detach "$c"; then
		GCC[$c]="FAIL: checkout"; echo "gcc ${c:0:8}: ${GCC[$c]}"; return
	fi
	if [ $first = 1 ]; then
		full_build "$WT" "$log"; rc=$?; first=0
	else
		incr_build "$WT" "$log"; rc=$?
		if [ $rc -ne 0 ]; then full_build "$WT" "$log"; rc=$?; fi
	fi
	if [ $rc -eq 0 ]; then GCC[$c]=PASS; else GCC[$c]="FAIL: $(first_err "$log")"; fi
	echo "gcc ${c:0:8}: ${GCC[$c]}"
}
COMMITS=$(git -C "$WT" rev-list --reverse --no-merges "$BASE..$HEAD")
for c in $COMMITS; do build_at "$c"; done
MERGE_HEAD=0
if [ -z "${GCC[$HEAD]:-}" ]; then
	MERGE_HEAD=1
	build_at "$HEAD"
fi
git -C "$WT" checkout -q --detach "$HEAD"
HEAD_OK=0
[ "${GCC[$HEAD]}" = PASS ] && HEAD_OK=1

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
CHANGED_C=$(git -C "$WT" diff --name-only --diff-filter=AMR "$MB" "$HEAD" -- '*.c' |
	grep -v '^src/acpica/' || true)
run_cpp() {	# REV OUT
	local tmp f
	tmp=$(mktemp -d) || return
	for f in $CHANGED_C; do
		mkdir -p "$tmp/$(dirname "$f")"
		git -C "$WT" show "$1:$f" > "$tmp/$f" 2> /dev/null || rm -f "$tmp/$f"
	done
	( cd "$tmp" && cppcheck --enable=warning,style,portability --quiet \
		--suppress=missingIncludeSystem --template='{file}:{line}:{id}:{message}' . ) 2> "$2"
	rm -rf "$tmp"
}
# "count key" per finding with the line number dropped, so moved code is not "new"
norm() { sed -E 's/^([^:]*):[0-9]+:/\1::/' "$1" | sort | uniq -c; }
if ! command -v cppcheck > /dev/null; then
	CP="SKIP (cppcheck not installed)"
elif [ -z "$CHANGED_C" ]; then
	CP="N/A (no .c changes)"
else
	run_cpp "$MB" "$LOGS/cppcheck-base.txt"
	run_cpp "$HEAD" "$LOGS/cppcheck-head.txt"
	# a finding is new when its per-key count grew; print it once per extra occurrence
	awk 'FNR == 1 { f++ }
		{ n = $1; k = $0; sub(/^ *[0-9]+ /, "", k) }
		f == 1 { b[k] = n; next }
		{ for (i = b[k] + 1; i <= n; i++) print k }' \
		<(norm "$LOGS/cppcheck-base.txt") <(norm "$LOGS/cppcheck-head.txt") \
		> "$LOGS/cppcheck-new.txt"
	CP="$(wc -l < "$LOGS/cppcheck-new.txt") new"
fi
echo "cppcheck: $CP"

# 5. fixture runs for touched tests, base vs head (and head vs expected output).
# stdout lists only rows worth reading: base/head diff, summary changed, head differs
# from the expected .log, or no summary line unless the output matches expected exactly.
runfw() {	# TREE TEST DUMP WIDTH [EXCLUDE]: same invocation/filter as fwts-test/*/test-*.sh
	LC_ALL=C "$1/src/fwts" --log-format="%line %owner " -w "$4" -j "$1/data" \
		--dumpfile="$3" "$2" - 2> /dev/null | cut -c7- | grep "^$2 " |
		if [ -n "${5:-}" ]; then grep -v -- "$5"; else cat; fi
}
# Join wrapped lines first: at -w 80 the summary can wrap mid-sentence.
fsum() {
	local s
	s=$(sed -E 's/^[^ ]+ +//' "$1" | tr '\n' ' ' |
		grep -oE '[0-9]+ passed, [0-9]+ failed, [0-9]+ warnings?, [0-9]+ aborted' | tail -1)
	echo "${s:-no-summary}"
}
fxpath() {	# PATH-FROM-SCRIPT SCRIPT-DIR -> absolute path
	local p=${1//\"/}
	case $p in
	'$FWTSTESTDIR/'*) echo "$WT/fwts-test/${p#\$FWTSTESTDIR/}" ;;
	'${FWTSTESTDIR}/'*) echo "$WT/fwts-test/${p#\$\{FWTSTESTDIR\}/}" ;;
	'$HERE/'*) echo "$2/${p#\$HERE/}" ;;
	/*) echo "$p" ;;
	*) echo "$2/$p" ;;
	esac
}
BASE_STATE=
need_base() {	# build wt-base at the merge base on first use
	if [ -z "$BASE_STATE" ]; then
		add_wt wt-base "$MB"
		if full_build "$WORK/wt-base" "$LOGS/build-base.log"; then BASE_STATE=ok
		else BASE_STATE=fail; fi
	fi
	[ "$BASE_STATE" = ok ]
}
TOUCHED=$(for f in $(git -C "$WT" diff --name-only "$MB" "$HEAD" -- 'src/*.c' |
		grep -vE '^src/(lib|acpica|libfwtsacpica|libfwtsiasl|utilities)/'); do
		[ -f "$WT/$f" ] && sed -n 's/^FWTS_REGISTER[A-Z_]*("\([^"]*\)".*/\1/p' "$WT/$f"
	done | sort -u)
FXT=$LOGS/fixtures.txt
: > "$FXT"
SHOW=()
if [ -z "$TOUCHED" ]; then
	FX="N/A (no test source touched)"
elif [ $HEAD_OK = 0 ]; then
	FX="SKIP (head build failed)"
else
	nfx=0 nchg=0 nexp=0 nunch=0 nnocov=0 nklog=0
	for t in $TOUCHED; do
		ndump=0 nkl=0
		for s in "$WT"/fwts-test/"$t"-[0-9]*/test-*.sh; do
			[ -f "$s" ] || continue
			if grep -q -- '--klog' "$s"; then nkl=$((nkl + 1)); continue; fi
			line=$(grep -m1 -- '--dumpfile=' "$s") || continue
			ndump=$((ndump + 1))
			sdir=$(dirname "$s")
			rel=${s#"$WT"/}
			tag=$(echo "${rel%.sh}" | tr '/' '_')
			dump=$(fxpath "$(echo "$line" | grep -oE -- '--dumpfile=[^ ]+' | sed 's/^--dumpfile=//')" "$sdir")
			w=$(echo "$line" | grep -oE -- ' -w [0-9]+' | awk '{print $2}' | head -1)
			w=${w:-80}
			excl=$(echo "$line" | sed -nE 's/.*\| grep -v ([A-Za-z0-9_]+) .*/\1/p')
			# expected output only when the script's filter is one runfw reproduces
			exp=
			if echo "$line" | grep -qE -- '- \| (cut -c7- \| grep "\^[^"]*"|grep "\^[^"]*"( \| grep -v [A-Za-z0-9_]+)? \| cut -c7-) > \$TMPLOG'; then
				e=$(grep -m1 -oE 'diff \$TMPLOG [^ ]+' "$s" | awk '{print $3}')
				[ -n "$e" ] && exp=$(fxpath "$e" "$sdir")
			fi
			row="$rel (${dump#"$WT"/}):"
			grep -qF "$rel" "$WT/Makefile.am" || row="$rel [not in TESTS] (${dump#"$WT"/}):"
			if [ ! -f "$dump" ]; then
				echo "$row dump file missing" >> "$FXT"; SHOW+=("$row dump file missing"); continue
			fi
			runfw "$WT" "$t" "$dump" "$w" "$excl" > "$LOGS/fx-head-$tag.log"
			nfx=$((nfx + 1))
			hs=$(fsum "$LOGS/fx-head-$tag.log")
			ex="exp=n/a" ne=-1
			if [ -n "$exp" ] && [ -f "$exp" ]; then
				ne=$(diff "$exp" "$LOGS/fx-head-$tag.log" | grep -c '^[<>]')
				ex="exp=$ne"
				[ "$ne" -gt 0 ] && nexp=$((nexp + 1))
			fi
			if need_base; then
				runfw "$WORK/wt-base" "$t" "$dump" "$w" "$excl" > "$LOGS/fx-base-$tag.log"
				bs=$(fsum "$LOGS/fx-base-$tag.log")
				nd=$(diff "$LOGS/fx-base-$tag.log" "$LOGS/fx-head-$tag.log" | grep -c '^[<>]')
				[ "$nd" -gt 0 ] && nchg=$((nchg + 1))
				row="$row base[$bs] head[$hs] diff=$nd $ex"
				if [ "$nd" -gt 0 ] || [ "$bs" != "$hs" ] || [ "$ne" -gt 0 ] ||
				   { [ "$hs" = no-summary ] && [ "$ne" != 0 ]; }; then
					SHOW+=("$row")
				else
					nunch=$((nunch + 1))
				fi
			else
				row="$row head[$hs] $ex (base build failed)"
				if [ "$ne" -gt 0 ] || { [ "$hs" = no-summary ] && [ "$ne" != 0 ]; }; then SHOW+=("$row")
				else nunch=$((nunch + 1)); fi
			fi
			echo "$row" >> "$FXT"
		done
		if [ $ndump = 0 ]; then
			if [ $nkl -gt 0 ]; then
				echo "$t: klog-style fixture (covered by make check)" >> "$FXT"; nklog=$((nklog + 1))
			else
				echo "$t: no fixture coverage" >> "$FXT"; nnocov=$((nnocov + 1))
			fi
		fi
	done
	FX="$nfx run, $nchg changed vs base, $nexp differ from expected"
	[ "$BASE_STATE" = fail ] && FX="$FX (base build failed)"
fi
echo "fixtures: $FX"
for r in "${SHOW[@]}"; do echo "  $r"; done
if [ -n "$TOUCHED" ] && [ $HEAD_OK = 1 ]; then
	echo "  $nnocov tests without fixture coverage, $nklog klog-style, $nunch unchanged (see logs/fixtures.txt)"
fi

# 6. regression-test presence
CHANGED=$(git -C "$WT" diff --name-only "$MB" "$HEAD")
REG=$LOGS/regression.txt
: > "$REG"
if echo "$CHANGED" | grep -v '^src/acpica/' | grep -qE '^src/.*\.[ch]$' &&
   ! echo "$CHANGED" | grep -q '^fwts-test/'; then
	echo "NO-FWTS-TEST-CHANGE (advisory): src/ changed but nothing under fwts-test/" >> "$REG"
fi
for s in $(git -C "$WT" diff --name-only --diff-filter=A "$MB" "$HEAD" -- 'fwts-test/*/test-*.sh'); do
	grep -qF "$s" "$WT/Makefile.am" || echo "NOT-IN-TESTS: $s missing from TESTS in Makefile.am" >> "$REG"
done
if git -C "$WT" diff "$MB" "$HEAD" -- src |
	grep -qE '^\+[[:space:]]*\{[[:space:]]*"[a-z][a-z0-9-]*",[[:space:]]*"'; then
	echo "$CHANGED" | grep -q '^doc/fwts.1' ||
		echo "OPTION-NO-MANPAGE: new option? doc/fwts.1 not updated" >> "$REG"
	echo "$CHANGED" | grep -q '^fwts-test/arg-help' ||
		echo "OPTION-NO-ARG-HELP: new option? fwts-test/arg-help-* not updated" >> "$REG"
fi
echo "regression checks:"
if [ -s "$REG" ]; then sed 's/^/  /' "$REG"; else echo "  none"; fi

# 7. matrix
row() {	# COMMIT SUBJECT-PREFIX
	local subj
	subj=$2$(git -C "$WT" log -1 --format=%s "$1" | cut -c1-60)
	if [ "$1" = "$HEAD" ]; then
		printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "${1:0:8}" "$subj" "${GCC[$1]}" "$CL" "$MC" "$CP" "$FX"
	else
		printf '%s\t%s\t%s\t-\t-\t-\t-\n' "${1:0:8}" "$subj" "${GCC[$1]}"
	fi
}
{
	printf 'commit\tsubject\tgcc\tclang\tmake_check\tcppcheck_new\tfixtures\n'
	for c in $COMMITS; do row "$c" ""; done
	[ $MERGE_HEAD = 1 ] && row "$HEAD" "merge-head: "
} > "$LOGS/matrix.tsv"
echo "matrix: $LOGS/matrix.tsv"
