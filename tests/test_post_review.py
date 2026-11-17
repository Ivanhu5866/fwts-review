import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import post_review as pr  # noqa: E402

REPLY = """Thanks for the patch.

1. **Crash** (`mcfg.c:658`): fix it.

### Inline comments
src/brs-i/mcfg/mcfg.c:658 — `table` may be NULL here.
- `src/a.c:12` -- second comment
  continued here.
"""


def test_parse_reply_splits_body_and_inline():
    body, inline = pr.parse_reply(REPLY)
    assert body.endswith("fix it.")
    assert "Inline comments" not in body
    assert inline == [
        {"path": "src/brs-i/mcfg/mcfg.c", "line": 658, "side": "RIGHT",
         "body": "`table` may be NULL here."},
        {"path": "src/a.c", "line": 12, "side": "RIGHT",
         "body": "second comment\ncontinued here."},
    ]


def test_parse_reply_without_inline_section():
    body, inline = pr.parse_reply("LGTM\n")
    assert body == "LGTM" and inline == []


def test_event_for_verdicts():
    assert pr.event_for("Request changes") == "REQUEST_CHANGES"
    assert pr.event_for("Approve with nits") == "APPROVE"
    assert pr.event_for("Approve") == "APPROVE"
    assert pr.event_for("Comment") == "COMMENT"


def test_fallbacks_fold_inline_then_comment(monkeypatch, tmp_path):
    f = tmp_path / "reply.md"
    f.write_text(REPLY)
    sent = []

    def fake_post(repo, n, p):
        sent.append(p)
        if len(sent) < 3:
            return 1, "HTTP 422"
        return 0, json.dumps({"html_url": "https://x/1"})

    monkeypatch.setattr(pr, "post", fake_post)
    assert pr.main(["--pr", "48", "--commit", "abc", "--verdict",
                    "Request changes", str(f)]) == 0
    assert [s["event"] for s in sent] == ["REQUEST_CHANGES", "REQUEST_CHANGES", "COMMENT"]
    assert "comments" in sent[0] and "comments" not in sent[1]
    assert "`src/a.c:12`: second comment" in sent[1]["body"]
