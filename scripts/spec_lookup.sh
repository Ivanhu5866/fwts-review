#!/bin/bash
# fwts-review spec lookup helper.
# Specs come only from the local library ($SPEC_DOC_DIR); nothing is fetched online.
#   spec_lookup.sh list SUBDIR                    list documents in the spec library
#   spec_lookup.sh pdf SUBDIR REGEX [NAME_GLOB]   search pdf/docx/odt/txt documents (page or line)
#   spec_lookup.sh actbl SIG                      print ACPICA actbl*.h structs for a table
# REGEX is a POSIX ERE matched case-insensitively: the input is lowercased and so
# is every REGEX character not preceded by a backslash (so \S, \. and \( keep their
# meaning). Write bracket classes in lowercase or case-agnostic form ([a-z],
# not [A-Z] or [[:upper:]]). \S \w \y etc. are gawk-only extensions.
# SIG may be a signature (APIC, "RSD PTR") or an ACPICA name (MADT).
# Exit 2 on usage/regex/path errors, 1 if pdf matches nothing (after an
# 'update the spec' hint) or actbl finds nothing.
# Env: SPEC_DOC_DIR SPEC_CACHE_DIR FWTS_REPO MAX
set -u
SPEC_DOC_DIR=${SPEC_DOC_DIR:-$HOME/CloudStation/Document}
SPEC_CACHE_DIR=${SPEC_CACHE_DIR:-$HOME/.cache/fwts-review/specs}
FWTS_REPO=${FWTS_REPO:-$HOME/work/fwts}
MAX=${MAX:-40}

die() { echo "spec_lookup: $*" >&2; exit 2; }
need_spec() {	# SUBDIR GLOB WHY
	echo "spec_lookup: $3 in $SPEC_DOC_DIR/$1 (glob '$2')." >&2
	echo "UPDATE-SPEC: please add or update the spec in $SPEC_DOC_DIR/$1, then rerun." >&2
}
usage() { sed -n '2,14p' "$0" >&2; exit 2; }

lower_re() {	# lowercase REGEX except characters escaped by a backslash
	local s=$1 o= c
	while [ -n "$s" ]; do
		c=${s:0:1}
		if [ "$c" = '\' ]; then
			o+=${s:0:2}; s=${s:2}
		else
			o+=${c,,}; s=${s:1}
		fi
	done
	printf '%s' "$o"
}

check_re() {	# the regex goes through ENVIRON: awk -v would process its escapes
	RE=$1 awk 'BEGIN { if ("" ~ ENVIRON["RE"]) x = 1 }' >/dev/null ||
		die "invalid regex: $1"
}

list_docs() {	# SUBDIR [GLOB]
	[ -d "$SPEC_DOC_DIR/$1" ] || die "no $SPEC_DOC_DIR/$1"
	find "$SPEC_DOC_DIR/$1" -type f -iname "${2:-*}" \
		\( -iname '*.pdf' -o -iname '*.docx' -o -iname '*.odt' -o -iname '*.txt' \) |
		# newest first: version-sort on the basename with [._ -] runs as "."
		awk '{ n = split($0, p, "/"); k = p[n]; gsub(/[._ -]+/, ".", k); print k "\t" $0 }' |
		sort -t "$(printf '\t')" -k1,1Vr | cut -f2-
}

to_text() {	# FILE -> prints cache path
	local f=$1 key out tmp
	key=$(printf '%s:%s' "$f" "$(stat -c %Y "$f")" | sha1sum | cut -c1-40)
	out=$SPEC_CACHE_DIR/$key.txt
	mkdir -p "$SPEC_CACHE_DIR"
	if [ ! -s "$out" ]; then
		# convert to a temp file so an interrupted run never leaves a truncated cache
		tmp=$out.tmp.$$
		case "${f,,}" in
		*.pdf) pdftotext -layout "$f" "$tmp" 2>/dev/null ;;
		*.docx|*.odt) python3 - "$f" "$tmp" <<'EOF'
import html, re, sys, zipfile
f, out = sys.argv[1], sys.argv[2]
name = "content.xml" if f.lower().endswith(".odt") else "word/document.xml"
x = zipfile.ZipFile(f).read(name).decode("utf-8", "replace")
x = re.sub(r"</(?:w:p|text:p|text:h)>", "\n", x)
x = re.sub(r"<(?:w:tab|text:tab)/>", "\t", x)
x = re.sub(r"<[^>]+>", "", x)
open(out, "w", encoding="utf-8").write(html.unescape(x))
EOF
			;;
		*) cp "$f" "$tmp" ;;
		esac && mv -f "$tmp" "$out" || { rm -f "$tmp"; return 1; }
	fi
	echo "$out"
}

cmd_pdf() {	# SUBDIR REGEX [GLOB]
	local re docs out
	[ -d "$SPEC_DOC_DIR/$1" ] ||
		{ need_spec "$1" "${3:-*}" "no such directory"; exit 2; }
	re=$(lower_re "$2")
	check_re "$re"
	[ "$MAX" -gt 0 ] 2>/dev/null || return 0
	docs=$(list_docs "$1" "${3:-*}")
	[ -n "$docs" ] || { need_spec "$1" "${3:-*}" "no document"; exit 1; }
	out=$(printf '%s\n' "$docs" | search_docs "$1" "$re")
	[ -n "$out" ] || { need_spec "$1" "${3:-*}" "no match for '$2'"; exit 1; }
	printf '%s\n' "$out"
}

search_docs() {	# SUBDIR RE; document paths on stdin
	local f txt rel paged hits re=$2 left=$MAX
	# Stop converting further documents once MAX lines have been printed.
	while IFS= read -r f; do
		txt=$(to_text "$f") || { echo "WARNING: cannot convert $f" >&2; continue; }
		rel=${f#"$SPEC_DOC_DIR/$1/"}
		case "${f,,}" in *.docx|*.odt) paged=0 ;; *) paged=1 ;; esac
		hits=$(RE=$re awk -v fn="$rel" -v paged="$paged" -v max="$left" '
			BEGIN { re = ENVIRON["RE"]; p = 1; n = 0 }
			{ p += gsub(/\f/, "") }
			tolower($0) ~ re {
				sub(/^[ \t]+/, "")
				if (paged) printf "%s p.%d: %s\n", fn, p, $0
				else printf "%s l.%d: %s\n", fn, FNR, $0
				if (++n >= max) exit
			}' "$txt")
		[ -n "$hits" ] || continue
		printf '%s\n' "$hits" || exit 0
		left=$((left - $(printf '%s\n' "$hits" | wc -l)))
		[ "$left" -gt 0 ] || break
	done
}

cmd_actbl() {
	local arg names out hdrs=("$FWTS_REPO"/src/acpica/source/include/actbl*.h)
	arg=$(printf '%s' "$1" | tr -cd 'A-Za-z0-9' | tr 'a-z' 'A-Z')
	[ -n "$arg" ] || die "bad signature: $1"
	# map signature or name via '#define ACPI_SIG_<NAME> "<sig>"' (APIC -> madt)
	names=$(awk -v a="$arg" '
		/^#define[ \t]+ACPI_SIG_[A-Za-z0-9_]+[ \t]+"/ {
			name = $2; sub(/^ACPI_SIG_/, "", name)
			sig = $0; sub(/^[^"]*"/, "", sig); sub(/".*/, "", sig)
			gsub(/[^A-Za-z0-9]/, "", sig)
			if (toupper(name) == a || toupper(sig) == a) print tolower(name)
		}' "${hdrs[@]}" | sort -u | tr '\n' ' ')
	[ -n "$names" ] || names=$(printf '%s' "$arg" | tr 'A-Z' 'a-z')
	out=$(awk -v names="$names" '
		BEGIN { n = split(names, nm, " ") }
		/^typedef struct acpi_/ {
			keep = 0
			for (i = 1; i <= n; i++) {
				t = "acpi_table_" nm[i]
				if ($3 == t || index($3, t "_") == 1 ||
				    index($3, "acpi_" nm[i] "_") == 1)
					keep = 1
			}
			if (keep) printf "%s:%d\n", FILENAME, FNR
		}
		keep { print }
		keep && /^}/ { keep = 0; print "" }' "${hdrs[@]}")
	[ -n "$out" ] || { echo "spec_lookup: no ACPICA struct for $1" >&2; exit 1; }
	printf '%s\n' "$out"
}

case "${1:-}" in
list)	[ $# -ge 2 ] || usage; list_docs "$2" ;;
pdf)	[ $# -ge 3 ] || usage; cmd_pdf "$2" "$3" "${4:-}" ;;
actbl)	[ $# -ge 2 ] || usage; cmd_actbl "$2" ;;
*)	usage ;;
esac
