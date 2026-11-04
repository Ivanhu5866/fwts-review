import email
import mailbox
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import mbox_extract as mx  # noqa: E402

DIFF = "---\n x.c | 1 +\ndiff --git a/x.c b/x.c\n--- a/x.c\n+++ b/x.c\n"


def mk(mid, subject, irt=None, body=DIFF):
    hdr = f"From: a at b.c (A B)\nSubject: {subject}\nMessage-ID: <{mid}>\n"
    if irt:
        hdr += f"In-Reply-To: <{irt}>\n"
    return email.message_from_string(hdr + "\n" + body)


def ids(msgs):
    return [mx.clean_id(m["Message-ID"]) for m in msgs]


def test_norm_from():
    assert mx.norm_from("alkorv at posteo.uk (Al Korv)") == "Al Korv <alkorv@posteo.uk>"
    assert mx.norm_from("A <a@b.c>") == "A <a@b.c>"


def test_msgid_from_html():
    page = '<a href="mailto:x?Subject=y&In-Reply-To=%3C1-a%40b.uk%3E">'
    assert mx.msgid_from_html(page) == "1-a@b.uk"


def test_single_patch_ignores_reply_with_same_subject():
    msgs = [mk("p", "[PATCH] [v4] fwts: x"),
            mk("r", "[PATCH] [v4] fwts: x", irt="p", body="looks good\n")]
    assert ids(mx.select_series(msgs, "p")) == ["p"]


def test_series_with_cover_from_middle_patch():
    msgs = [mk("c", "[PATCH 0/2] cover", body="cover\n"),
            mk("p1", "[PATCH 1/2] a: one", irt="c"),
            mk("p2", "[PATCH 2/2] a: two", irt="c"),
            mk("re", "Re: [PATCH 1/2] a: one", irt="p1")]
    assert ids(mx.select_series(msgs, "p2")) == ["p1", "p2"]
    assert ids(mx.select_series(msgs, "c")) == ["p1", "p2"]


def test_series_whose_cover_is_missing_from_archive():
    msgs = [mk("p1", "[PATCH 1/2] a: one", irt="gone"),
            mk("p2", "[PATCH 2/2] a: two", irt="gone")]
    assert ids(mx.select_series(msgs, "p2")) == ["p1", "p2"]


def test_series_without_cover_skips_older_version():
    msgs = [mk("o1", "[PATCH 1/2] a: one"),
            mk("o2", "[PATCH 2/2] a: two", irt="o1"),
            mk("n1", "[PATCH v2 1/2] a: one", irt="o1"),
            mk("n2", "[PATCH v2 2/2] a: two", irt="n1")]
    assert ids(mx.select_series(msgs, "n2")) == ["n1", "n2"]


def test_incomplete_series_raises():
    msgs = [mk("p1", "[PATCH 1/3] a: one"), mk("p2", "[PATCH 2/3] a: two", irt="p1")]
    with pytest.raises(mx.IncompleteSeries):
        mx.select_series(msgs, "p1")


def test_next_month():
    assert mx.next_month("2025", "December") == ("2026", "January")
    assert mx.next_month("2025", "August") == ("2025", "September")


def test_write_mbox_normalises_from(tmp_path):
    out = tmp_path / "s.mbox"
    mx.write_mbox([mk("p", "[PATCH] a: x")], str(out))
    (m,) = list(mailbox.mbox(str(out)))
    assert m["From"] == "A B <a@b.c>"


def test_has_diff_ignores_quoted_diff():
    assert mx.has_diff(mk("p", "[PATCH] a: x"))
    reply = mk("r", "[PATCH 1/2] a: one", irt="p",
               body="> diff --git a/x.c b/x.c\n> +++ b/x.c\nok\n")
    assert not mx.has_diff(reply)


def test_single_patch_target_without_diff_raises():
    msgs = [mk("p", "[PATCH] [v5] a: x"),
            mk("r", "[PATCH] [v5] a: x", irt="p", body="ping\n")]
    with pytest.raises(LookupError, match="no diff"):
        mx.select_series(msgs, "r")


def test_write_mbox_restores_at_in_commit_message_only(tmp_path):
    diff = ("---\n x.c | 1 +\ndiff --git a/x.c b/x.c\n--- a/x.c\n+++ b/x.c\n"
            "+Signed-off-by: q at r.s\n+From: t at u.v\n")
    body = ("From: Haibo Xu <haibo1.xu at intel.com>\n\nmsg\n\n"
            "Signed-off-by: Haibo Xu <haibo1.xu at intel.com>\n"
            "Reviewed-by: R <r at x.org>\nCc: c at d.e\n"
            "Signed-off-by: Sunil V L <sunilvl at ventanamicro.com>\n" + diff)
    out = tmp_path / "s.mbox"
    mx.write_mbox([mk("p", "[PATCH] a: x", body=body)], str(out))
    (m,) = list(mailbox.mbox(str(out)))
    got = m.get_payload()
    head, sep, tail = got.partition("\n---\n")
    assert head == ("From: Haibo Xu <haibo1.xu@intel.com>\n\nmsg\n\n"
                    "Signed-off-by: Haibo Xu <haibo1.xu@intel.com>\n"
                    "Reviewed-by: R <r@x.org>\nCc: c@d.e\n"
                    "Signed-off-by: Sunil V L <sunilvl@ventanamicro.com>")
    assert sep + tail == "\n" + diff


class _Resp:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.data


def _serve(monkeypatch, pages):
    seen = []

    def urlopen(req, timeout=None):
        url = req.full_url
        seen.append(url)
        if url not in pages:
            raise mx.urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return _Resp(pages[url])
    monkeypatch.setattr(mx.urllib.request, "urlopen", urlopen)
    return seen


MBOX = (b"From a at b.c  Mon Aug  4 00:00:00 2025\n"
        b"From: a at b.c (A B)\nSubject: [PATCH] a: x\nMessage-ID: <p>\n\nbody\n\n")


def test_load_month_prefers_live_txt(monkeypatch, tmp_path):
    a = mx.ARCHIVE
    seen = _serve(monkeypatch, {f"{a}/2026-November.txt": MBOX,
                                f"{a}/2026-November.txt.gz": b"stale"})
    msgs = mx.load_month("2026", "November", str(tmp_path))
    assert ids(msgs) == ["p"]
    assert seen == [f"{a}/2026-November.txt"]


@pytest.mark.parametrize("gz", [True, False])
def test_load_month_falls_back_to_txt_gz(monkeypatch, tmp_path, gz):
    import gzip
    data = gzip.compress(MBOX) if gz else MBOX
    _serve(monkeypatch, {f"{mx.ARCHIVE}/2025-August.txt.gz": data})
    assert ids(mx.load_month("2025", "August", str(tmp_path))) == ["p"]


def test_main_reports_incomplete_series_when_next_month_missing(
        monkeypatch, tmp_path, capsys):
    a = mx.ARCHIVE
    page = b'<a href="mailto:x?In-Reply-To=%3Cp1%3E">'
    box = (b"From a at b.c  Mon Aug  4 00:00:00 2025\n"
           b"From: a at b.c (A B)\nSubject: [PATCH 1/2] a: one\nMessage-ID: <p1>\n\n"
           + DIFF.encode() + b"\n")
    _serve(monkeypatch, {f"{a}/2026-November/000001.html": page,
                         f"{a}/2026-November.txt": box})
    rc = mx.main([f"{a}/2026-November/000001.html", str(tmp_path / "o.mbox")])
    err = capsys.readouterr().err
    assert rc == 3
    assert "have [1] of 2" in err and "404" not in err


def test_write_mbox_keeps_utf8_body_bytes(tmp_path):
    raw = ("From: a at b.c (A B)\nSubject: [PATCH] a: x\nMessage-ID: <p>\n\n"
           "Fix the caf\u00e9 \u2013 thing\n\nSigned-off-by: J\u00f6rg <j at k.de>\n"
           + DIFF + "+\u00e9\n").encode()
    out = tmp_path / "s.mbox"
    mx.write_mbox([email.message_from_bytes(raw)], str(out))
    data = out.read_bytes()
    assert "caf\u00e9 \u2013 thing".encode() in data
    assert "Signed-off-by: J\u00f6rg <j@k.de>".encode() in data
    assert "+\u00e9\n".encode() in data
