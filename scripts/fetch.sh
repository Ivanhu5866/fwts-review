#!/bin/bash
# fwts-review: put the change under review into an isolated worktree.
#   fetch.sh [--repo DIR] [--base REF] INPUT   (default base: origin master)
#   fetch.sh [--repo DIR] --cleanup ID
# INPUT: PR number | https://github.com/fwts/fwts/pull/N[/changes|commits/<sha>]
#        | https://lists.ubuntu.com/archives/fwts-devel/YYYY-Month/NNNNNN.html | A..B
# Prints ID= KIND= BASE= HEAD= WORK= WT= (also saved to WORK/fetch.env).
# Exit: 0 ok, 2 usage, 3 fetch/apply failure (run --cleanup ID afterwards).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$HOME/work/fwts
ROOT=${FWTS_REVIEW_ROOT:-/tmp}	# override for tests only
CACHE=refs/fwts-review/origin-master
BASE_REF=$CACHE
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
# fetch only into refs/fwts-review/*: no tags, no FETCH_HEAD, no remote-tracking refs
gf() { g fetch -q --no-tags --no-write-fetch-head --refmap= origin "$@"; }
fail() {
	echo "fetch: $*" >&2
	if [ -n "$ID" ]; then echo "fetch: clean up with: $0 --cleanup $ID" >&2; fi
	exit 3
}

# keeps $CACHE: it is shared by all reviews
cleanup() {
	local id=$1 work=$ROOT/fwts-review-$1 w
	if ! [[ $id =~ ^[A-Za-z0-9._-]+$ ]] || [[ $id == *..* ]]; then
		echo "fetch: bad ID '$id'" >&2
		exit 2
	fi
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
	trap 'rm -f "$MBOX" "$MBOX.out"' EXIT
	python3 "$HERE/mbox_extract.py" "$IN" "$MBOX" > "$MBOX.out" ||
		fail "could not extract the patch from $IN"
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

# 2. resolve BASE/HEAD (local ranges need no network)
case $KIND in
local)
	BASE=$(g rev-parse --verify "${IN%%..*}^{commit}") || fail "bad base ${IN%%..*}"
	HEAD=$(g rev-parse --verify "${IN##*..}^{commit}") || fail "bad head ${IN##*..}"
	ID=local-${BASE:0:8}-${HEAD:0:8}
	;;
*)
	gf "+refs/heads/master:$CACHE" || fail "git fetch origin master failed"
	g rev-parse -q --verify "$BASE_REF^{commit}" > /dev/null || fail "bad --base $BASE_REF"
	;;
esac
WORK=$ROOT/fwts-review-$ID
if [ -e "$WORK" ]; then cleanup "$ID" > /dev/null; fi
mkdir -p "$WORK/logs"

case $KIND in
pr)
	gf "+pull/$N/head:refs/fwts-review/$ID" || fail "cannot fetch PR $N"
	gh pr view "$N" -R fwts/fwts \
		--json number,title,body,author,baseRefName,headRefName,commits,files,url \
		> "$WORK/pr.json" || echo "WARNING: gh pr view failed" >&2
	if [ -n "$SHA" ]; then
		g rev-parse -q --verify "$SHA^{commit}" > /dev/null ||
			gf "$SHA" || fail "commit $SHA not found"
		HEAD=$(g rev-parse "$SHA^{commit}")
		g merge-base --is-ancestor "$HEAD" "refs/fwts-review/$ID" ||
			echo "WARNING: $SHA is not in the current PR head (force-pushed?)" >&2
		BASE=$(g rev-parse "$HEAD^")
	else
		HEAD=$(g rev-parse "refs/fwts-review/$ID")
		BASE=$(g merge-base "$BASE_REF" "$HEAD") ||
			fail "no merge base between $BASE_REF and PR $N"
	fi
	g worktree add -q --detach "$WORK/wt" "$HEAD" || fail "git worktree add failed"
	;;
local)
	g worktree add -q --detach "$WORK/wt" "$HEAD" || fail "git worktree add failed"
	;;
ml)
	mv "$MBOX" "$WORK/series.mbox"
	rm -f "$MBOX.out"
	BASE=$(g rev-parse "$BASE_REF^{commit}")
	g worktree add -q --detach "$WORK/wt" "$BASE" || fail "git worktree add failed"
	if ! git -C "$WORK/wt" am -3 "$WORK/series.mbox" > "$WORK/logs/am.log" 2>&1; then
		git -C "$WORK/wt" am --abort > /dev/null 2>&1 || true
		cat "$WORK/logs/am.log" >&2
		fail "git am failed on $BASE_REF; retry with --base <older ref>"
	fi
	HEAD=$(git -C "$WORK/wt" rev-parse HEAD)
	g update-ref "refs/fwts-review/$ID" "$HEAD" || fail "update-ref failed"
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
