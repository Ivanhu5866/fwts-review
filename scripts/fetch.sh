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
	-h|--help) sed -n '2,8p' "$0"; exit 0 ;;
	*) break ;;
	esac
done
g() { git -C "$REPO" "$@"; }
fail() {
	echo "fetch: $*" >&2
	if [ -n "$ID" ]; then echo "fetch: clean up with: $0 --cleanup $ID" >&2; fi
	exit 3
}

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
[ $# -eq 1 ] || { sed -n '2,8p' "$0" >&2; exit 2; }
IN=$1
ID= SHA= N= MBOX=

# 1. classify the input and compute ID (before fetching, so cleanup is exact)
if [[ $IN =~ lists\.ubuntu\.com/archives/fwts-devel/ ]]; then
	KIND=ml
	MBOX=$(mktemp --suffix=.mbox)
	if ! python3 "$HERE/mbox_extract.py" "$IN" "$MBOX" > "$MBOX.out"; then
		rm -f "$MBOX" "$MBOX.out"
		fail "could not extract the patch from $IN"
	fi
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
	sed -n '2,8p' "$0" >&2; exit 2
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
