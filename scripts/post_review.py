#!/usr/bin/env python3
"""Post a GitHub reply.md as a review on an fwts PR.

usage: post_review.py --pr N --commit SHA --verdict VERDICT [--repo O/R] [--dry-run] REPLY_MD

reply.md format: the review body, then an optional "### Inline comments"
section with one "path:line — comment" per line.  Verdict maps to the review
event: "Request changes" -> REQUEST_CHANGES, "Approve"/"Approve with nits" ->
APPROVE, anything else -> COMMENT.

If GitHub rejects the inline comments (line not in the diff), the review is
re-posted with them folded into the body.  If it rejects APPROVE or
REQUEST_CHANGES (e.g. on your own PR), it is re-posted as COMMENT.
Prints POSTED=<html_url> on success.
"""
import argparse
import json
import re
import subprocess
import sys

INLINE_HDR = re.compile(r"^#{2,4}\s*inline comments\s*$", re.I)
INLINE_LINE = re.compile(r"^\s*[-*]?\s*`?([^\s:`]+):(\d+)`?\s*(?:—|–|-{1,2})\s*(.+)$")


def parse_reply(text):
    body, inline, in_inline = [], [], False
    for ln in text.splitlines():
        if INLINE_HDR.match(ln):
            in_inline = True
            continue
        if in_inline:
            m = INLINE_LINE.match(ln)
            if m:
                inline.append({"path": m.group(1), "line": int(m.group(2)),
                               "side": "RIGHT", "body": m.group(3).strip()})
            elif ln.strip() and inline:
                inline[-1]["body"] += "\n" + ln.strip()
            continue
        body.append(ln)
    return "\n".join(body).strip(), inline


def event_for(verdict):
    v = verdict.strip().lower()
    if v.startswith("request"):
        return "REQUEST_CHANGES"
    if v.startswith("approve"):
        return "APPROVE"
    return "COMMENT"


def fold(body, inline):
    if not inline:
        return body
    lines = [f"- `{c['path']}:{c['line']}`: {c['body']}" for c in inline]
    return body + "\n\n**Inline comments**\n" + "\n".join(lines)


def payload(body, inline, event, commit):
    p = {"commit_id": commit, "event": event, "body": body}
    if inline:
        p["comments"] = inline
    return p


def post(repo, pr, p):
    r = subprocess.run(["gh", "api", "-X", "POST",
                        f"repos/{repo}/pulls/{pr}/reviews", "--input", "-"],
                       input=json.dumps(p), capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--pr", required=True, type=int)
    ap.add_argument("--commit", required=True)
    ap.add_argument("--verdict", required=True)
    ap.add_argument("--repo", default="fwts/fwts")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("reply")
    a = ap.parse_args(argv)

    with open(a.reply, encoding="utf-8") as f:
        body, inline = parse_reply(f.read())
    event = event_for(a.verdict)
    p = payload(body, inline, event, a.commit)
    if a.dry_run:
        print(json.dumps(p, indent=2, ensure_ascii=False))
        return 0

    attempts = [p]
    if inline:
        attempts.append(payload(fold(body, inline), [], event, a.commit))
    if event != "COMMENT":
        attempts.append(payload(fold(body, inline), [], "COMMENT", a.commit))
    for i, q in enumerate(attempts):
        rc, out = post(a.repo, a.pr, q)
        if rc == 0:
            url = json.loads(out).get("html_url", "") if out.strip().startswith("{") else ""
            if i:
                print(f"NOTE: posted as {q['event']}"
                      f"{' with inline comments folded into the body' if inline and not q.get('comments') else ''}",
                      file=sys.stderr)
            print(f"POSTED={url}")
            return 0
        print(f"attempt {i + 1} failed: {out.strip()[:400]}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
