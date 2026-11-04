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
