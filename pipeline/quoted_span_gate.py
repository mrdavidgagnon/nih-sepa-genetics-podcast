#!/usr/bin/env python3
"""Quoted-span fidelity gate: every quoted span in a deliverable must appear in the source.

Run BEFORE writing script.md (the install step), not after. Run 482 caught three
real defects in one pass this way -- a garbled bibliographic title, a digit/word
title mismatch, and a genuinely invented quotation attributed to a system prompt
-- all of which two prior rounds of citation and editorial review had missed.

The discriminating count for the invented-quotation class is source 0 with
script >= 1: a quoted string absent from the source text.

NORMALIZATION (all four views are required, and they apply to the PROBE TOO)
---------------------------------------------------------------------------
PDF extraction wraps lines, so a naive comparison false-fails on its own:

  raw                 unmodified source
  collapsed           measure-\n ment  -> measurement   (hyphen at linebreak closed)
  nolb                Game-\n Based    -> Game-Based    (hyphen kept, linebreak dropped)
  whitespace          every run of whitespace -> one space
  alnum               drop every non-alphanumeric character (final fallback)

`retained` (the regex that rewrites a word-hyphen-newline-word run to keep the
hyphen) is kept for clarity but is REDUNDANT: `nolb` is a strict superset of it,
so it fixes nothing nolb has not already fixed.

The `alnum` view exists because PDF extraction inserts SPURIOUS INTRA-WORD
SPACES, and no hyphen view and no whitespace collapse can close a space that
sits inside a word. Run 488 measured this against three real published
episodes: the 048 source text contains "human e motions", "cognitiv e tasks",
"f eedback" and "e motion scales", which made six correctly-quoted reference
titles report source 0. That is a checker bug that reads exactly like six
fabricated citations -- the most dangerous false-positive shape this gate has.

`alnum` does not weaken detection. Dropping or inventing WORDS still fails,
because the intervening characters survive the fold: the run-474 class
("when intentionally designed" for "when it is intentionally designed") and an
outright invented sentence are both still caught.

Without `retained`, the real title "Foundations of Game-Based Learning" reports
MISSING (run 482). Without `whitespace` applied to BOTH the view and the probe,
a journal title printed verbatim but line-wrapped between whole words reports
MISSING (run 483) -- the three hyphen views all key on `-\n` and none of them
closes a plain newline between words.

Casefold before concluding a quotation is invented: run 484 false-flagged
"find a promising sector" because the source prints it list-initial as
"(1) Find a promising sector".

BENIGN CLASSES (expected source-0 hits; not the blocking class)
---------------------------------------------------------------
Pass --whitelist to name them explicitly rather than loosening the assertion:
  * regex-captured trailing punctuation
  * bibliographic titles the notes quote in their own reference list where the
    source prints them unquoted
  * the notes quoting their own editorial shorthand ("paper only") or
    source-type labels ("German healthcare report") that describe the episode's
    own speech, not the authors' wording
  * SCARE-QUOTED OWN-SPEECH -- the largest class in the back catalogue. The
    house style states a position by quoting what it is not ("The headline is
    not \"this model is unfair.\"") or names a phrase as the correspondent's
    own ("an average is a place to hide"). Correctly attributed in the script,
    and supposed to be absent from the source.
  * a spoken number rendered as words ("thirty-six of fifty") where the source
    prints digits ("36 of the 50 skills")
  * the SOURCE PAPER'S OWN TITLE, which extraction strips as front matter, so
    an episode naming the paper it is about cannot match

Only an AUTHOR-ATTRIBUTED span with source 0 is the blocking class. Read the
~200 characters before the span: if the turn attributes it to an author or to
the paper, source 0 is blocking; if the episode is quoting itself, a position
it rejects, or a number it is reading aloud, it is not.

USAGE
-----
  python3 pipeline/quoted_span_gate.py --source episodes/049/source-KEY.txt \
      [--source episodes/NNN/source-OTHER.txt ...] \
      --check episodes/049/script.md --check episodes/049/episode-notes.md

Exit 0 = every quoted span verified. Exit 1 = at least one unverified span.
Always match each deliverable against the SOURCE, never against the other
deliverable -- run 474's defect was the notes dropping two words inside
quotation marks while the script had it right, which a script-vs-notes
comparison cannot see.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

WS = lambda t: re.sub(r"\s+", " ", t)


def normalize_quotes(text: str) -> str:
    """Fold smart quotes and dashes so a curly-quoted source matches a straight probe."""
    return (text.replace("\u201c", '"').replace("\u201d", '"')
                .replace("\u2018", "'").replace("\u2019", "'")
                .replace("\u2014", "-").replace("\u2013", "-"))


def source_views(text: str) -> list[str]:
    """The four normalizations. Fewer than four makes the checker false-fail."""
    raw = text
    collapsed = re.sub(r"(\w)-\n(\w)", r"\1\2", text)   # measure-\nment -> measurement
    retained = re.sub(r"(\w)-\n(\w)", r"\1-\2", text)   # Game-\nBased -> Game-Based
    nolb = text.replace("-\n", "-")
    return [raw, collapsed, retained, nolb]


def alnum_only(text: str) -> str:
    """Drop every non-alphanumeric character.

    The final fallback view. Closes spurious intra-word spaces from PDF
    extraction ("cognitiv e tasks"), every hyphen-wrap form, and punctuation
    drift at once. Must be applied to the probe as well as the haystack.
    """
    return re.sub(r"[^a-z0-9]", "", normalize_quotes(text).casefold())


def build_haystacks(source_text: str) -> list[str]:
    """Every view, quote-folded, whitespace-collapsed and casefolded."""
    views = [normalize_quotes(v) for v in source_views(source_text)]
    return [WS(v).casefold() for v in views]


def extract_spans(text: str) -> list[str]:
    """Quoted spans of 4+ chars that do not cross a line break."""
    return re.findall(r'"([^"\n]{4,})"', normalize_quotes(text))


def probe_of(span: str) -> str:
    """Normalize a probe the SAME WAY as the haystack, or it false-fails (run 483)."""
    return WS(span.strip().strip(".,;:!?")).casefold()


def verify_text(source_text: str, text: str,
                whitelist: list[str] | None = None) -> dict:
    haystacks = build_haystacks(source_text)
    alnum_hay = alnum_only(source_text)
    allow = {probe_of(w) for w in (whitelist or [])}
    spans = extract_spans(text)
    unverified = []
    for span in spans:
        probe = probe_of(span)
        if probe in allow:
            continue
        if any(probe in hay for hay in haystacks):
            continue
        # Final fallback: PDF extraction artefacts inside words.
        if alnum_only(span.strip().strip(".,;:!?")) in alnum_hay:
            continue
        unverified.append(span)
    return {
        "spans": len(spans),
        "unverified": unverified,
        "ok": not unverified,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Assert every quoted span in each deliverable appears in the source.")
    ap.add_argument("--source", action="append", required=True, metavar="FILE",
                    help="extracted source text (episodes/NNN/source-KEY.txt); "
                         "repeat for an episode with several sources")
    ap.add_argument("--check", action="append", required=True, metavar="FILE",
                    help="deliverable to scan; repeat for script.md and episode-notes.md")
    ap.add_argument("--whitelist", action="append", default=[], metavar="SPAN",
                    help="a known-benign span (own apparatus / reference-list title)")
    args = ap.parse_args(argv)

    # An episode can group several papers (001 has five, 002 has four), so a
    # span is verified if it appears in ANY of them. Each source is scored
    # INDEPENDENTLY and the residual sets are intersected -- the same semantics
    # preflight() uses on the publish path, so the operator-facing command and
    # the publication gate agree by construction rather than by coincidence.
    #
    # Do NOT concatenate the sources into one haystack. A span that straddles
    # the boundary between two joined papers matches the JOIN while existing in
    # no single paper: on episode 001's real extracts, "Child Study 6d MIT Open
    # Access" spans the tail of source-4UDPRQZR and the head of
    # source-BGWWIUWC, verifies against the concatenation, and verifies against
    # none of the five sources alone. That is a quiet weakening of the gate.
    #
    # Before run 052 this argument was a plain store, so a repeated --source was
    # SILENTLY discarded down to the last path with no warning and no usage
    # error: the operator saw a confident verdict scored against one paper, and
    # every span quoted from the others reported SOURCE 0 -- indistinguishable
    # from a fabricated quotation, the most dangerous false positive this gate
    # has.
    source_texts = [Path(p).read_text(encoding="utf-8", errors="replace")
                    for p in args.source]
    report = {"sources": list(args.source), "files": {}, "ok": True}
    for target in args.check:
        text = Path(target).read_text(encoding="utf-8", errors="replace")
        residual = None
        spans = 0
        for source_text in source_texts:
            scored = verify_text(source_text, text, args.whitelist)
            spans = scored["spans"]
            missing = set(scored["unverified"])
            residual = missing if residual is None else (residual & missing)
        unverified = sorted(residual or set())
        result = {"spans": spans, "unverified": unverified,
                  "ok": not unverified, "sources_scored": len(source_texts)}
        report["files"][target] = result
        report["ok"] = report["ok"] and result["ok"]

    for name, result in report["files"].items():
        print(f"{name}: spans={result['spans']} unverified={len(result['unverified'])}")
        for span in result["unverified"]:
            print(f"  SOURCE 0: {span[:200]}")
    print(f"ok={report['ok']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
