"""Read lane: verbatim single-voice readings of Zotero "Read" collection items.

Separate from the two-voice interview pipeline. A Read episode is:
  1. extract  - pypdf body-text extraction (front matter / running heads /
                reference list / figure+table captions removed)
  2. script   - full-disclosure spoken intro + the body text verbatim
  3. render   - single-voice (host) chunked Edge TTS -> one mp3
  4. verify   - fidelity gate: every body word must survive into the script,
                and audio duration must match the word count
  5. notes    - show notes with the complete citation + Zotero link

Read episodes are numbered from 501 in the SAME feed as the interview episodes
and are registered in pipeline/read-episodes.json, which publish_feed.py reads.

Usage:
  read_lane.py extract --pdf PATH [--out TXT]
  read_lane.py build --episode 501 --item KEY [--pdf PATH]
  read_lane.py render --episode 501 [--force]
  read_lane.py verify --episode 501
  read_lane.py zotero-read          # list live Read collection items
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = "/data/.openclaw/workspace/vendor/two-voice-tts"
EPISODES = ROOT / "episodes"
READ_MANIFEST = ROOT / "pipeline" / "read-episodes.json"
STATE_PATH = ROOT / "pipeline" / "state.json"

ZOTERO_GROUP = "2412036"
READ_COLLECTION = "DV6F4ILX"
PRODUCED_COLLECTION = "6P2KVFKQ"
ZOTERO_KEY_FILE = ROOT / "check_zotero.py"

VOICE = "en-US-AvaMultilingualNeural"
RATE = "-3%"
TTS_CHUNK_CHARS = 1600
WORDS_PER_MINUTE = 150.0
FIRST_READ_NUMBER = 501


# --------------------------------------------------------------------------
# PDF body-text extraction
# --------------------------------------------------------------------------

REFERENCE_HEADINGS = re.compile(
    r"^\s*(references|bibliography|works\s+cited|reference\s+list|literature\s+cited)"
    r"\s*:?\s*$",
    re.I,
)
CAPTION = re.compile(
    r"^\s*(figure|fig\.?|table|tbl\.?|chart|exhibit|plate|scheme|algorithm|listing)"
    r"\s*\.?\s*\d+[a-z]?\s*[.:\u2014-]?",
    re.I,
)
PAGE_NUMBER = re.compile(r"^\s*(page\s*)?[\divxlcdm]{1,6}\s*$", re.I)
ACKNOWLEDGEMENT = re.compile(
    r"^\s*(acknowledg(e)?ments?|funding|conflicts?\s+of\s+interest|author\s+contributions|"
    r"declaration\s+of\s+(competing\s+)?interest|data\s+availability|supplementary\s+material|"
    r"appendix(\s+[a-z\d]+)?|orcid|about\s+the\s+authors?)\s*:?\s*$",
    re.I,
)
BODY_START = re.compile(
    r"^\s*(abstract|introduction|1\.?\s+introduction|background)\s*:?\s*$", re.I
)
HYPHEN_WRAP = re.compile(r"(\w+)-\n(\w+)")
URL_OR_DOI = re.compile(r"(https?://\S+|doi\.org/\S+|www\.\S+)", re.I)
ORCID = re.compile(r"orcid", re.I)


def dehyphenate(raw: str) -> str:
    """Rejoin words broken across a line, keeping genuine compound hyphens.

    A PDF line break turns both "measure-\nment" (one word) and "LLM-\nas-a-judge"
    (a real hyphen) into the same shape. Decide per candidate from evidence in
    the same document: if the closed form occurs elsewhere, close it; if the
    hyphenated form occurs elsewhere, keep the hyphen; otherwise keep the hyphen
    when the left fragment looks like an acronym or a complete word, since
    dropping a real hyphen corrupts the authors' text while an extra hyphen only
    affects how the TTS phrases it.
    """
    flat = re.sub(r"\s+", " ", raw)
    lower = flat.lower()

    def choose(match: re.Match) -> str:
        left, right = match.group(1), match.group(2)
        closed = f"{left}{right}"
        hyphenated = f"{left}-{right}"
        closed_seen = lower.count(closed.lower()) > 0
        hyphen_seen = lower.count(hyphenated.lower()) > 0
        if closed_seen and not hyphen_seen:
            return closed
        if hyphen_seen and not closed_seen:
            return hyphenated
        if left.isupper() or len(left) > 2 and left.lower() in COMMON_WORDS:
            return hyphenated
        return closed

    return HYPHEN_WRAP.sub(choose, raw)


# Small closed-class list: a left fragment that is itself one of these is almost
# certainly a compound's first element, not half of a split word.
COMMON_WORDS = {
    "self", "non", "pre", "post", "co", "cross", "multi", "high", "low", "well",
    "long", "short", "open", "closed", "data", "human", "machine", "large",
    "small", "real", "full", "semi", "sub", "inter", "intra", "meta", "re",
    "planned", "based", "driven", "centered", "oriented", "level", "scale",
    "world", "time", "state", "fine", "coarse", "rule", "end", "top", "bottom",
}

def extract_pages(pdf: Path) -> list[str]:
    try:
        import pypdf
    except ImportError:
        sys.path.insert(0, "/data/.openclaw/workspace/media/zotero-podcast/.venv-podcast/lib/python3.13/site-packages")
        import pypdf

    reader = pypdf.PdfReader(str(pdf))
    return [(page.extract_text() or "") for page in reader.pages]


def running_lines(pages: list[str], edge: int = 3) -> set[str]:
    """Lines repeated near the top/bottom of many pages = running head/foot."""
    counts: Counter[str] = Counter()
    for raw in pages:
        lines = [x.strip() for x in raw.splitlines() if x.strip()]
        for line in lines[:edge] + lines[-edge:]:
            counts[re.sub(r"\d+", "#", line)] += 1
    threshold = max(2, int(len(pages) * 0.4))
    return {key for key, n in counts.items() if n >= threshold and len(key) < 200}


def body_text(pdf: Path) -> dict:
    """Return body-only text plus an audit trail of what was dropped."""
    pages = extract_pages(pdf)
    if not pages:
        raise ValueError(f"no pages extracted from {pdf}")
    heads = running_lines(pages)
    raw = "\n\n".join(pages)
    raw = dehyphenate(raw)

    dropped = {
        "running_head_or_foot": 0,
        "page_number": 0,
        "caption": 0,
        "url_or_doi": 0,
        "orcid": 0,
        "after_references": 0,
        "back_matter": 0,
        "before_body": 0,
    }

    lines = raw.splitlines()
    # Locate the reference list: the LAST reference heading in the final 50%.
    cut = len(lines)
    for index in range(len(lines) - 1, int(len(lines) * 0.5), -1):
        if REFERENCE_HEADINGS.match(lines[index]):
            cut = index
            break
    dropped["after_references"] = len(lines) - cut
    lines = lines[:cut]

    # Locate the start of the body (abstract/introduction) to drop front matter.
    start = 0
    for index, line in enumerate(lines[: max(1, int(len(lines) * 0.35))]):
        if BODY_START.match(line):
            start = index
            break
    dropped["before_body"] = start
    lines = lines[start:]

    kept: list[str] = []
    in_back_matter = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            kept.append("")
            continue
        if ACKNOWLEDGEMENT.match(stripped):
            in_back_matter = True
        if in_back_matter:
            dropped["back_matter"] += 1
            continue
        if re.sub(r"\d+", "#", stripped) in heads:
            dropped["running_head_or_foot"] += 1
            continue
        if PAGE_NUMBER.match(stripped):
            dropped["page_number"] += 1
            continue
        if CAPTION.match(stripped):
            dropped["caption"] += 1
            continue
        if ORCID.search(stripped):
            dropped["orcid"] += 1
            continue
        if URL_OR_DOI.search(stripped):
            dropped["url_or_doi"] += 1
            continue
        kept.append(stripped)

    # Re-flow into paragraphs: a line ending mid-sentence continues.
    paragraphs: list[str] = []
    buffer: list[str] = []
    for line in kept:
        if not line:
            if buffer:
                paragraphs.append(" ".join(buffer))
                buffer = []
            continue
        buffer.append(line)
        if re.search(r"[.!?][\"')\]]?$", line) and len(line) < 70:
            paragraphs.append(" ".join(buffer))
            buffer = []
    if buffer:
        paragraphs.append(" ".join(buffer))

    text = "\n\n".join(p.strip() for p in paragraphs if p.strip())
    text = re.sub(r"[ \t]{2,}", " ", text)
    return {
        "text": text,
        "pages": len(pages),
        "words": len(text.split()),
        "dropped_lines": dropped,
    }


# --------------------------------------------------------------------------
# Zotero
# --------------------------------------------------------------------------

def zotero_key() -> str:
    env = os.environ.get("ZOTERO_API_KEY")
    if env:
        return env
    match = re.search(r'key\s*=\s*"([^"]+)"', ZOTERO_KEY_FILE.read_text())
    if not match:
        raise RuntimeError("no Zotero API key found")
    return match.group(1)


def zotero_get(path: str) -> tuple[object, dict]:
    url = f"https://api.zotero.org/groups/{ZOTERO_GROUP}/{path}"
    request = urllib.request.Request(url)
    request.add_header("Zotero-API-Key", zotero_key())
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.loads(response.read()), dict(response.headers)


def read_collection_items() -> list[dict]:
    data, _ = zotero_get(f"collections/{READ_COLLECTION}/items/top?format=json&limit=100")
    return data if isinstance(data, list) else []


def full_citation(item: dict) -> str:
    """Complete citation: every author, full title, venue, year. No et al."""
    data = item.get("data", item)
    names = []
    for creator in data.get("creators", []):
        if creator.get("creatorType") not in ("author", "editor", None):
            continue
        if creator.get("name"):
            names.append(creator["name"])
        else:
            first = creator.get("firstName", "").strip()
            last = creator.get("lastName", "").strip()
            names.append(f"{first} {last}".strip())
    if len(names) > 1:
        authors = ", ".join(names[:-1]) + ", and " + names[-1]
    else:
        authors = names[0] if names else "Author not recorded in Zotero"
    venue = (
        data.get("publicationTitle")
        or data.get("proceedingsTitle")
        or data.get("bookTitle")
        or data.get("publisher")
        or data.get("repository")
        or "venue not recorded in Zotero"
    )
    year = (re.search(r"\b(19|20)\d{2}\b", data.get("date", "")) or [None])
    year = year.group(0) if hasattr(year, "group") else "year not recorded in Zotero"
    return f"{authors}. \"{data.get('title', 'Untitled')}.\" {venue}, {year}."


# --------------------------------------------------------------------------
# Script
# --------------------------------------------------------------------------

DISCLOSURE = (
    "This is Moral Machines, reading number {number}. "
    "What follows is a complete verbatim reading of the body text of the following work. {citation} "
    "Three things before we start. "
    "First, this is an automated text-to-speech reading, not a summary and not an interview; "
    "no human reviewed this audio before it was published. "
    "Second, the reading covers the body text only. Front matter, running heads, figures, tables, "
    "their captions, equations, acknowledgements, and the reference list are not read, and figure and "
    "table content is not described, so any argument that depends on seeing them will be incomplete here. "
    "Third, text extracted from a PDF can garble symbols, so treat anything that sounds wrong as an "
    "extraction artifact rather than the authors' words, and check the original. "
    "The complete citations are in the show notes, with links to the Zotero files when you have been "
    "granted access. Here is the work."
)

OUTRO = (
    "That is the end of the reading. Again, that was {citation} "
    "The complete citations are in the show notes, with links to the Zotero files when you have been "
    "granted access."
)


def build_script(number: str, citation: str, text: str) -> str:
    intro = DISCLOSURE.format(number=number.lstrip("0"), citation=citation)
    outro = OUTRO.format(citation=citation)
    lines = [
        f"# Reading {number}",
        "",
        "<!-- Read lane: single voice, verbatim body text. Do not paraphrase or edit the",
        "     READING block; the fidelity gate compares it word-for-word with source.txt. -->",
        "",
        f"**Reader:** {intro}",
        "",
        "<!-- BEGIN READING -->",
    ]
    for paragraph in text.split("\n\n"):
        paragraph = paragraph.strip()
        if paragraph:
            lines += [f"**Reader:** {paragraph}", ""]
    lines += ["<!-- END READING -->", "", f"**Reader:** {outro}", ""]
    return "\n".join(lines)


def script_turns(script: Path) -> list[str]:
    turns = []
    for line in script.read_text().splitlines():
        match = re.match(r"^\*\*Reader:\*\*\s+(.+)$", line)
        if match:
            turns.append(match.group(1).strip())
    if not turns:
        raise ValueError(f"no **Reader:** turns in {script}")
    return turns


def spoken_text(text: str) -> str:
    return text.replace("*", "").replace("`", "").replace("_", " ")


def chunk(text: str, limit: int = TTS_CHUNK_CHARS) -> list[str]:
    """Split a long paragraph on sentence boundaries for TTS stability."""
    if len(text) <= limit:
        return [text]
    sentences = re.split(r"(?<=[.!?])\s+", text)
    out: list[str] = []
    current = ""
    for sentence in sentences:
        while len(sentence) > limit:
            out.append(sentence[:limit])
            sentence = sentence[limit:]
        if len(current) + len(sentence) + 1 <= limit:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                out.append(current)
            current = sentence
    if current:
        out.append(current)
    return out


# --------------------------------------------------------------------------
# Render
# --------------------------------------------------------------------------

def tts_imports():
    sys.path.insert(0, VENDOR)
    import edge_tts
    import imageio_ffmpeg

    return edge_tts, imageio_ffmpeg


async def synthesize(edge_tts, path: Path, text: str) -> None:
    for attempt in range(5):
        try:
            await edge_tts.Communicate(spoken_text(text), VOICE, rate=RATE).save(str(path))
            if path.stat().st_size > 500:
                return
            raise RuntimeError(f"suspiciously small part: {path.stat().st_size} bytes")
        except Exception:
            if attempt == 4:
                raise
            await asyncio.sleep(2 + 2 * attempt)


async def render_episode(number: str, force: bool = False) -> dict:
    edge_tts, imageio_ffmpeg = tts_imports()
    directory = EPISODES / number
    script = directory / "script.md"
    parts = directory / "parts-read"
    parts.mkdir(parents=True, exist_ok=True)
    output = directory / f"episode-{number}.mp3"

    pieces: list[str] = []
    for turn in script_turns(script):
        pieces.extend(chunk(turn))

    files = []
    for index, piece in enumerate(pieces):
        part = parts / f"{index:05d}.mp3"
        if force or not part.exists() or part.stat().st_size < 500:
            await synthesize(edge_tts, part, piece)
        files.append(part)
        if index % 25 == 0:
            print(f"  tts {index}/{len(pieces)}", flush=True)

    concat = parts / "concat.txt"
    concat.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in files))
    subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat), "-c:a", "libmp3lame", "-b:a", "96k", str(output),
        ],
        check=True,
        capture_output=True,
    )
    return {"episode": number, "parts": len(files), "audio": str(output),
            "bytes": output.stat().st_size}


def audio_seconds(path: Path) -> float:
    _, imageio_ffmpeg = tts_imports()
    stderr = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-i", str(path)],
        capture_output=True, text=True,
    ).stderr
    match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", stderr)
    if not match:
        return 0.0
    return int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3))


# --------------------------------------------------------------------------
# Fidelity gate
# --------------------------------------------------------------------------

def normalize_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def verify(number: str) -> dict:
    directory = EPISODES / number
    source = (directory / "source.txt").read_text()
    script = (directory / "script.md").read_text()

    reading = re.search(
        r"<!-- BEGIN READING -->(.*?)<!-- END READING -->", script, re.S
    )
    if not reading:
        return {"ok": False, "issues": ["script is missing the READING block"]}
    spoken = " ".join(
        re.sub(r"^\*\*Reader:\*\*\s+", "", line)
        for line in reading.group(1).splitlines()
        if line.startswith("**Reader:**")
    )

    source_words = normalize_words(source)
    spoken_words = normalize_words(spoken)
    coverage = len(spoken_words) / len(source_words) if source_words else 0.0

    issues = []
    if coverage < 0.995:
        issues.append(
            f"reading covers {coverage:.3%} of source words "
            f"({len(spoken_words)}/{len(source_words)}) — words were dropped"
        )
    if len(spoken_words) > len(source_words) * 1.005:
        issues.append(
            f"reading has {len(spoken_words) - len(source_words)} more words than the "
            "source — text was added"
        )
    # Order check: the reading must be the source sequence, not a reshuffle.
    if source_words and spoken_words[: len(source_words)] != source_words[: len(spoken_words)]:
        first_diff = next(
            (i for i, (a, b) in enumerate(zip(source_words, spoken_words)) if a != b),
            None,
        )
        if first_diff is not None:
            issues.append(
                f"reading diverges from source at word {first_diff}: "
                f"source={source_words[first_diff]!r} script={spoken_words[first_diff]!r}"
            )

    # The rendered audio is intro + reading + outro, so the duration baseline
    # must use every spoken turn, not just the reading block.
    all_spoken = " ".join(script_turns(directory / "script.md"))
    audio_words = len(normalize_words(all_spoken))

    audio = directory / f"episode-{number}.mp3"
    duration = None
    if audio.exists():
        duration = audio_seconds(audio)
        expected = audio_words / WORDS_PER_MINUTE * 60
        if expected and not (0.65 * expected <= duration <= 1.45 * expected):
            issues.append(
                f"audio is {duration:.0f}s but {audio_words} spoken words should take "
                f"about {expected:.0f}s — audio may be truncated or padded"
            )
    else:
        issues.append("no audio rendered yet")

    return {
        "ok": not issues,
        "episode": number,
        "source_words": len(source_words),
        "spoken_words": len(spoken_words),
        "audio_words": audio_words,
        "coverage": round(coverage, 5),
        "audio_seconds": round(duration, 1) if duration else None,
        "issues": issues,
    }


# --------------------------------------------------------------------------
# Notes + manifest
# --------------------------------------------------------------------------

NOTES_TEMPLATE = """# Reading {number} — {title}

Verbatim single-voice reading. Not an interview, not a summary.

## What this audio is

This episode is a complete automated text-to-speech reading of the **body text**
of the work cited below. No human reviewed the audio before publication. The
reading was produced by extracting text from the PDF held in Zotero and sending
it to a synthetic voice unchanged; the reading is checked word-for-word against
the extracted text by an automated fidelity gate before publishing.

## What is not in the audio

- Front matter (title block, author affiliations, ORCID lines, journal furniture)
- Running heads and footers, page numbers
- Figures, tables, and their captions — and no description of them is substituted
- Equations and other non-textual content, which text extraction may garble
- Acknowledgements, funding statements, appendices, and the reference list
- Any argument that depends on seeing a figure or table will be incomplete here

PDF text extraction is imperfect. If a passage sounds wrong, treat it as an
extraction artifact rather than the authors' words and consult the original.

## Source

1. {citation} Zotero item: {zotero_link}{public_link}

The complete citations are in these show notes, with links to the Zotero files
when you have been granted access.

## Production record

- Zotero item key: `{item_key}`
- Source PDF SHA-256: `{sha}`
- Extracted body text: {source_words} words from {pages} PDF pages
- Fidelity gate: {coverage} of extracted words present in the reading, in order
- Rendered: {rendered} ({voice})
"""


def write_notes(number: str, item: dict, citation: str, extraction: dict,
                sha: str, verification: dict) -> Path:
    data = item.get("data", item)
    key = item.get("key", data.get("key", "unknown"))
    public = data.get("DOI") or data.get("url") or ""
    public_link = f" Public link: {public}" if public else ""
    notes = NOTES_TEMPLATE.format(
        number=number,
        title=data.get("title", "Untitled"),
        citation=citation,
        zotero_link=f"https://www.zotero.org/groups/{ZOTERO_GROUP}/items/{key}",
        public_link=public_link,
        item_key=key,
        sha=sha,
        source_words=extraction["words"],
        pages=extraction["pages"],
        coverage=f"{verification.get('coverage', 0):.3%}",
        rendered=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        voice=VOICE,
    )
    path = EPISODES / number / "episode-notes.md"
    path.write_text(notes)
    return path


def load_read_manifest() -> dict:
    if READ_MANIFEST.exists():
        return json.loads(READ_MANIFEST.read_text())
    return {"schema_version": 1, "episodes": {}}


def save_read_manifest(manifest: dict) -> None:
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    fd, name = tempfile.mkstemp(dir=str(READ_MANIFEST.parent), text=True)
    with os.fdopen(fd, "w") as handle:
        json.dump(manifest, handle, indent=1, sort_keys=True)
    os.replace(name, READ_MANIFEST)


def register(number: str, item: dict, citation: str, extraction: dict,
             verification: dict) -> None:
    data = item.get("data", item)
    manifest = load_read_manifest()
    manifest.setdefault("episodes", {})[number] = {
        "number": number,
        "kind": "read",
        "title": data.get("title", "Untitled"),
        "item_key": item.get("key", ""),
        "citation": citation,
        "audio": f"episode-{number}.mp3",
        "base": f"episode-{number}-reading",
        "guid": f"episode-{number}-reading-{item.get('key','')}",
        "source_words": extraction["words"],
        "pages": extraction["pages"],
        "coverage": verification.get("coverage"),
        "verified": verification.get("ok", False),
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    save_read_manifest(manifest)


def next_number() -> str:
    manifest = load_read_manifest()
    used = [int(x) for x in manifest.get("episodes", {})]
    return str(max(used) + 1 if used else FIRST_READ_NUMBER)


def sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------

def build(number: str | None, item_key: str, pdf: Path | None) -> dict:
    items = {x["key"]: x for x in read_collection_items()}
    item = items.get(item_key)
    if item is None:
        data, _ = zotero_get(f"items/{item_key}?format=json")
        item = data
    citation = full_citation(item)
    number = number or next_number()
    directory = EPISODES / number
    directory.mkdir(parents=True, exist_ok=True)

    if pdf is None:
        raise SystemExit(
            "no --pdf given: download the Zotero attachment first "
            "(read_lane.py cannot yet pull attachments)"
        )
    target = directory / f"source-{item_key}.pdf"
    if Path(pdf).resolve() != target.resolve():
        target.write_bytes(Path(pdf).read_bytes())

    extraction = body_text(target)
    (directory / "source.txt").write_text(extraction["text"])
    (directory / "extraction-report.json").write_text(
        json.dumps({k: v for k, v in extraction.items() if k != "text"}, indent=1)
    )
    (directory / "script.md").write_text(
        build_script(number, citation, extraction["text"])
    )
    verification = verify(number)
    write_notes(number, item, citation, extraction, sha256(target), verification)
    register(number, item, citation, extraction, verification)
    return {
        "episode": number,
        "citation": citation,
        "extraction": {k: v for k, v in extraction.items() if k != "text"},
        "verify": verification,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("extract")
    p.add_argument("--pdf", type=Path, required=True)
    p.add_argument("--out", type=Path)

    p = sub.add_parser("build")
    p.add_argument("--episode")
    p.add_argument("--item", required=True)
    p.add_argument("--pdf", type=Path)

    p = sub.add_parser("render")
    p.add_argument("--episode", required=True)
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("verify")
    p.add_argument("--episode", required=True)

    sub.add_parser("zotero-read")
    sub.add_parser("next-number")

    args = parser.parse_args(argv)

    if args.cmd == "extract":
        result = body_text(args.pdf)
        if args.out:
            args.out.write_text(result["text"])
        print(json.dumps({k: v for k, v in result.items() if k != "text"}, indent=1))
        if not args.out:
            print(result["text"][:2000])
    elif args.cmd == "build":
        print(json.dumps(build(args.episode, args.item, args.pdf), indent=1))
    elif args.cmd == "render":
        print(json.dumps(asyncio.run(render_episode(args.episode, args.force)), indent=1))
    elif args.cmd == "verify":
        result = verify(args.episode)
        print(json.dumps(result, indent=1))
        return 0 if result["ok"] else 1
    elif args.cmd == "zotero-read":
        for item in read_collection_items():
            data = item["data"]
            print(item["key"], data.get("itemType"), "|", full_citation(item))
    elif args.cmd == "next-number":
        print(next_number())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
