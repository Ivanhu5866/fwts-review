#!/bin/bash
# fwts-review spec lookup helper.
#   spec_lookup.sh update                         git pull ~/work/ACPI_spec
#   spec_lookup.sh acpi REGEX                     search ACPI spec RST (file:line [heading] text)
#   spec_lookup.sh list SUBDIR                    list documents in the spec library
#   spec_lookup.sh pdf SUBDIR REGEX [NAME_GLOB]   search pdf/docx/odt/txt documents (page or line)
#   spec_lookup.sh actbl SIG                      print ACPICA actbl*.h structs for a table
# Case-insensitive. Env: ACPI_SPEC_DIR SPEC_DOC_DIR SPEC_CACHE_DIR FWTS_REPO MAX
set -u
ACPI_SPEC_DIR=${ACPI_SPEC_DIR:-$HOME/work/ACPI_spec}
SPEC_DOC_DIR=${SPEC_DOC_DIR:-$HOME/CloudStation/Document}
SPEC_CACHE_DIR=${SPEC_CACHE_DIR:-$HOME/.cache/fwts-review/specs}
FWTS_REPO=${FWTS_REPO:-$HOME/work/fwts}
MAX=${MAX:-40}

die() { echo "spec_lookup: $*" >&2; exit 2; }
usage() { sed -n '2,9p' "$0" >&2; exit 2; }

cmd_update() {
	git -C "$ACPI_SPEC_DIR" pull --ff-only -q 2>&1 ||
		echo "WARNING: ACPI_spec pull failed; using local copy" >&2
	git -C "$ACPI_SPEC_DIR" log -1 --format='ACPI_spec at %h (%cs) %s'
}

cmd_acpi() {
	[ -d "$ACPI_SPEC_DIR/source" ] || die "no $ACPI_SPEC_DIR/source"
	awk -v re="$1" '
		FNR == 1 { head = ""; prev = "" }
		/^(=+|-+|~+|\^+|"+|\*+|#+)$/ && length($0) >= 3 && prev !~ /^[ \t]*$/ {
			head = prev; prev = $0; next
		}
		tolower($0) ~ tolower(re) {
			n = split(FILENAME, p, "/")
			printf "%s:%d [%s] %s\n", p[n], FNR, head, $0
		}
		{ prev = $0 }' "$ACPI_SPEC_DIR"/source/*.rst | head -n "$MAX"
}

list_docs() {	# SUBDIR [GLOB]
	[ -d "$SPEC_DOC_DIR/$1" ] || die "no $SPEC_DOC_DIR/$1"
	find "$SPEC_DOC_DIR/$1" -type f -iname "${2:-*}" \
		\( -iname '*.pdf' -o -iname '*.docx' -o -iname '*.odt' -o -iname '*.txt' \) |
		sort -V -r
}

to_text() {	# FILE -> prints cache path
	local f=$1 key out
	key=$(printf '%s:%s' "$f" "$(stat -c %Y "$f")" | sha1sum | cut -c1-40)
	out=$SPEC_CACHE_DIR/$key.txt
	mkdir -p "$SPEC_CACHE_DIR"
	if [ ! -s "$out" ]; then
		case "${f,,}" in
		*.pdf) pdftotext -layout "$f" "$out" 2>/dev/null || { rm -f "$out"; return 1; } ;;
		*.docx|*.odt) python3 - "$f" "$out" <<'EOF' || return 1
import html, re, sys, zipfile
f, out = sys.argv[1], sys.argv[2]
name = "content.xml" if f.lower().endswith(".odt") else "word/document.xml"
x = zipfile.ZipFile(f).read(name).decode("utf-8", "replace")
x = re.sub(r"</(?:w:p|text:p|text:h)>", "\n", x)
x = re.sub(r"<(?:w:tab|text:tab)/>", "\t", x)
x = re.sub(r"<[^>]+>", "", x)
open(out, "w").write(html.unescape(x))
EOF
			;;
		*) cp "$f" "$out" ;;
		esac
	fi
	echo "$out"
}

cmd_pdf() {	# SUBDIR REGEX [GLOB]
	local f txt rel paged hits left=$MAX
	[ "$left" -gt 0 ] 2>/dev/null || return 0
	# Stop converting further documents once MAX lines have been printed.
	list_docs "$1" "${3:-*}" | while IFS= read -r f; do
		txt=$(to_text "$f") || { echo "WARNING: cannot convert $f" >&2; continue; }
		rel=${f#"$SPEC_DOC_DIR/$1/"}
		case "${f,,}" in *.docx|*.odt) paged=0 ;; *) paged=1 ;; esac
		hits=$(awk -v re="$2" -v fn="$rel" -v paged="$paged" -v max="$left" '
			BEGIN { p = 1; n = 0 }
			{ p += gsub(/\f/, "") }
			tolower($0) ~ tolower(re) {
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
	local sig
	sig=$(printf '%s' "$1" | tr 'A-Z' 'a-z')
	awk -v sig="$sig" '
		/^typedef struct acpi_/ {
			keep = ($3 == "acpi_table_" sig || index($3, "acpi_" sig "_") == 1)
			if (keep) printf "%s:%d\n", FILENAME, FNR
		}
		keep { print }
		keep && /^}/ { keep = 0; print "" }' \
		"$FWTS_REPO"/src/acpica/source/include/actbl*.h
}

case "${1:-}" in
update) cmd_update ;;
acpi)	[ $# -ge 2 ] || usage; cmd_acpi "$2" ;;
list)	[ $# -ge 2 ] || usage; list_docs "$2" ;;
pdf)	[ $# -ge 3 ] || usage; cmd_pdf "$2" "$3" "${4:-}" ;;
actbl)	[ $# -ge 2 ] || usage; cmd_actbl "$2" ;;
*)	usage ;;
esac
