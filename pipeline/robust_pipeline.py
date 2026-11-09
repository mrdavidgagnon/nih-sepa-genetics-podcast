#!/usr/bin/env python3
"""Safe, resumable podcast production workflow.

The command line interface deliberately uses only the Python standard library.
It is designed to make the existing episode files inspectable and to keep
network publication outside the rendering step.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent
PIPELINE = ROOT / "pipeline"
LEDGER_PATH = PIPELINE / "state.json"
INVENTORY_PATH = PIPELINE / "inventory.json"
LOCK_PATH = PIPELINE / ".pipeline.lock"
MANIFEST_PATH = PIPELINE / "manifest.json"
FEED_BASE = "https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast"
DEPLOY_REPO = "https://github.com/mrdavidgagnon/nih-sepa-genetics-podcast"
DEPLOY_ENV_FILE = Path("/opt/data/.env")
DEPLOY_GIT_USER = "Hermes (Agent)"
DEPLOY_GIT_EMAIL = "hermes@mrdavidgagnon.github.io"
REQUIRED_DISCLOSURE = "The complete citations are in the show notes, with links to the Zotero files when you have been granted access."
ROLES = {"host", "rowan", "guest"}
MAX_RETRIES = 4
RENDER_TEXT_VERSION = 2

STATES = {
    "planned", "review_pending", "reviewed", "rendering", "rendered",
    "verified", "published", "blocked", "failed",
}
TRANSITIONS = {
    "planned": {"review_pending", "blocked"},
    "review_pending": {"reviewed", "blocked"},
    "reviewed": {"rendering", "blocked"},
    "rendering": {"rendered", "failed", "blocked"},
    "rendered": {"verified", "rendering", "blocked"},
    "verified": {"published", "rendering", "blocked"},
    "published": {"rendering"},
    "blocked": {"review_pending", "planned"},
    "failed": {"rendering", "planned"},
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def atomic_write(path: Path, content: str | bytes) -> None:
    """Write and fsync a file, then replace it so readers never see a half file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content.encode() if isinstance(content, str) else content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(name)


def atomic_json(path: Path, value: Any) -> None:
    atomic_write(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


class PipelineLock:
    """Exclusive process lock with an inspectable owner record.

    A lock is never silently broken: stale locks require an explicit
    ``unlock --force`` after a human has checked the owner record.
    """
    def __init__(self, path: Path = LOCK_PATH, timeout: float = 0.0):
        self.path, self.timeout, self.fd = path, timeout, None

    def __enter__(self):
        import fcntl
        self.path.parent.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        while True:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                owner = {"pid": os.getpid(), "host": socket.gethostname(), "started_at": utc_now(), "command": " ".join(sys.argv)}
                os.ftruncate(self.fd, 0)
                os.write(self.fd, json.dumps(owner).encode())
                os.fsync(self.fd)
                return self
            except BlockingIOError:
                if time.monotonic() - started >= self.timeout:
                    os.close(self.fd)
                    self.fd = None
                    raise RuntimeError(f"pipeline lock is held: {self.path}")
                time.sleep(0.05)

    def __exit__(self, *_):
        import fcntl
        if self.fd is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
            self.fd = None


def unlock(force: bool = False) -> None:
    """Remove a lock record only when explicitly requested."""
    if not LOCK_PATH.exists():
        return
    if not force:
        raise RuntimeError("refusing to remove lock; use unlock --force after checking its owner")
    import fcntl
    fd = os.open(LOCK_PATH, os.O_RDWR)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("lock is currently held; refusing to remove an active lock")
        os.unlink(LOCK_PATH)
    finally:
        os.close(fd)


def lock_status(path: Path = LOCK_PATH) -> dict[str, Any]:
    """Report whether the persistent lock record is actively held."""
    if not path.exists():
        return {"present": False, "active": False}
    owner = {}
    with contextlib.suppress(Exception):
        owner = json.loads(path.read_text() or "{}")
    import fcntl
    fd = os.open(path, os.O_RDWR)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            active = False
            fcntl.flock(fd, fcntl.LOCK_UN)
        except BlockingIOError:
            active = True
    finally:
        os.close(fd)
    return {"present": True, "active": active, "owner": owner}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text())


def load_ledger() -> dict[str, Any]:
    if LEDGER_PATH.exists():
        data = json.loads(LEDGER_PATH.read_text())
        if data.get("schema_version") != 1:
            raise ValueError("unsupported pipeline state schema")
        return data
    manifest = load_manifest()
    episodes = {}
    for number, item in manifest.get("episodes", {}).items():
        manifest_status = str(item.get("status", ""))
        imported_status = "published" if manifest_status == "published_and_moved" else ("verified" if manifest_status.startswith("published_") else "planned")
        episodes[number] = {
            "status": imported_status,
            "sources": item.get("sources", []), "attempts": 0,
            "transitions": [{"from": None, "to": imported_status, "at": utc_now(), "reason": "imported from manifest"}],
            "checks": {}, "artifacts": {}, "errors": [],
        }
    return {"schema_version": 1, "pipeline": manifest.get("pipeline", "podcast"), "updated_at": utc_now(), "episodes": episodes}


def save_ledger(ledger: dict[str, Any]) -> None:
    ledger["updated_at"] = utc_now()
    atomic_json(LEDGER_PATH, ledger)


def transition(ledger: dict[str, Any], episode: str, to_state: str, reason: str = "") -> None:
    if to_state not in STATES:
        raise ValueError(f"unknown state: {to_state}")
    record = ledger.setdefault("episodes", {}).setdefault(episode, {"status": "planned", "transitions": []})
    old = record.get("status", "planned")
    if old != to_state and to_state not in TRANSITIONS.get(old, set()):
        raise ValueError(f"invalid state transition {episode}: {old} -> {to_state}")
    record["status"] = to_state
    record.setdefault("transitions", []).append({"from": old, "to": to_state, "at": utc_now(), "reason": reason})


# --- production attempts -----------------------------------------------------
#
# Episode state alone cannot describe a long-running production run. An agent
# turn can research sources, draft a script and fail after twenty minutes while
# the episode is still `planned`, so ten consecutive failures left `attempts: 0`
# and no record of how far any of them got. The unit of work therefore gets its
# own durable record, written as it goes rather than at the end.

# Outcomes are deliberately distinct: a watchdog that cannot tell a deliberate
# stop from a crash will either relaunch finished work or ignore dead work.
ATTEMPT_OUTCOMES = {"completed", "failed", "stopped"}
DERIVED_OUTCOMES = {"timed_out", "stalled", "running"}
# How long an attempt may go without a checkpoint before it is presumed dead.
DEFAULT_STALL_SECONDS = 900


def _episode_record(ledger: dict[str, Any], episode: str) -> dict[str, Any]:
    return ledger.setdefault("episodes", {}).setdefault(
        episode, {"status": "planned", "transitions": []}
    )


def classify_attempt(attempt: dict[str, Any], now: datetime,
                     stall_seconds: int = DEFAULT_STALL_SECONDS) -> str:
    """Name the state of one attempt without mutating it.

    Pure so the rules can be tested directly. A finished attempt keeps the
    outcome it recorded; an unfinished one is judged against its own budget and
    its last checkpoint, never against unrelated ledger activity.
    """
    outcome = attempt.get("outcome")
    if outcome:
        return str(outcome)
    deadline = attempt.get("deadline_at")
    if deadline and now > _parse_iso(deadline):
        return "timed_out"
    marks = attempt.get("checkpoints") or []
    last_at = marks[-1]["at"] if marks else attempt.get("started_at")
    if last_at and (now - _parse_iso(last_at)).total_seconds() > stall_seconds:
        return "stalled"
    return "running"


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _open_attempt(record: dict[str, Any]) -> dict[str, Any] | None:
    for attempt in reversed(record.get("attempt_log") or []):
        if not attempt.get("outcome"):
            return attempt
    return None


def start_attempt(episode: str, budget_seconds: int, run_id: str = "",
                  stage: str = "started") -> dict[str, Any]:
    """Open a durable record for one production unit, with its whole-unit budget.

    The budget covers the complete unit including finalisation, not a single
    iteration: sizing a timeout against one pass is what killed a run that had
    already done the work but had not yet written it.
    """
    now = datetime.now(timezone.utc)
    with PipelineLock(timeout=0):
        ledger = load_ledger()
        record = _episode_record(ledger, episode)
        existing = _open_attempt(record)
        if existing:
            # Never silently start a second attempt beside a live one; that is
            # how duplicate workers appear.
            existing["outcome"] = "stopped"
            existing["finished_at"] = now.isoformat().replace("+00:00", "Z")
            existing["detail"] = "superseded by a new attempt"
        attempt = {
            "attempt_id": f"{episode}-{int(now.timestamp())}",
            "run_id": run_id,
            "started_at": now.isoformat().replace("+00:00", "Z"),
            "budget_seconds": int(budget_seconds),
            "deadline_at": (now + timedelta(seconds=int(budget_seconds)))
                .isoformat().replace("+00:00", "Z"),
            "checkpoints": [{"stage": stage, "at": now.isoformat().replace("+00:00", "Z"),
                             "detail": ""}],
            "outcome": None,
        }
        record.setdefault("attempt_log", []).append(attempt)
        record["attempts"] = record.get("attempts", 0) + 1
        save_ledger(ledger)
    return attempt


def checkpoint_attempt(episode: str, stage: str, detail: str = "") -> dict[str, Any]:
    """Record durable progress mid-unit so partial work survives termination."""
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    with PipelineLock(timeout=0):
        ledger = load_ledger()
        record = _episode_record(ledger, episode)
        attempt = _open_attempt(record)
        if not attempt:
            raise ValueError(f"no open attempt for episode {episode}; run 'attempt start' first")
        attempt.setdefault("checkpoints", []).append(
            {"stage": stage, "at": now, "detail": detail[:400]}
        )
        save_ledger(ledger)
    return attempt


def finish_attempt(episode: str, outcome: str, detail: str = "") -> dict[str, Any]:
    """Close an attempt with an explicit terminal outcome."""
    if outcome not in ATTEMPT_OUTCOMES:
        raise ValueError(f"outcome must be one of {sorted(ATTEMPT_OUTCOMES)}")
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    with PipelineLock(timeout=0):
        ledger = load_ledger()
        record = _episode_record(ledger, episode)
        attempt = _open_attempt(record)
        if not attempt:
            raise ValueError(f"no open attempt for episode {episode}")
        attempt["outcome"] = outcome
        attempt["finished_at"] = now
        attempt["detail"] = detail[:400]
        save_ledger(ledger)
    return attempt


def attempts_report(ledger: dict[str, Any], now: datetime | None = None,
                    stall_seconds: int = DEFAULT_STALL_SECONDS) -> dict[str, Any]:
    """Summarise attempts per episode, including consecutive failures.

    A run of failures that leaves no episode-state change is invisible in the
    episode view; it is exactly the condition an operator needs to see.
    """
    moment = now or datetime.now(timezone.utc)
    episodes: dict[str, Any] = {}
    for number, record in sorted((ledger.get("episodes") or {}).items()):
        log = record.get("attempt_log") or []
        if not log:
            continue
        states = [classify_attempt(a, moment, stall_seconds) for a in log]
        consecutive_failures = 0
        for state in reversed(states):
            if state in {"failed", "timed_out", "stalled"}:
                consecutive_failures += 1
            else:
                break
        last = log[-1]
        episodes[number] = {
            "attempts": len(log),
            "last_state": states[-1],
            "last_stage": (last.get("checkpoints") or [{}])[-1].get("stage"),
            "last_started_at": last.get("started_at"),
            "consecutive_failures": consecutive_failures,
            "in_flight": states[-1] == "running",
        }
    return episodes


def episode_dirs(episode: str | None = None) -> Iterable[tuple[str, Path]]:
    if episode:
        path = ROOT / "episodes" / episode
        if not path.is_dir():
            raise FileNotFoundError(path)
        return [(episode, path)]
    return sorted((p.name, p) for p in (ROOT / "episodes").iterdir() if p.is_dir() and p.name.isdigit())


def inventory(episode: str | None = None) -> dict[str, Any]:
    entries = []
    for number, directory in episode_dirs(episode):
        for path in sorted(directory.rglob("*")):
            if path.is_file() and not path.name.startswith("."):
                stat = path.stat()
                entries.append({"episode": number, "path": path.relative_to(ROOT).as_posix(), "size": stat.st_size, "sha256": sha256(path), "mtime_ns": stat.st_mtime_ns})
    ownership: dict[str, list[str]] = {}
    for number, item in load_manifest().get("episodes", {}).items():
        for key in item.get("sources", []):
            ownership.setdefault(key, []).append(number)
    result = {"schema_version": 1, "generated_at": utc_now(), "root": str(ROOT), "files": entries, "source_ownership": ownership,
              "duplicate_sources": {key: owners for key, owners in ownership.items() if len(owners) > 1}}
    atomic_json(INVENTORY_PATH, result)
    return result


def reconcile(episode: str | None = None, write: bool = False) -> dict[str, Any]:
    ledger = load_ledger()
    expected = load_manifest().get("episodes", {})
    report = {"generated_at": utc_now(), "episodes": {}, "ok": True}
    ownership: dict[str, list[str]] = {}
    for number, item in expected.items():
        for key in item.get("sources", []):
            ownership.setdefault(key, []).append(number)
    report["source_ownership"] = ownership
    for key, owners in ownership.items():
        if len(owners) > 1:
            report["ok"] = False
            report.setdefault("issues", []).append(f"source {key} is assigned to multiple episodes: {owners}")
    for number, directory in episode_dirs(episode):
        rec = ledger.setdefault("episodes", {}).setdefault(number, {"status": "planned", "transitions": []})
        expected_item = expected.get(number, {})
        audio = list(directory.glob("*.mp3"))
        notes = directory / "episode-notes.md"
        issues = []
        if expected_item.get("sources") and rec.get("sources") and sorted(expected_item["sources"]) != sorted(rec["sources"]):
            issues.append("ledger source list differs from manifest")
        if not notes.exists():
            issues.append("missing episode-notes.md")
        if rec.get("status") in {"rendered", "verified", "published"} and not audio:
            issues.append("ledger says audio exists but no MP3 is present")
        artifacts = {"notes": str(notes.relative_to(ROOT)) if notes.exists() else None,
                     "audio": [str(p.relative_to(ROOT)) for p in audio]}
        rec["artifacts"] = artifacts
        if issues:
            report["ok"] = False
            # De-duplicating extend (ported from the HITL tree, run 459 there).
            # reconcile(write=True) runs every slice, so an issue that stays
            # true must not be re-stored each time: an unconditional extend()
            # grew this list without bound (218 exact copies of one accurate
            # issue on HITL stubs 017/018/020). Every DISTINCT issue is still
            # recorded and report["ok"] is still False -- no gate changes.
            stored = rec.setdefault("errors", [])
            seen = {e for e in stored if isinstance(e, str)}
            for issue in issues:
                if issue not in seen:
                    stored.append(issue)
                    seen.add(issue)
        report["episodes"][number] = {"status": rec.get("status"), "issues": issues, "artifacts": artifacts}
    if write:
        save_ledger(ledger)
    return report


def parse_turns(script: Path) -> list[tuple[str, str]]:
    turns = []
    for line in script.read_text().splitlines():
        m = re.match(r"^\*\*(Host|Rowan|Turing|Guest):\*\*\s+(.+?)\s*$", line, re.I)
        if m:
            role = m.group(1).lower().replace("guest", "rowan").replace("turing", "rowan")
            if role not in ROLES or not m.group(2).strip():
                raise ValueError(f"invalid dialogue turn in {script}: {line}")
            turns.append((role, m.group(2).strip()))
    if not turns:
        raise ValueError(f"no Host/Rowan turns found in {script}")
    return turns


def source_keys(text: str) -> list[str]:
    return re.findall(r"(?:items/|zotero://select/items/)([A-Z0-9]{8})", text)


def review_gate(episode: str, panel: Path | None = None) -> dict[str, Any]:
    panel = panel or ROOT / "episodes" / episode / "review-panel.md"
    try:
        panel_label = str(panel.relative_to(ROOT))
    except ValueError:
        panel_label = str(panel)
    result: dict[str, Any] = {"episode": episode, "ok": False, "panel": panel_label, "issues": [], "reviewers": []}
    if not panel.exists():
        result["issues"].append("review panel is missing")
        return result
    text = panel.read_text()
    heading_matches = re.findall(r"^##\s+Reviewer\s+(\d+)\s+—\s+(.+)$", text, re.M)
    headings = [name for _, name in heading_matches]
    result["reviewers"] = headings
    if len(headings) != 3 or len(set(headings)) != 3 or len({number for number, _ in heading_matches}) != 3:
        result["issues"].append("exactly three distinct reviewer sections are required")
    verdicts = re.findall(r"(?:Initial\s+)?verdict:\s*([^\.\n]+)", text, re.I)
    if len(verdicts) != 3 or any("pass" not in v.lower() for v in verdicts):
        result["issues"].append("each reviewer must record a pass verdict")
    required = re.findall(r"Required revisions:\s*(.*?)(?=\n\n|\n##|$)", text, re.I | re.S)
    if len(required) != 3 or any(not r.strip() for r in required):
        result["issues"].append("each reviewer must record required revisions and their resolution")
    if not re.search(r"Revision record\b", text, re.I):
        result["issues"].append("revision record is missing")
    if re.search(r"\b(?:unresolved|not addressed|blocked)\b", text, re.I):
        result["issues"].append("panel contains an unresolved/blocking issue")
    result["ok"] = not result["issues"]
    return result


def record_review(episode: str, panel: Path | None = None) -> dict[str, Any]:
    """Persist a review decision and its evidence in the episode ledger."""
    result = review_gate(episode, panel)
    ledger = load_ledger()
    record = ledger.setdefault("episodes", {}).setdefault(episode, {"status": "planned", "transitions": []})
    record.setdefault("checks", {})["review_gate"] = result
    if result["ok"]:
        if record.get("status") == "planned":
            transition(ledger, episode, "review_pending", "review submitted")
        if record.get("status") == "review_pending":
            transition(ledger, episode, "reviewed", "three-reviewer gate passed")
    elif record.get("status") == "planned":
        transition(ledger, episode, "review_pending", "review gate failed; revisions required")
    save_ledger(ledger)
    return result


def preflight(episode: str, require_audio: bool = False, enforce_review: bool = True) -> dict[str, Any]:
    directory = ROOT / "episodes" / episode
    result: dict[str, Any] = {"episode": episode, "ok": False, "issues": [], "checks": {}}
    manifest = load_manifest().get("episodes", {}).get(episode, {})
    script, notes = directory / "script.md", directory / "episode-notes.md"
    try:
        turns = parse_turns(script)
        result["checks"]["dialogue_turns"] = len(turns)
    except (OSError, ValueError) as exc:
        result["issues"].append(str(exc))
        turns = []
    if not notes.exists():
        result["issues"].append("missing episode-notes.md")
        notes_text = ""
    else:
        notes_text = notes.read_text()
    script_text = script.read_text() if script.exists() else ""
    if REQUIRED_DISCLOSURE not in script_text and REQUIRED_DISCLOSURE not in notes_text:
        result["issues"].append("required Zotero-links disclosure is absent from both script and notes")
    if not re.search(r"fictional.*(?:composite|correspondent)|(?:composite|fictional).*correspondent", script_text, re.I | re.S):
        result["issues"].append("fictional-correspondent disclosure is absent from script")
    if not re.search(r"AI-generated|AI generated", script_text, re.I):
        result["issues"].append("AI-summary disclosure is absent from script")
    keys = source_keys(notes_text)
    expected_keys = list(manifest.get("sources", []))
    result["checks"]["notes_zotero_keys"] = sorted(set(keys))
    all_owners: dict[str, list[str]] = {}
    for number, item in load_manifest().get("episodes", {}).items():
        for key in item.get("sources", []):
            all_owners.setdefault(key, []).append(number)
    for key in expected_keys:
        if len(all_owners.get(key, [])) > 1:
            result["issues"].append(f"source {key} is assigned to multiple episodes")
    if expected_keys and not set(expected_keys).issubset(keys):
        result["issues"].append("manifest source key missing from episode notes")
    numbered = re.findall(r"^\s*\d+\.\s+(.+)$", notes_text, re.M)
    for key in expected_keys:
        entry = next((line for line in numbered if key in line), "")
        if not entry:
            result["issues"].append(f"source {key} has no numbered citation entry")
            continue
        if not re.search(r"\b(?:19|20)\d{2}\b", entry):
            result["issues"].append(f"source {key} citation has no publication year")
        if len(re.sub(r"\[[^]]+\]\([^)]*\)", "", entry).split()) < 8:
            result["issues"].append(f"source {key} citation is too short for author/title/venue metadata")
        if not re.search(r"zotero\.org|zotero://", entry, re.I):
            result["issues"].append(f"source {key} citation has no direct Zotero link")
    result["checks"]["numbered_source_entries"] = len(numbered)
    if len(keys) != len(set(keys)):
        result["issues"].append("duplicate Zotero links in notes")
    if enforce_review:
        gate = review_gate(episode)
        result["checks"]["review_gate"] = gate
        if not gate["ok"]:
            result["issues"].extend("review gate: " + issue for issue in gate["issues"])
    if require_audio:
        audio = list(directory.glob("*.mp3"))
        if len(audio) != 1 or audio[0].stat().st_size == 0:
            result["issues"].append("exactly one non-empty episode MP3 is required")
        else:
            result["checks"]["audio"] = {"path": str(audio[0].relative_to(ROOT)), "size": audio[0].stat().st_size, "sha256": sha256(audio[0])}
    result["ok"] = not result["issues"]
    return result


def run_with_retry(operation, attempts: int = MAX_RETRIES, base_delay: float = 1.0):
    attempts = max(1, min(attempts, MAX_RETRIES))
    last = None
    for number in range(1, attempts + 1):
        try:
            return operation(number)
        except Exception as exc:  # caller receives the final cause
            last = exc
            if number == attempts:
                raise
            time.sleep(base_delay * (2 ** (number - 1)))
    raise last  # pragma: no cover


def _tts_imports():
    sys.path.insert(0, "/data/.openclaw/workspace/vendor/two-voice-tts")
    import edge_tts, imageio_ffmpeg
    return edge_tts, imageio_ffmpeg


def spoken_text(text: str) -> str:
    """Remove Markdown-only emphasis delimiters before sending text to TTS."""
    return text.replace("*", "").replace("`", "")


async def render_episode(episode: str, retries: int = MAX_RETRIES, force: bool = False) -> Path:
    """Render script turns with resumable parts and an atomic final MP3."""
    gate = preflight(episode, require_audio=False, enforce_review=True)
    if not gate["ok"]:
        raise ValueError("preflight failed: " + "; ".join(gate["issues"]))
    script = ROOT / "episodes" / episode / "script.md"
    output_dir = script.parent
    output = next((p for p in output_dir.glob("*.mp3") if p.name != "output.mp3"), output_dir / f"episode-{episode}.mp3")
    parts = output_dir / "parts-robust"
    parts.mkdir(exist_ok=True)
    turns = parse_turns(script)
    plan = hashlib.sha256(script.read_bytes()).hexdigest()
    plan_file = parts / "render-plan.json"
    old_plan = json.loads(plan_file.read_text()) if plan_file.exists() else {}
    if (old_plan.get("script_sha256") != plan
            or old_plan.get("render_text_version") != RENDER_TEXT_VERSION):
        force = True
        for old in parts.glob("*.mp3"):
            old.unlink()
    edge_tts, imageio_ffmpeg = _tts_imports()
    voices = {"host": "en-US-AvaMultilingualNeural", "rowan": "en-US-AndrewMultilingualNeural", "guest": "en-US-AndrewMultilingualNeural"}
    rates = {"host": "-3%", "rowan": "+18%", "guest": "+18%"}
    with PipelineLock(timeout=0):
        ledger = load_ledger()
        record = ledger.setdefault("episodes", {}).setdefault(episode, {"status": "planned", "transitions": []})
        if record.get("status") in {"planned", "review_pending"}:
            if record.get("status") == "planned":
                transition(ledger, episode, "review_pending", "awaiting three-reviewer gate")
                save_ledger(ledger)
            transition(ledger, episode, "reviewed", "three-reviewer gate passed")
        transition(ledger, episode, "rendering", "render started")
        record["attempts"] = record.get("attempts", 0) + 1
        save_ledger(ledger)
        files = []
        try:
            for index, (role, text) in enumerate(turns):
                part = parts / f"{index:04d}-{role}.mp3"
                if not force and part.exists() and part.stat().st_size > 1000:
                    files.append(part)
                    continue
                temporary = part.with_suffix(part.suffix + f".tmp.{os.getpid()}")
                async def synth(_: int):
                    await edge_tts.Communicate(spoken_text(text), voices[role], rate=rates[role]).save(str(temporary))
                    if not temporary.exists() or temporary.stat().st_size <= 1000:
                        raise IOError(f"empty TTS output for turn {index}")
                await _async_retry(synth, retries)
                os.replace(temporary, part)
                files.append(part)
            concat = parts / "concat.txt"
            atomic_write(concat, "".join(f"file '{p.resolve().as_posix()}'\n" for p in files))
            temporary_output = output.with_suffix(output.suffix + f".tmp.{os.getpid()}")
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            # The atomic temporary name ends in ``.tmp.<pid>``, so ffmpeg
            # cannot infer the output container from its suffix. Declare MP3
            # explicitly before writing the temporary file.
            subprocess.run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c:a", "libmp3lame", "-b:a", "128k", "-f", "mp3", str(temporary_output)], check=True, capture_output=True)
            if not temporary_output.exists() or temporary_output.stat().st_size <= 1000:
                raise IOError("ffmpeg produced an empty output")
            os.replace(temporary_output, output)
            atomic_json(plan_file, {"schema_version": 1, "render_text_version": RENDER_TEXT_VERSION, "script_sha256": plan, "turns": len(turns), "parts": [p.name for p in files], "completed_at": utc_now()})
            transition(ledger, episode, "rendered", "atomic render complete")
            record["artifacts"] = {"audio": str(output.relative_to(ROOT)), "audio_sha256": sha256(output), "turns": len(turns)}
            save_ledger(ledger)
            return output
        except Exception as exc:
            if 'temporary_output' in locals():
                with contextlib.suppress(FileNotFoundError):
                    temporary_output.unlink()
            record.setdefault("errors", []).append({"at": utc_now(), "error": repr(exc)})
            transition(ledger, episode, "failed", "render failed")
            save_ledger(ledger)
            raise


async def _async_retry(operation, attempts: int):
    attempts = max(1, min(attempts, MAX_RETRIES))
    for n in range(1, attempts + 1):
        try:
            return await operation(n)
        except Exception:
            if n == attempts:
                raise
            await asyncio.sleep(2 ** (n - 1))


def verify_feed(feed: Path | str, remote: str | None = None, timeout: float = 15.0) -> dict[str, Any]:
    """Verify local RSS/files and optionally the deployed feed over HTTP."""
    feed_path = Path(feed) if not str(feed).startswith(("http://", "https://")) else None
    result: dict[str, Any] = {"ok": False, "feed": str(feed), "checks": [], "issues": [], "warnings": []}
    try:
        xml = feed_path.read_bytes() if feed_path else urllib.request.urlopen(str(feed), timeout=timeout).read()
        root = ET.fromstring(xml)
        if remote and feed_path:
            remote_feed = remote.rstrip("/") + "/feed.xml"
            try:
                with urllib.request.urlopen(remote_feed, timeout=timeout) as response:
                    remote_root = ET.fromstring(response.read())
                    if response.status != 200 or not remote_root.findall(".//item"):
                        raise IOError(f"HTTP {response.status} or no RSS items")
                result["checks"].append({"name": "remote_feed", "url": remote_feed, "http": 200})
            except Exception as exc:
                result["issues"].append(f"remote feed check failed for {remote_feed}: {exc}")
        items = root.findall(".//item")
        guids = [item.findtext("guid", "") for item in items]
        if len(guids) != len(set(guids)):
            result["issues"].append("duplicate RSS GUID")
        result["checks"].append({"name": "feed_parse", "ok": True, "items": len(items)})
        for item in items:
            legacy_item = item.findtext("{http://www.itunes.com/dtds/podcast-1.0.dtd}episode") == "1"
            enclosure = item.find("enclosure")
            if enclosure is None or not enclosure.get("url"):
                result["issues"].append("RSS item missing enclosure")
                continue
            url, length = enclosure.get("url"), int(enclosure.get("length", "-1"))
            if feed_path:
                local = feed_path.parent / Path(urllib.parse.urlparse(url).path).name
                if not local.exists():
                    result["issues"].append(f"missing local enclosure {local.name}")
                elif length != local.stat().st_size:
                    result["issues"].append(f"enclosure length mismatch for {local.name}")
            if remote:
                remote_url = remote.rstrip("/") + "/" + Path(urllib.parse.urlparse(url).path).name
                req = urllib.request.Request(remote_url, headers={"Range": "bytes=0-1023"})
                try:
                    with urllib.request.urlopen(req, timeout=timeout) as response:
                        status = response.status
                        body = response.read(1024)
                    if status not in (200, 206) or not body:
                        result["issues"].append(f"remote audio check failed for {remote_url}: HTTP {status}")
                    else:
                        content_range = response.headers.get("Content-Range", "")
                        match = re.search(r"/([0-9]+)$", content_range)
                        if match and int(match.group(1)) != length:
                            result["issues"].append(f"remote audio length mismatch for {remote_url}")
                        result["checks"].append({"name": "remote_audio", "url": remote_url, "http": status})
                except Exception as exc:
                    result["issues"].append(f"remote audio check failed for {remote_url}: {exc}")
            notes_link = item.find("content:encoded", {"content": "http://purl.org/rss/1.0/modules/content/"})
            if notes_link is None:
                # ElementTree's expanded name is easier to handle portably.
                notes_link = next((x for x in item if x.tag.endswith("encoded")), None)
            if notes_link is not None:
                hrefs = re.findall(r'href=["\']([^"\']+notes\.md)["\']', notes_link.text or "")
                if feed_path:
                    for href in hrefs:
                        local_notes = feed_path.parent / Path(urllib.parse.urlparse(href).path).name
                        if not local_notes.exists():
                            target = result["warnings"] if legacy_item else result["issues"]
                            target.append(f"missing local notes file {local_notes.name}")
                if remote:
                    for href in hrefs:
                        notes_url = remote.rstrip("/") + "/" + Path(href).name
                        try:
                            with urllib.request.urlopen(notes_url, timeout=timeout) as response:
                                if response.status != 200:
                                    raise IOError(f"HTTP {response.status}")
                            result["checks"].append({"name": "remote_notes", "url": notes_url, "http": 200})
                        except Exception as exc:
                            target = result["warnings"] if legacy_item else result["issues"]
                            target.append(f"remote notes check failed for {notes_url}: {exc}")
    except Exception as exc:
        result["issues"].append(f"feed parse/check failed: {exc}")
    result["ok"] = not result["issues"]
    return result


def publish_local(episodes: list[str] | None = None, remote: str | None = None) -> dict[str, Any]:
    """Build the checked-in local feed and verify it; never performs a git push.

    Already-published legacy episodes are treated as imported history. Any
    episode still in a production state must pass the review gate and audio
    preflight before it can enter the local feed.
    """
    try:
        from .publish_feed import main as build_feed
    except ImportError:
        from publish_feed import main as build_feed
    ledger = load_ledger()
    selected = episodes or sorted(load_manifest().get("episodes", {}))
    checks = []
    for number in selected:
        record = ledger.get("episodes", {}).get(number, {})
        if record.get("status") != "published":
            check = preflight(number, require_audio=True, enforce_review=True)
            checks.append(check)
            if not check["ok"]:
                raise ValueError(f"publish preflight failed for {number}: {'; '.join(check['issues'])}")
    with PipelineLock(timeout=0):
        build_feed()
        result = verify_feed(ROOT / "feed-site" / "feed.xml", remote)
        if not result["ok"]:
            raise ValueError("local publication verification failed: " + "; ".join(result["issues"]))
        for number in selected:
            record = ledger.setdefault("episodes", {}).setdefault(number, {"status": "planned", "transitions": []})
            if record.get("status") == "rendered":
                transition(ledger, number, "verified", "local feed checks passed")
            if record.get("status") == "verified":
                transition(ledger, number, "published", "local feed built and verified; remote push remains manual")
        save_ledger(ledger)
    return {"ok": True, "episodes": selected, "preflight": checks, "verification": result, "external_push": "not performed"}



def load_deploy_token() -> str:
    """Return the deploy token. Environment variables win over the env file;
    the dedicated podcast token (GITHUB_PODCAST_TOKEN) is preferred over the
    general-purpose GITHUB_TOKEN. Raises if neither is configured.
    Never hardcodes a token."""
    for var in ("GITHUB_PODCAST_TOKEN", "GITHUB_TOKEN"):
        val = os.environ.get(var, "").strip()
        if val:
            return val
    if DEPLOY_ENV_FILE.exists():
        for var in ("GITHUB_PODCAST_TOKEN", "GITHUB_TOKEN"):
            for line in DEPLOY_ENV_FILE.read_text().splitlines():
                line = line.strip()
                if line.startswith("#"):
                    continue
                key, sep, val = line.partition("=")
                if sep and key == var:
                    val = val.strip()
                    if val:
                        return val
    raise ValueError("deploy token not set (GITHUB_PODCAST_TOKEN or GITHUB_TOKEN)")

def push_to_remote(episodes: list[str] | None = None, wait_seconds: int = 120,
                   push_timeout: int | None = None) -> dict[str, Any]:
    """Deploy the verified local feed-site to the GitHub Pages site and confirm live.

    Standalone CLI command; publish_local() does not call it automatically.
    """
    import shutil
    import subprocess as sp

    token = load_deploy_token()
    if shutil.which("git") is None:
        raise ValueError("git is not available on this host")
    work = Path(tempfile.mkdtemp(prefix="pitl-deploy-"))
    repo = work / "repo"
    result: dict[str, Any] = {"ok": False, "cloned": False, "committed": [], "pushed": False, "live": []}
    try:
        clone_url = f"https://{token}@{DEPLOY_REPO.removeprefix('https://')}"
        sp.run(["git", "clone", "--quiet", "--depth", "1", clone_url, str(repo)],
               check=True, capture_output=True, timeout=600)
        result["cloned"] = True
        # Scrub the token from the on-disk git config (defence in depth), then
        # re-point the remote at the clean URL. The push is authenticated by a
        # repo-local, self-deleting credential helper (token read from the
        # environment, never written to disk) -- NOT by the URL. The old
        # behaviour of replacing the token with the literal string "[token]"
        # left the origin URL as https://[token]@github.com/..., an invalid
        # credential: git gets a 401, falls back to an interactive password
        # prompt (no tty), and exits 128.
        cfg = repo / ".git" / "config"
        cfg.write_text(cfg.read_text().replace(token, "[token]"))
        sp.run(["git", "-C", str(repo), "remote", "set-url", "origin", DEPLOY_REPO],
               check=True, capture_output=True)
        helper = work / "ghcred"
        helper.write_text(
            "#!/bin/sh\n"
            "# Read host from the key=value lines git sends on stdin.\n"
            'host=""\n'
            'while IFS="=" read -r key value; do\n'
            '  [ "$key" = "host" ] && host="$value"\n'
            "done\n"
            'if [ "$host" = "github.com" ]; then\n'
            '  t="${GITHUB_PODCAST_TOKEN:-}"\n'
            '  [ -z "$t" ] && t="${GITHUB_TOKEN:-}"\n'
            '  if [ -n "$t" ]; then\n'
            '    echo "username=x"\n'
            '    echo "password=$t"\n'
            "  fi\n"
            "fi\n"
        )
        helper.chmod(0o700)
        sp.run(["git", "-C", str(repo), "config", "credential.helper",
                "!" + str(helper)], check=True, capture_output=True)
        site = ROOT / "feed-site"
        synced = []
        for f in site.iterdir():
            if f.is_file():
                shutil.copy2(f, repo / f.name)
                synced.append(f.name)
        r = sp.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
        staged = sp.run(["git", "-C", str(repo), "diff", "--cached", "--name-only"],
                         check=True, capture_output=True, text=True).stdout.split()
        if staged:
            note = ("Publish episodes: " + ", ".join(sorted(episodes))) if episodes                 else "Sync feed-site to live site"
            sp.run(["git", "-C", str(repo), "-c", f"user.name={DEPLOY_GIT_USER}",
                     "-c", f"user.email={DEPLOY_GIT_EMAIL}", "commit", "--quiet",
                     "-m", f"{note} (local feed built and verified)",
                     "-m", f"Staged files: {', '.join(staged)}"],
                    check=True, capture_output=True)
            result["committed"] = staged
        if not result["committed"]:
            result["ok"] = True
            result["note"] = "local feed already matches the live site; nothing to push"
            return result
        push_env = dict(os.environ)
        if not push_env.get("GITHUB_PODCAST_TOKEN"):
            push_env["GITHUB_PODCAST_TOKEN"] = token
        # Size-aware push window. The old code used a hardcoded 300s, which is
        # ample for a ~20 MB interview episode but not for a long verbatim
        # reading: the sibling tree's 66 MB reading 501 really did exceed it,
        # and because TimeoutExpired fell into the broad handler below it was
        # reported identically to a credential failure and misdiagnosed as one.
        # Derive the window from the bytes actually staged, at a pessimistic
        # assumed floor rate, and keep 300s as a FLOOR so this can only ever
        # grant more time than before, never less.
        staged_bytes = 0
        for name in staged:
            f = repo / name
            if f.is_file():
                staged_bytes += f.stat().st_size
        if push_timeout is None:
            assumed_bytes_per_s = 120 * 1024  # deliberately pessimistic floor
            derived = int(staged_bytes / assumed_bytes_per_s) + 120
            effective_timeout = max(300, derived)
        else:
            effective_timeout = max(1, int(push_timeout))
        result["staged_bytes"] = staged_bytes
        result["push_timeout"] = effective_timeout
        sp.run(["git", "-C", str(repo), "push", "--quiet", "origin", "HEAD:main"],
               check=True, capture_output=True, timeout=effective_timeout,
               env=push_env)
        result["pushed"] = True
        # GitHub Pages propagates within a couple of minutes; verify live feed.
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            v = verify_feed(str(ROOT / "feed-site" / "feed.xml"), remote=FEED_BASE)
            result["live"] = v
            if v["ok"]:
                break
            time.sleep(30)
        result["ok"] = bool(result["live"]) and not result["live"]["issues"]
        if not result["ok"]:
            result["issues"] = result["live"]["issues"]
        return result
    except sp.TimeoutExpired as exc:
        # A timed-out push is NOT a failed push: git may have finished
        # server-side after the client stopped waiting. Reporting it as a
        # generic failure is what caused the sibling tree to hunt credentials
        # on what was really a slow upload of a large reading. Say so, and
        # tell the operator to establish the remote state before retrying --
        # a blind retry risks a non-fast-forward rejection.
        err = str(exc)
        err = err.replace(token, "[redacted]") if token else err
        result["timed_out"] = True
        result["remote_state"] = "indeterminate"
        result["error"] = (
            f"push exceeded its {result.get('push_timeout', 'configured')}s window "
            f"after staging {result.get('staged_bytes', 0)} bytes; the remote may "
            "or may not have the commit. This is a TIMEOUT, not an authentication "
            "failure: check `git ls-remote origin main` before retrying, and "
            "re-run with a larger --push-timeout. Underlying: " + err
        )
        return result
    except Exception as exc:
        err = str(exc)
        err = err.replace(token, "[redacted]") if token else err
        result["error"] = f"remote deploy failed: {err}"
        return result
    finally:
        # Wipe the working tree (git objects may contain the token until it is
        # garbage-collected); keep nothing on disk.
        sp.run(["rm", "-rf", str(work)], check=False, capture_output=True)



def feed_coverage(feed: Path | str | None = None) -> dict[str, Any]:
    """Audit that every episode recorded as published actually reaches the feed.

    READ-ONLY. It grants nothing and writes nothing; it is not a publication
    gate and does not replace preflight/review_gate/verify_feed. It exists
    because the publish path and the bookkeeping can disagree in silence:
    publish_feed.py derives its item list from the manifest plus the ledger
    status, so an episode whose status falls outside the published family, or
    whose manifest entry is missing, is skipped while `publish` still reports
    ok: true.

    Matching is on the episode number inside the item GUID, which is stable
    across the interview naming scheme and the read lane's `-reading` suffix,
    so constructing `episode-NNN.mp3` by hand cannot produce a false 404. Each
    matched enclosure is additionally checked to exist on disk at exactly its
    advertised byte length.
    """
    feed_path = Path(feed) if feed else (ROOT / "feed-site" / "feed.xml")
    report: dict[str, Any] = {
        "ok": True,
        "feed": str(feed_path),
        "feed_items": 0,
        "published_episodes": 0,
        "missing_from_feed": [],
        "enclosure_issues": [],
        "unrecorded_feed_items": [],
        "issues": [],
    }
    if not feed_path.exists():
        report["ok"] = False
        report["issues"].append(f"feed not found: {feed_path}")
        return report
    try:
        root = ET.fromstring(feed_path.read_text())
    except ET.ParseError as exc:
        report["ok"] = False
        report["issues"].append(f"feed does not parse: {exc}")
        return report

    items = root.findall(".//item")
    report["feed_items"] = len(items)

    by_number: dict[str, list[tuple[str, str, str]]] = {}
    for item in items:
        guid = (item.findtext("guid") or "").strip()
        enc = item.find("enclosure")
        url = (enc.get("url") or "") if enc is not None else ""
        length = (enc.get("length") or "") if enc is not None else ""
        found = re.findall(r"episode-(\d+)", guid) or re.findall(r"episode-(\d+)", url)
        if found:
            by_number.setdefault(found[0], []).append((guid, url, length))
        else:
            report["unrecorded_feed_items"].append(guid or url or "<unidentified item>")

    published: set[str] = set()
    for path in (LEDGER_PATH, MANIFEST_PATH):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        for number, rec in (data.get("episodes") or {}).items():
            if str(rec.get("status", "")).startswith("published"):
                published.add(str(number))
    try:
        read_data = json.loads((PIPELINE / "read-episodes.json").read_text())
    except (OSError, json.JSONDecodeError):
        read_data = {}
    for number, rec in (read_data.get("episodes") or {}).items():
        if rec.get("verified"):
            published.add(str(number))
    report["published_episodes"] = len(published)

    for number in sorted(published):
        entries = by_number.get(number)
        if not entries:
            report["missing_from_feed"].append(number)
            report["issues"].append(
                f"episode {number} is recorded as published but has no feed item")
            continue
        for guid, url, length in entries:
            name = url.rsplit("/", 1)[-1]
            if not name:
                report["enclosure_issues"].append(
                    {"episode": number, "guid": guid, "problem": "no enclosure url"})
                report["issues"].append(f"episode {number} feed item has no enclosure url")
                continue
            local = feed_path.parent / name
            if not local.exists():
                report["enclosure_issues"].append(
                    {"episode": number, "file": name, "problem": "enclosure file absent"})
                report["issues"].append(f"episode {number} enclosure {name} is not on disk")
                continue
            actual = local.stat().st_size
            if length and str(actual) != str(length):
                report["enclosure_issues"].append({
                    "episode": number, "file": name, "problem": "length mismatch",
                    "advertised": length, "actual": actual})
                report["issues"].append(
                    f"episode {number} enclosure {name} advertises {length} bytes "
                    f"but is {actual}")

    report["ok"] = not report["issues"]
    return report


def status() -> dict[str, Any]:
    ledger = load_ledger()
    report = {"generated_at": utc_now(), "ledger_updated_at": ledger.get("updated_at"), "episodes": {}, "healthy": True}
    for number, rec in sorted(ledger.get("episodes", {}).items()):
        # Legacy published episodes predate checked-in scripts/review panels;
        # retain their audit issues without treating them as an active failure.
        pre = preflight(number, require_audio=False, enforce_review=False)
        is_legacy = rec.get("status") == "published"
        entry = {"state": rec.get("status"), "attempts": rec.get("attempts", 0), "errors": rec.get("errors", [])[-3:], "preflight_ok": True if is_legacy else pre["ok"], "issues": [] if is_legacy else pre["issues"]}
        if is_legacy and pre["issues"]:
            entry["legacy_audit_issues"] = pre["issues"]
        report["episodes"][number] = entry
        if rec.get("status") in {"failed", "blocked", "rendering"} or (not is_legacy and not pre["ok"]):
            report["healthy"] = False
    report["lock"] = dict(lock_status(), path=str(LOCK_PATH))
    if report["lock"]["active"]:
        report["healthy"] = False
    return report


def episode_last_change(record: dict[str, Any]) -> datetime | None:
    """When this episode itself last moved, ignoring unrelated ledger writes."""
    stamps: list[datetime] = []
    for entry in record.get("transitions") or []:
        with contextlib.suppress(Exception):
            stamps.append(_parse_iso(entry["at"]))
    for attempt in record.get("attempt_log") or []:
        for mark in attempt.get("checkpoints") or []:
            with contextlib.suppress(Exception):
                stamps.append(_parse_iso(mark["at"]))
    return max(stamps) if stamps else None


def watchdog(max_render_minutes: int = 120,
             stall_seconds: int = DEFAULT_STALL_SECONDS) -> dict[str, Any]:
    """Report work that cannot still be making progress.

    Staleness is measured per episode. It previously came from the ledger's
    global ``updated_at``, so any write about any other episode made a genuinely
    stuck render look fresh and the watchdog never fired.
    """
    report = status()
    ledger = load_ledger()
    now = datetime.now(timezone.utc)
    stale: list[str] = []

    for number, rec in report["episodes"].items():
        record = (ledger.get("episodes") or {}).get(number, {})
        changed = episode_last_change(record)
        if rec["state"] == "rendering" and changed:
            age_minutes = (now - changed).total_seconds() / 60
            if age_minutes > max_render_minutes:
                stale.append(f"episode {number} rendering for {age_minutes:.1f} minutes")

    attempts = attempts_report(ledger, now, stall_seconds)
    for number, info in attempts.items():
        if info["last_state"] == "timed_out":
            stale.append(f"episode {number} attempt exceeded its budget without finishing")
        elif info["last_state"] == "stalled":
            stale.append(f"episode {number} attempt has not checkpointed recently")
        # Repeated failure that never changes episode state is invisible in the
        # episode view; surface it rather than letting it retry silently.
        if info["consecutive_failures"] >= 3:
            stale.append(
                f"episode {number} has {info['consecutive_failures']} consecutive failed attempts"
            )

    report["attempts"] = attempts
    report["stale"] = stale
    report["healthy"] = report["healthy"] and not stale
    return report


def print_result(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("inventory"); p.add_argument("--episode")
    p = sub.add_parser("reconcile"); p.add_argument("--episode"); p.add_argument("--write", action="store_true")
    p = sub.add_parser("preflight"); p.add_argument("episode"); p.add_argument("--audio", action="store_true"); p.add_argument("--no-review", action="store_true")
    p = sub.add_parser("review"); p.add_argument("episode"); p.add_argument("--panel", type=Path)
    p = sub.add_parser("render"); p.add_argument("episode"); p.add_argument("--force", action="store_true"); p.add_argument("--retries", type=int, default=MAX_RETRIES)
    p = sub.add_parser("verify"); p.add_argument("feed", nargs="?", default=str(ROOT / "feed-site" / "feed.xml")); p.add_argument("--remote")
    p = sub.add_parser("publish"); p.add_argument("--episode", action="append", dest="episodes"); p.add_argument("--remote", help="optional deployed site base URL to verify; no upload is performed")
    p = sub.add_parser("push"); p.add_argument("--episode", action="append", dest="episodes"); p.add_argument("--wait", type=int, default=120, help="seconds to wait for GitHub Pages to go live"); p.add_argument("--push-timeout", type=int, default=None, dest="push_timeout", help="seconds to allow the git push itself (default: derived from staged bytes, floor 300)")
    sub.add_parser("status")
    p = sub.add_parser("coverage"); p.add_argument("feed", nargs="?", default=None)
    p = sub.add_parser("watchdog"); p.add_argument("--max-render-minutes", type=int, default=120)
    p.add_argument("--stall-seconds", type=int, default=DEFAULT_STALL_SECONDS)
    p = sub.add_parser("unlock"); p.add_argument("--force", action="store_true")
    # Attempt tracking for long-running production units. A driver calls
    # `start` once, `checkpoint` as it completes each stage, and `finish` with
    # an explicit outcome, so a terminated run leaves evidence of its progress.
    p = sub.add_parser("attempt")
    asub = p.add_subparsers(dest="attempt_command", required=True)
    a = asub.add_parser("start"); a.add_argument("episode")
    a.add_argument("--budget-seconds", type=int, required=True,
                   help="budget for the COMPLETE unit including finalisation")
    a.add_argument("--run-id", default=""); a.add_argument("--stage", default="started")
    a = asub.add_parser("checkpoint"); a.add_argument("episode")
    a.add_argument("--stage", required=True); a.add_argument("--detail", default="")
    a = asub.add_parser("finish"); a.add_argument("episode")
    a.add_argument("--outcome", required=True, choices=sorted(ATTEMPT_OUTCOMES))
    a.add_argument("--detail", default="")
    asub.add_parser("status")
    args = parser.parse_args(argv)
    try:
        result = None
        if args.command == "inventory":
            with PipelineLock(timeout=0):
                result = inventory(args.episode)
        elif args.command == "reconcile":
            if args.write:
                with PipelineLock(timeout=0):
                    result = reconcile(args.episode, True)
            else:
                result = reconcile(args.episode, False)
        elif args.command == "preflight": result = preflight(args.episode, args.audio, not args.no_review)
        elif args.command == "review":
            with PipelineLock(timeout=0):
                result = record_review(args.episode, args.panel)
        elif args.command == "render": result = {"ok": True, "output": str(asyncio.run(render_episode(args.episode, args.retries, args.force)))}
        elif args.command == "verify": result = verify_feed(args.feed, args.remote)
        elif args.command == "publish": result = publish_local(args.episodes, args.remote)
        elif args.command == "push": result = push_to_remote(args.episodes, args.wait, getattr(args, "push_timeout", None))
        elif args.command == "status": result = status()
        elif args.command == "coverage": result = feed_coverage(args.feed)
        elif args.command == "watchdog": result = watchdog(args.max_render_minutes, args.stall_seconds)
        elif args.command == "unlock": unlock(args.force); result = {"unlocked": True}
        elif args.command == "attempt":
            if args.attempt_command == "start":
                result = {"ok": True, "attempt": start_attempt(
                    args.episode, args.budget_seconds, args.run_id, args.stage)}
            elif args.attempt_command == "checkpoint":
                result = {"ok": True, "attempt": checkpoint_attempt(
                    args.episode, args.stage, args.detail)}
            elif args.attempt_command == "finish":
                result = {"ok": True, "attempt": finish_attempt(
                    args.episode, args.outcome, args.detail)}
            else:
                result = {"ok": True, "attempts": attempts_report(load_ledger())}
        print_result(result)
        if args.command in {"reconcile", "preflight", "review", "verify", "publish", "push", "status", "watchdog", "attempt", "coverage"}:
            return 0 if result.get("ok", result.get("healthy", True)) else 1
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
