#!/usr/bin/env python3
"""Extract a patch (or the whole [PATCH n/m] series) from the fwts-devel
pipermail archive into an mbox that `git am` can apply.

Usage: mbox_extract.py URL OUT_MBOX
  URL: https://lists.ubuntu.com/archives/fwts-devel/YYYY-Month/NNNNNN.html
Prints MSGID=<id> and PATCHES=<n>. Exit 2 usage, 3 fetch/lookup failure.
"""
import gzip
import mailbox
import os
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

ARCHIVE = "https://lists.ubuntu.com/archives/fwts-devel"
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
URL_RE = re.compile(r"/fwts-devel/(\d{4})-([A-Za-z]+)/\d+\.html")
LEAD_RE = re.compile(r"^((?:\[[^\]]*\]\s*)+)")
NM_RE = re.compile(r"(\d+)/(\d+)")
DIFF_RE = re.compile(r"^diff --git ", re.M)
MSG_END_RE = re.compile(r"^(?:---|diff --git .*)$", re.M)
TRAILER_RE = re.compile(r"^(?:From|Signed-off-by|Acked-by|Reviewed-by|Tested-by|"
                        r"Reported-by|Co-developed-by|Suggested-by|Cc):",
                        re.I | re.M)
OBF_RE = re.compile(r"([A-Za-z0-9._%+-]+) at ([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")


class IncompleteSeries(Exception):
    pass


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def clean_id(v):
    return str(v or "").strip().strip("<>").strip()


def norm_from(value):
    m = re.match(r"\s*(\S+) at (\S+) \((.*)\)\s*$", str(value))
    return f"{m.group(3)} <{m.group(1)}@{m.group(2)}>" if m else str(value)


def msgid_from_html(text):
    m = re.search(r"In-Reply-To=%3C(.*?)%3E", text)
    return urllib.parse.unquote(m.group(1)) if m else None


def subject(msg):
    return " ".join(str(msg.get("Subject", "")).split())


def has_diff(msg):
    body = msg.get_payload(decode=False)
    body = body if isinstance(body, str) else str(body)
    return bool(DIFF_RE.search(body))


def deobfuscate_body(msg):
    """Undo pipermail's 'user at host' in the commit message's in-body From:
    and trailer lines; the diff (after the first '---' line) is untouched."""
    cte = str(msg.get("Content-Transfer-Encoding", "")).lower()
    if msg.is_multipart() or cte in ("base64", "quoted-printable"):
        return
    # work on the raw bytes: get_payload(decode=False) is lossy for 8-bit text
    body = msg.get_payload(decode=True).decode("ascii", "surrogateescape")
    end = MSG_END_RE.search(body)
    cut = end.start() if end else len(body)
    head = "".join(OBF_RE.sub(r"\1@\2", ln) if TRAILER_RE.match(ln) else ln
                   for ln in body[:cut].splitlines(keepends=True))
    msg.set_payload((head + body[cut:]).encode("ascii", "surrogateescape"))


def patch_info(msg):
    """(key, n, m) for a [PATCH] subject, n/m None for single patches."""
    s = subject(msg)
    if s.lower().startswith("re:"):
        return None
    m = LEAD_RE.match(s)
    if not m or "PATCH" not in m.group(1).upper():
        return None
    lead = m.group(1)
    nm = NM_RE.search(lead)
    key = " ".join(NM_RE.sub("", lead).split())
    return (key, int(nm.group(1)), int(nm.group(2))) if nm else (key, None, None)


def select_series(msgs, target):
    by_id = {clean_id(m["Message-ID"]): m for m in msgs}
    t = by_id.get(target)
    if t is None:
        raise LookupError(f"message <{target}> not found in archive")
    info = patch_info(t)
    if info is None:
        raise LookupError("target is not a [PATCH] message")
    key, n, total = info
    if n is None:
        if not has_diff(t):
            raise LookupError("target [PATCH] message has no diff (a reply?)")
        return [t]
    cands = {}
    for mid, m in by_id.items():
        i = patch_info(m)
        if i and i[0] == key and i[2] == total and (i[1] == 0 or has_diff(m)):
            cands[mid] = (i[1], clean_id(m["In-Reply-To"]))
    if target not in cands:
        raise LookupError("target [PATCH n/m] message has no diff (a reply?)")
    group, seen_n = {target}, {n}
    changed = True
    while changed:
        changed = False
        member_irts = {cands[g][1] for g in group if g in cands}
        for mid, (cn, irt) in cands.items():
            if mid in group or cn in seen_n:
                continue
            # parent, child, or sibling (same parent, e.g. the cover
            # letter is missing from the archive)
            if irt in group or mid in member_irts or (irt and irt in member_irts):
                group.add(mid)
                seen_n.add(cn)
                changed = True
    got = sorted((cands[g][0], g) for g in group if cands[g][0] != 0)
    if [x[0] for x in got] != list(range(1, total + 1)):
        raise IncompleteSeries(
            f"incomplete series: have {[x[0] for x in got]} of {total}")
    return [by_id[g] for _, g in got]


def next_month(year, month):
    i = MONTHS.index(month)
    return (str(int(year) + 1), MONTHS[0]) if i == 11 else (year, MONTHS[i + 1])


def load_month(year, month, tmpdir=None):
    # the current month is only served live as .txt; .txt.gz is rebuilt nightly
    url = f"{ARCHIVE}/{year}-{month}.txt"
    try:
        data = fetch(url)
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        data = fetch(url + ".gz")
    try:
        data = gzip.decompress(data)
    except OSError:
        pass
    with tempfile.NamedTemporaryFile(suffix=".mbox", dir=tmpdir) as f:
        f.write(data)
        f.flush()
        box = mailbox.mbox(f.name, create=False)
        try:
            return list(box)
        finally:
            box.close()


def write_mbox(msgs, out):
    box = mailbox.mbox(out, create=True)
    box.lock()
    try:
        for m in msgs:
            frm = norm_from(m["From"])
            del m["From"]
            m["From"] = frm
            deobfuscate_body(m)
            box.add(m)
        box.flush()
    finally:
        box.unlock()
        box.close()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    url, out = argv
    m = URL_RE.search(url)
    if not m:
        print("mbox_extract: not a fwts-devel pipermail message URL", file=sys.stderr)
        return 2
    year, month = m.groups()
    tmpdir = os.path.dirname(os.path.abspath(out))
    try:
        target = msgid_from_html(fetch(url).decode("utf-8", "replace"))
        if not target:
            raise LookupError("no Message-ID in page")
        msgs = load_month(year, month, tmpdir)
        try:
            series = select_series(msgs, target)
        except IncompleteSeries as inc:
            try:
                msgs += load_month(*next_month(year, month), tmpdir)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    raise inc from None
                raise
            series = select_series(msgs, target)
    except Exception as e:  # network, lookup, incomplete series
        print(f"mbox_extract: {e}", file=sys.stderr)
        return 3
    write_mbox(series, out)
    print(f"MSGID={target}")
    print(f"PATCHES={len(series)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
