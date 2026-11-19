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
import email.utils
import fnmatch
import hashlib
import io
import json
import os
import platform
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import zlib
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
PUBLISH_FEED_PATH = PIPELINE / "publish_feed.py"
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


def lane_ownership(episodes: dict[str, Any]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Source ownership per lane: (interview_owners, read_owners).

    The two lanes record their Zotero keys under different manifest fields, and
    that is load-bearing: a reading registers under ``read_source`` so a paper
    that has BOTH an interview and a verbatim reading does not look like a
    duplicate-ownership conflict (run 029). Building one map from ``sources``
    alone, as every ownership site here used to, dropped readings out of
    duplicate detection altogether -- two readings of the same paper collided
    in silence even though read_lane.sync_durable_state() mirrors them into
    manifest.json specifically so duplicate detection can see them.

    Keyed on the field name, the same discriminator move_verified_sources.py
    uses, so an interview (no ``read_source``) and a reading (no ``sources``)
    each land in exactly one map and cross-lane sharing stays legal.
    """
    interview: dict[str, list[str]] = {}
    read: dict[str, list[str]] = {}
    for number, item in episodes.items():
        for key in item.get("sources", []) or []:
            interview.setdefault(key, []).append(number)
        for key in item.get("read_source", []) or []:
            read.setdefault(key, []).append(number)
    return interview, read


def duplicate_owners(*maps: dict[str, list[str]]) -> dict[str, list[str]]:
    """Keys owned by more than one episode WITHIN a lane map."""
    duplicates: dict[str, list[str]] = {}
    for mapping in maps:
        for key, owners in mapping.items():
            if len(owners) > 1:
                duplicates[key] = sorted(owners)
    return duplicates


def inventory(episode: str | None = None) -> dict[str, Any]:
    entries = []
    for number, directory in episode_dirs(episode):
        for path in sorted(directory.rglob("*")):
            if path.is_file() and not path.name.startswith("."):
                stat = path.stat()
                entries.append({"episode": number, "path": path.relative_to(ROOT).as_posix(), "size": stat.st_size, "sha256": sha256(path), "mtime_ns": stat.st_mtime_ns})
    ownership, read_ownership = lane_ownership(load_manifest().get("episodes", {}))
    result = {"schema_version": 1, "generated_at": utc_now(), "root": str(ROOT), "files": entries, "source_ownership": ownership,
              "read_source_ownership": read_ownership,
              "duplicate_sources": duplicate_owners(ownership, read_ownership)}
    atomic_json(INVENTORY_PATH, result)
    return result


def reconcile(episode: str | None = None, write: bool = False) -> dict[str, Any]:
    ledger = load_ledger()
    expected = load_manifest().get("episodes", {})
    report = {"generated_at": utc_now(), "episodes": {}, "ok": True}
    ownership, read_ownership = lane_ownership(expected)
    report["source_ownership"] = ownership
    report["read_source_ownership"] = read_ownership
    for key, owners in duplicate_owners(ownership, read_ownership).items():
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
        # The published FAMILY, not three literal strings. The old set
        # omitted the documented end states `published_and_moved`
        # (001-003's convention) and `published_pending_zotero_move`, so
        # the audio-integrity check was dead for every shipped episode in
        # this tree: an mp3 could vanish and reconcile stayed ok:true.
        # feed_coverage() already tests the family this way.
        status_now = str(rec.get("status", ""))
        if (status_now in {"rendered", "verified"} or status_now.startswith("published")) and not audio:
            issues.append("ledger says audio exists but no MP3 is present")
        # MERGE, never replace. render_episode() records the rendered audio's
        # provenance here -- audio_sha256 and the turn count -- and this
        # function runs with write=True every slice, so assigning a freshly
        # built {notes, audio} dict over the top destroyed that digest on the
        # first reconcile after any render. All three published episodes in
        # this tree show the fingerprint: a "rendering -> rendered / atomic
        # render complete" transition (so a digest was definitely written) and
        # artifacts holding only {audio, notes}. Nothing re-derives it, so the
        # loss was permanent and silent: reconcile still returned ok: true.
        artifacts = dict(rec.get("artifacts") or {})
        artifacts.update({"notes": str(notes.relative_to(ROOT)) if notes.exists() else None,
                          "audio": [str(p.relative_to(ROOT)) for p in audio]})
        # Recording provenance is not checking it (run 042's lesson, here in
        # the interview lane). reconcile() already has the audio in hand, so
        # verify the preserved digest against the file rather than leaving a
        # field with no reader. A digest that is ABSENT is not an issue --
        # 001-003 lost theirs to the bug being fixed above and are genuinely
        # published, so refusing them would be a false failure. Only a digest
        # that is present and WRONG is reported: that means the audio on disk
        # is not the audio that was rendered and gated.
        recorded_digest = artifacts.get("audio_sha256")
        if recorded_digest and len(audio) == 1:
            actual_digest = sha256(audio[0])
            if actual_digest != recorded_digest:
                issues.append(
                    f"audio does not match the digest recorded at render time "
                    f"(recorded {recorded_digest[:12]}..., on disk "
                    f"{actual_digest[:12]}...); the mp3 was replaced after it "
                    f"was gated")
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


def registry_audit() -> dict[str, Any]:
    """Audit that the durable registries agree about every episode.

    READ-ONLY. It grants nothing, writes nothing, and is NOT a publication
    gate -- the registry analogue of :func:`feed_coverage`, which proves a
    published episode reached the feed. This proves the two registries agree
    it exists at all.

    They are written by independent paths: ``state.json`` by the state
    machine, ``manifest.json`` separately at registration, so a slice that
    stops early leaves them disagreeing with nothing to notice. That silence
    is the documented cause of the worst publication gaps in the sibling tree
    (one episode live-absent for two months, another marked published while
    absent from the manifest), and until now this tree's docs asked each run
    to diff the two files BY HAND.

    Three findings, separated because they differ in severity:

    ``missing_from_manifest``
        Published in the ledger, no manifest entry. The dangerous one: the
        manifest is what ``publish_feed.py``'s item derivation and
        ``move_verified_sources.py``'s ownership logic read, so the episode is
        invisible to both while the ledger insists it shipped.
    ``missing_from_ledger``
        The manifest knows an episode the ledger has never heard of, so
        ``status``, the watchdog and the attempt ledger are all blind to it.
        Worse here than mere silence: ``reconcile(write=True)`` runs every
        slice and SILENTLY RECREATES the record as a ``planned`` stub,
        destroying the published status rather than reporting the gap.
    ``status_divergence``
        Both registries know it and disagree about how far it got. A ledger
        ``published`` against a manifest ``published_and_moved`` is the
        ordinary Zotero-move lag, so it is reported separately under
        ``benign_move_lag`` and does NOT fail the audit. The reverse direction
        does: a manifest behind the ledger means a registration never landed.

    Source ownership is checked with :func:`lane_ownership`, not a bare
    ``sources`` sweep -- readings record their key under ``read_source`` so a
    paper with both an interview and a verbatim reading is not a false
    conflict (run 029), while two readings of the same paper are a real one
    (run 033). A reading IS required to appear in both registries here,
    because ``read_lane.sync_durable_state()`` mirrors it into both by design
    (run 009); its registry of record is still ``read-episodes.json``.
    """
    report: dict[str, Any] = {
        "ok": True,
        "ledger_episodes": 0,
        "manifest_episodes": 0,
        "missing_from_manifest": [],
        "missing_from_ledger": [],
        "status_divergence": [],
        "benign_move_lag": [],
        "duplicate_sources": {},
        "issues": [],
    }

    def _episodes(path: Path) -> dict[str, Any]:
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            report["ok"] = False
            report["issues"].append(f"cannot read {path.name}: {exc}")
            return {}
        return {str(k): (v or {}) for k, v in (data.get("episodes") or {}).items()}

    ledger = _episodes(LEDGER_PATH)
    manifest = _episodes(MANIFEST_PATH)
    report["ledger_episodes"] = len(ledger)
    report["manifest_episodes"] = len(manifest)

    def _published(rec: dict[str, Any]) -> bool:
        return str(rec.get("status", "")).startswith("published")

    for number in sorted(ledger):
        if number in manifest or not _published(ledger[number]):
            continue
        report["missing_from_manifest"].append(number)
        report["issues"].append(
            f"episode {number} is published in the ledger but absent from the manifest")

    for number in sorted(manifest):
        if number in ledger:
            continue
        report["missing_from_ledger"].append(number)
        report["issues"].append(
            f"episode {number} is in the manifest but absent from the ledger")

    for number in sorted(set(ledger) & set(manifest)):
        a = str(ledger[number].get("status", ""))
        b = str(manifest[number].get("status", ""))
        if a == b:
            continue
        entry = {"episode": number, "ledger": a, "manifest": b}
        if a == "published" and b == "published_and_moved":
            report["benign_move_lag"].append(entry)
            continue
        report["status_divergence"].append(entry)
        report["issues"].append(
            f"episode {number} status disagrees: ledger {a!r} vs manifest {b!r}")

    interview_owners, read_owners = lane_ownership(manifest)
    for key, owners in sorted(duplicate_owners(interview_owners, read_owners).items()):
        report["duplicate_sources"][key] = owners
        report["issues"].append(
            f"source {key} is assigned to multiple episodes: {owners}")

    report["ok"] = not report["issues"]
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


READ_MANIFEST_PATH = PIPELINE / "read-episodes.json"
READ_COVERAGE_FLOOR = 0.995

FIRST_READ_NUMBER = 500


def file_md5(path: Path) -> str:
    """md5 of a file, read in blocks so a 20 MB enclosure is not loaded whole."""
    digest = hashlib.md5()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch_bytes(url: str, timeout: float = 15.0,
                headers: dict[str, str] | None = None) -> tuple[int, bytes, dict[str, str]]:
    """One HTTP GET, returned as (status, body, headers).

    Factored out as a module-level function on purpose: it is the single
    network seam of :func:`deploy_drift`, so a test can replace it with
    ``mock.patch.object(rp, "fetch_bytes", ...)`` and exercise every drift
    class offline. 404 and friends are returned, not raised.
    """
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, b"", dict(exc.headers or {})


def remote_total_size(headers: dict[str, str], status: int,
                      body_length: int) -> int | None:
    """Total deployed size of a file from a byte-range probe's headers.

    A 206 answers with ``Content-Range: bytes 0-0/<total>``, which is the whole
    point of probing one byte instead of downloading an enclosure. A server
    that ignores the Range header answers 200 with the entire body, in which
    case ``Content-Length`` -- or the body itself -- is the total. Returns None
    when neither is available, so an unverifiable size is reported as such
    rather than silently passing.
    """
    content_range = headers.get("Content-Range") or headers.get("content-range") or ""
    match = re.search(r"/([0-9]+)\s*$", content_range)
    if match:
        return int(match.group(1))
    if status == 200:
        length = headers.get("Content-Length") or headers.get("content-length")
        if length and str(length).strip().isdigit():
            return int(str(length).strip())
        if body_length:
            return body_length
    return None


# Files small enough to compare by md5 over a full GET. Everything else
# (enclosures, cover art) is compared by deployed byte length via a one-byte
# range probe, so a drift check costs kilobytes rather than tens of megabytes.
DRIFT_TEXT_SUFFIXES = (".xml", ".md", ".svg", ".txt", ".html", ".json")

# Fallback for _deployable_site_files() when git cannot answer. Mirrors the
# .gitignore rules that actually matter inside feed-site/; kept deliberately
# narrow, since a pattern list that drifts from .gitignore is the very thing
# the git query exists to avoid.
DRIFT_SKIP_PATTERNS = ("*.bak-*", "*.tmp")

# Deployed repo-relative paths that legitimately have no local counterpart.
# Empty here, and that emptiness is the finding: every one of the 77 blobs on
# the deploy branch is a file this tree still produces, so ANY unaccounted path
# is either a retired deliverable still being served or a file that was never
# ours. Add an entry only with a reason -- an exemption is a gate with the sign
# flipped (run 036).
DRIFT_ALLOWED_REMOTE_ONLY: tuple[str, ...] = ()


def _deployable_site_files(site_dir: Path) -> tuple[list[Path], list[str]]:
    """The feed-site files a deploy would actually publish, plus those skipped.

    push_to_remote() copies every file in feed-site/ into the clone and then
    runs ``git add -A``, which **respects .gitignore** -- so a gitignored file
    is copied but never committed, and correctly 404s on the live site. This
    tree's feed-site/ holds two such files (``cover.png.bak-run004``,
    ``cover.svg.bak-run004``), which the sibling show's does not. Iterating
    every file the way the sibling's deploy_drift() does would therefore report
    two permanent false "not deployed" issues against a perfectly clean deploy.

    The deployable set is derived from git rather than from a hardcoded pattern
    list, so it cannot drift from the rules the deploy itself obeys;
    DRIFT_SKIP_PATTERNS is only a fallback for when git is unavailable.
    """
    candidates = sorted(p for p in site_dir.iterdir() if p.is_file())
    if not candidates:
        return [], []
    skipped: list[str] = []
    try:
        proc = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "--stdin"],
                      input="\n".join(str(p) for p in candidates),
                      capture_output=True, text=True, timeout=30)
        # exit 0 = some paths ignored, 1 = none ignored; both are success here.
        if proc.returncode in (0, 1):
            ignored = {line.strip() for line in proc.stdout.splitlines() if line.strip()}
            if ignored:
                skipped = sorted(Path(p).name for p in ignored)
            return [p for p in candidates if str(p) not in ignored], skipped
    except Exception:
        pass
    keep = []
    for p in candidates:
        if any(fnmatch.fnmatch(p.name, pat) for pat in DRIFT_SKIP_PATTERNS):
            skipped.append(p.name)
        else:
            keep.append(p)
    return keep, sorted(skipped)


def list_remote_tree(repo: str | None = None, branch: str = "main",
                     token: str | None = None,
                     timeout: float = 30.0) -> list[str]:
    """Every blob path on the deploy branch, as repo-root-relative strings.

    The second network seam of :func:`deploy_drift`, kept module level so a
    test can replace it with ``mock.patch.object`` and exercise every orphan
    class offline.

    Uses the git tree API rather than crawling HTTP because the question is
    "what is deployed?", and an orphan is by definition a file that no local
    listing and no feed reference will ever name -- so there is nothing to
    crawl from. Raises on any failure: an un-enumerable remote is reported as
    an issue by the caller, never as a pass.
    """
    import urllib.request

    target = (repo or DEPLOY_REPO).removeprefix("https://github.com/").strip("/")
    auth = token or load_deploy_token()
    headers = {
        "Authorization": f"Bearer {auth}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "moral-machines-drift",
    }

    def api(url: str) -> dict[str, Any]:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode())

    head = api(f"https://api.github.com/repos/{target}/branches/{branch}")
    tree_sha = head["commit"]["commit"]["tree"]["sha"]
    tree = api(
        f"https://api.github.com/repos/{target}/git/trees/{tree_sha}?recursive=1")
    if tree.get("truncated"):
        raise ValueError(
            "remote tree listing was truncated; orphan audit would be incomplete")
    return [entry["path"] for entry in tree.get("tree", [])
            if entry.get("type") == "blob"]


def remote_only_paths(remote_paths: list[str], root_dir: Path | str,
                      site_dir: Path | str,
                      allowed: tuple[str, ...] = DRIFT_ALLOWED_REMOTE_ONLY) -> list[str]:
    """Deployed paths that nothing in this local tree accounts for.

    RETARGETED from the sibling show, which accounts for a deployed path by
    flat basename against feed-site/ because its repo holds only that payload.
    This repo deploys the WHOLE project -- episodes/, pipeline/, tests/ and the
    repo docs are all tracked and served -- so the sibling predicate would
    report every nested path as an orphan and make `push` permanently red.

    A deployed path is accounted for when either:
      * the local tree has that exact repo-relative path, or
      * it is a FLAT path that feed-site/ produces (push copies feed-site/*
        into the clone root, so those arrive without their directory).

    Keyed on the full repo-relative path, never the basename alone: a stale
    ``episodes/004/script.md`` must not be excused by an unrelated local file
    of the same name, and a nested path can never collide with the flat
    feed-site namespace.
    """
    root = Path(root_dir)
    site = Path(site_dir)
    allow = set(allowed)
    orphans = []
    for path in remote_paths:
        if path in allow:
            continue
        if (root / path).exists():
            continue
        if "/" not in path and (site / path).exists():
            continue
        orphans.append(path)
    return sorted(orphans)


def deploy_drift(remote: str | None = None, site: Path | None = None,
                 text_only: bool = False, timeout: float = 15.0,
                 orphans: bool | None = None) -> dict[str, Any]:
    """Audit that the deployed site is byte-identical to the local feed-site.

    READ-ONLY, and the cheapest full-stack proof that a deploy is complete.
    Until now this tree's docs asked each slice to hand-roll it as a
    ``curl | md5sum`` pair, which checks ``feed.xml`` alone and is re-typed
    (and re-mistyped) every run.

    The gap it closes is specific and was proved on real code: every remote
    probe in :func:`verify_feed` is an **existence** probe. Show notes, cover
    art and the landing page are checked for HTTP 200 and a few bytes;
    enclosures are checked by ``Content-Range`` total only; and run 056
    compares the deployed feed to the local one by **GUID set**. So a deploy
    whose notes, cover, landing page or feed **text** was rewritten -- or whose
    enclosure bytes were swapped at the same byte length -- returns ok: true
    with an empty issue list, which is the verdict ``publish_local()`` refuses
    on and ``push_to_remote()``'s wait loop breaks on to call a deploy live.

    It is **not** a publication gate: it grants nothing, writes nothing, and
    does not replace ``preflight``/``review_gate``/``verify_feed`` or the read
    lane's fidelity gate. ``verify --remote`` asks whether the live feed parses
    and its enclosures are fetchable; this asks the strictly different question
    of whether the live bytes equal the local bytes.

    Text files (feed.xml, show notes, cover.svg, index.html) are compared by
    md5 over a full GET. Binaries are compared by deployed byte length from a
    one-byte range probe. ``text_only`` skips the binaries entirely, which is
    the right mode for a doc-only or manifest-only change.

    CONVERSE SWEEP (run 079). Everything above -- and every remote probe in
    :func:`verify_feed` -- iterates files that exist LOCALLY and asks whether
    the remote has them. Nothing asked the opposite question: what does the
    remote HAVE that we no longer intend? ``push_to_remote()`` copies
    feed-site/* into the clone and runs ``git add -A``, which stages additions
    and modifications and can never DELETE a path the local tree stopped
    producing. So any file ever deployed stays deployed, served to subscribers,
    with every audit green: a retired episode's enclosure and notes, a stale
    alternate-name feed copy, or a file naming the SIBLING SHOW at the deploy
    root all returned ok: true with an EMPTY issue list -- a verdict
    indistinguishable from a clean deploy, and the verdict
    ``push_to_remote()``'s wait loop breaks on to declare a deploy live.

    This is the only audit in the project that can see an orphan at all. It is
    attempted only when the remote IS the deploy site, because the
    site-to-repo mapping is unknown for any other host. An enumeration failure
    is an ISSUE, never a pass (run 036: a waiver is a gate with the sign
    flipped).
    """
    base = (remote or FEED_BASE).rstrip("/")
    site_dir = Path(site) if site is not None else (ROOT / "feed-site")
    report: dict[str, Any] = {
        "ok": True,
        "remote": base,
        "site": str(site_dir),
        "checked": 0,
        "text_only": bool(text_only),
        "identical": [],
        "md5_mismatch": [],
        "size_mismatch": [],
        "missing_remote": [],
        "unverifiable": [],
        "not_deployed_by_design": [],
        "remote_only": [],
        "orphan_audit": "not attempted",
        "issues": [],
    }
    if not site_dir.is_dir():
        report["ok"] = False
        report["issues"].append(f"site directory not found: {site_dir}")
        return report

    deployable, skipped = _deployable_site_files(site_dir)
    report["not_deployed_by_design"] = skipped

    for local in deployable:
        is_text = local.suffix.lower() in DRIFT_TEXT_SUFFIXES
        if text_only and not is_text:
            continue
        url = f"{base}/{local.name}"
        report["checked"] += 1
        if is_text:
            status, body, _ = fetch_bytes(url, timeout=timeout)
            if status != 200:
                report["missing_remote"].append({"file": local.name, "http": status})
                report["issues"].append(f"{local.name} is not deployed (HTTP {status})")
                continue
            local_md5 = file_md5(local)
            remote_md5 = hashlib.md5(body).hexdigest()
            if local_md5 == remote_md5:
                report["identical"].append(local.name)
            else:
                report["md5_mismatch"].append({
                    "file": local.name, "local_md5": local_md5,
                    "remote_md5": remote_md5,
                    "local_bytes": local.stat().st_size,
                    "remote_bytes": len(body)})
                report["issues"].append(
                    f"{local.name} differs: local md5 {local_md5} vs live {remote_md5}")
            continue
        status, body, headers = fetch_bytes(
            url, timeout=timeout, headers={"Range": "bytes=0-0"})
        if status not in (200, 206):
            report["missing_remote"].append({"file": local.name, "http": status})
            report["issues"].append(f"{local.name} is not deployed (HTTP {status})")
            continue
        total = remote_total_size(headers, status, len(body))
        local_bytes = local.stat().st_size
        if total is None:
            report["unverifiable"].append({
                "file": local.name,
                "problem": "no Content-Range or Content-Length on the range probe"})
            report["issues"].append(
                f"{local.name} deployed size could not be determined")
        elif total == local_bytes:
            report["identical"].append(local.name)
        else:
            report["size_mismatch"].append({
                "file": local.name, "local_bytes": local_bytes,
                "remote_bytes": total})
            report["issues"].append(
                f"{local.name} differs: local {local_bytes} bytes vs live {total}")

    # Converse sweep: anything DEPLOYED that this tree no longer produces.
    # See the docstring -- this is the only audit in the project that can see
    # an orphan at all.
    attempt = orphans
    if attempt is None:
        attempt = base == FEED_BASE.rstrip("/")
        if not attempt:
            report["orphan_audit"] = (
                "not attempted: remote is not the deploy site, so the "
                "site-to-repo mapping is unknown")
    if attempt:
        try:
            remote_paths = list_remote_tree(timeout=max(timeout, 30.0))
        except Exception as exc:  # enumerate failed -> issue, never a pass
            report["orphan_audit"] = f"failed: {type(exc).__name__}: {exc}"
            report["issues"].append(
                f"deployed file listing could not be enumerated: {exc}")
        else:
            extra = remote_only_paths(remote_paths, ROOT, site_dir)
            report["remote_blobs"] = len(remote_paths)
            report["remote_only"] = extra
            report["orphan_audit"] = "completed"
            for path in extra:
                report["issues"].append(
                    f"{path} is deployed but this tree no longer produces it; "
                    f"push stages with `git add -A` and can never delete a "
                    f"retired path, so it is still served to subscribers")

    report["ok"] = not report["issues"]
    return report


def load_read_manifest() -> dict[str, Any]:
    """The read lane's registry of record; ``read_lane.py`` owns this file.

    Returned empty (never raised) when absent or corrupt, because every caller
    here is a read-only audit that must still report on the interview lane.
    """
    try:
        return json.loads(READ_MANIFEST_PATH.read_text())
    except (OSError, ValueError):
        return {}


def is_reading(number: str, read_episodes: dict[str, Any] | None = None) -> bool:
    """Is this episode number a verbatim reading rather than an interview?

    Readings are numbered from 501 and registered in ``read-episodes.json``.
    Either signal is sufficient: the number range alone identifies a reading
    that has not been registered yet (the run-422 class), and the registry
    alone would identify one renumbered outside the range.
    """
    episodes = read_episodes if read_episodes is not None else (load_read_manifest().get("episodes") or {})
    if str(number) in episodes:
        return True
    return bool(re.fullmatch(r"\d+", str(number))) and int(number) >= FIRST_READ_NUMBER




def parse_reading_turns(script: Path) -> list[str]:
    """Spoken turns of a verbatim reading: a single ``**Reader:**`` voice.

    A reading has no Host/Rowan dialogue by design, so parse_turns() raises on
    one. Kept deliberately strict in the same shape: an empty turn or a file
    with no Reader line at all is still an error.
    """
    turns = []
    for line in script.read_text().splitlines():
        m = re.match(r"^\*\*Reader:\*\*\s+(.+?)\s*$", line)
        if m:
            if not m.group(1).strip():
                raise ValueError(f"invalid reading turn in {script}: {line}")
            turns.append(m.group(1).strip())
    if not turns:
        raise ValueError(f"no Reader turns found in {script}")
    return turns


def fidelity_gate(episode: str) -> dict[str, Any]:
    """Read-lane publication gate: the recorded automated word-fidelity result.

    This is the reviewer panel's counterpart for verbatim readings, where there
    is no paraphrase risk to review and the real risk is silent omission. The
    verdict is produced by ``read_lane.py verify`` and recorded in
    pipeline/read-episodes.json; this function only READS it, exactly as
    publish_feed.read_episodes() does, so there is one gate and one verdict
    rather than two implementations that can disagree.

    It grants nothing on a missing or unverified record, and additionally
    requires the inputs the gate scores (source.txt, script.md) to still be on
    disk so the verdict remains reproducible with ``read_lane.py verify``.
    """
    result: dict[str, Any] = {"episode": episode, "ok": False, "issues": [],
                              "registry": "pipeline/read-episodes.json"}
    try:
        registry = json.loads(READ_MANIFEST_PATH.read_text())
    except (OSError, ValueError) as exc:
        result["issues"].append(f"read-episode registry is unreadable: {exc}")
        return result
    record = registry.get("episodes", {}).get(episode)
    if not isinstance(record, dict):
        result["issues"].append("no read-episode registry entry; run read_lane.py build")
        return result
    coverage = record.get("coverage")
    result["coverage"] = coverage
    result["source_words"] = record.get("source_words")
    if not record.get("verified"):
        result["issues"].append("automated fidelity gate has not passed; run read_lane.py verify")
    if not isinstance(coverage, (int, float)):
        result["issues"].append("registry records no word-coverage figure")
    elif coverage < READ_COVERAGE_FLOOR:
        result["issues"].append(f"word coverage {coverage:.3%} is below the {READ_COVERAGE_FLOOR:.1%} floor")
    directory = ROOT / "episodes" / episode
    for name in ("source.txt", "script.md"):
        if not (directory / name).exists():
            result["issues"].append(f"missing {name}; the fidelity verdict is not reproducible")
    # Bind the verdict to the AUDIO it was earned on.
    #
    # verify() compares script.md against source.txt, so it is structurally
    # unable to tell which paper the audio came from (run 032/030's lesson: a
    # gate deriving both sides of its comparison from the same write validates
    # internal consistency, not provenance). Run 040 therefore recorded
    # audio_sha256/audio_bytes beside the verdict -- but nothing ever read
    # them, so they documented the hazard without gating it.
    #
    # It is reachable by an ordinary operator sequence, because
    # read_lane.render_episode() writes episodes/NNN/episode-NNN.mp3 and writes
    # NO registry, while record_verdict() runs only from the CLI `verify`
    # branch: verify (verdict + digest stored) -> build --force for another
    # paper -> render leaves `verified: true` next to a digest of the PREVIOUS
    # audio, and publish_feed.read_episodes() ships on that flag alone.
    #
    # Checked here rather than in a new gate so there stays exactly one read
    # verdict with one owner. It grants nothing: a missing digest is a refusal
    # (an entry predating run 040 must be re-verified, not waived), and the
    # audio must exist and match byte-for-byte.
    recorded_digest = record.get("audio_sha256")
    recorded_bytes = record.get("audio_bytes")
    audio = directory / f"episode-{episode}.mp3"
    result["audio"] = {"recorded_sha256": recorded_digest, "recorded_bytes": recorded_bytes}
    if not audio.exists():
        result["issues"].append(
            f"missing {audio.name}; the verified audio is not on disk")
    elif not isinstance(recorded_digest, str) or not recorded_digest:
        result["issues"].append(
            "registry records no audio_sha256; re-run read_lane.py verify so the "
            "verdict is bound to the rendered audio")
    else:
        actual_digest = sha256(audio)
        actual_bytes = audio.stat().st_size
        result["audio"].update({"sha256": actual_digest, "bytes": actual_bytes})
        if actual_digest != recorded_digest:
            result["issues"].append(
                f"{audio.name} does not match the verified audio "
                f"(recorded {recorded_digest[:12]}..., on disk {actual_digest[:12]}...); "
                f"re-run read_lane.py verify")
        elif isinstance(recorded_bytes, int) and recorded_bytes != actual_bytes:
            result["issues"].append(
                f"{audio.name} is {actual_bytes} bytes but the verdict recorded "
                f"{recorded_bytes}; re-run read_lane.py verify")
    result["ok"] = not result["issues"]
    return result


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
    """Deterministic publication gate.

    Two lanes with different, non-interchangeable contracts:

    * interview episodes -- two-voice Host/Rowan dialogue, the synthetic
      correspondent and AI-summary disclosures, and the three-reviewer panel.
    * verbatim readings (kind == "read") -- a single ``**Reader:**`` voice, no
      Rowan, no synthetic-interview disclosure, and the automated word-fidelity
      gate INSTEAD of the reviewer panel.

    Scoring a reading against the interview rules failed it for *complying with
    the style guide* and, because read_lane.sync_durable_state() registers a
    reading in manifest.json, one registered reading aborted publication of
    every healthy interview episode. The lane is selected from manifest
    ``kind``, the same discriminator publish_feed.py uses; interviews carry no
    ``kind`` key, so anything not explicitly a reading takes the interview
    path unchanged.
    """
    directory = ROOT / "episodes" / episode
    result: dict[str, Any] = {"episode": episode, "ok": False, "issues": [], "checks": {}}
    manifest = load_manifest().get("episodes", {}).get(episode, {})
    is_read = str(manifest.get("kind", "")) == "read"
    result["checks"]["lane"] = "read" if is_read else "interview"
    script, notes = directory / "script.md", directory / "episode-notes.md"
    try:
        turns = parse_reading_turns(script) if is_read else parse_turns(script)
        result["checks"]["reading_turns" if is_read else "dialogue_turns"] = len(turns)
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
    if is_read:
        # The style guide forbids the synthetic-interview disclosure on a
        # verbatim reading and bars Rowan from appearing in one, so requiring
        # either would fail the reading for compliance. Assert their ABSENCE
        # instead, and require the reading's own spoken disclosure.
        if re.search(r"Rowan Field", script_text, re.I):
            result["issues"].append("Dr. Rowan Field must not appear in a verbatim reading")
        if not re.search(r"verbatim reading", script_text, re.I):
            result["issues"].append("verbatim-reading disclosure is absent from script")
        if not re.search(r"automated text-to-speech", script_text, re.I):
            result["issues"].append("automated-text-to-speech disclosure is absent from script")
    else:
        if not re.search(r"fictional.*(?:composite|correspondent)|(?:composite|fictional).*correspondent", script_text, re.I | re.S):
            result["issues"].append("fictional-correspondent disclosure is absent from script")
        if not re.search(r"AI-generated|AI generated", script_text, re.I):
            result["issues"].append("AI-summary disclosure is absent from script")
    keys = source_keys(notes_text)
    # A reading's Zotero key is registered under read_source, not sources, so
    # preflight()'s interview source-ownership model cannot report a false
    # duplicate for a paper that has both an interview and a reading. The
    # citation checks below still apply to it.
    expected_keys = list(manifest.get("read_source", []) if is_read else manifest.get("sources", []))
    result["checks"]["notes_zotero_keys"] = sorted(set(keys))
    # Zero declared source keys waives EVERY check below that iterates them:
    # duplicate ownership, manifest-key-in-notes, and the numbered citation /
    # year / metadata-length / Zotero-link loop. With expected_keys == [] all
    # of those are all-of loops over an empty collection, so they return no
    # findings and preflight reported ok: true with an EMPTY issue list -- the
    # only episode-level check publish_local() runs.
    #
    # Run 049 established this for the interview lane and guarded it inside the
    # interview-only quoted-span block below. But the apparatus here is lane
    # SHARED, so the reading half stayed open; this is run 032's lane-asymmetry
    # axis ("does the other lane here lack a guard this lane holds?") applied
    # to a guard added one run earlier, in the same function.
    #
    # The read lane's reachability is STRONGER, not weaker. An interview's
    # `sources` is hand-written, so an empty list means somebody wrote one. A
    # reading's `read_source` is DERIVED by read_lane.sync_durable_state() as
    # `[item_key] if item_key else []`, with item_key itself read as
    # `entry.get("item_key", "")` -- so a registry entry that never recorded an
    # item key silently becomes read_source: [] with no hand-editing anywhere,
    # and takes the free pass.
    #
    # Both lanes are built FROM a paper, so zero declared sources is a defect
    # in every case and this only ever adds refusals. Each lane is named with
    # the field and registry that actually fixes it.
    if not expected_keys:
        if is_read:
            result["issues"].append(
                "no Zotero source key is declared for this reading, so every "
                "citation check below it is vacuous; record item_key in "
                "pipeline/read-episodes.json and re-run read_lane.py verify "
                "so read_source is mirrored into pipeline/manifest.json")
        else:
            result["issues"].append(
                "no Zotero source keys are declared in the manifest for this "
                "episode, so every citation check below it is vacuous; "
                "register sources in pipeline/manifest.json")
    # Count owners in THIS episode's lane. expected_keys already comes from
    # read_source for a reading, so looking it up in an interview-only map made
    # the count 0 or 1 forever: no number of readings of one paper could ever
    # trip the check.
    interview_owners, read_owners = lane_ownership(load_manifest().get("episodes", {}))
    all_owners = read_owners if is_read else interview_owners
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
        if is_read:
            gate = fidelity_gate(episode)
            result["checks"]["fidelity_gate"] = gate
            if not gate["ok"]:
                result["issues"].extend("fidelity gate: " + issue for issue in gate["issues"])
        else:
            gate = review_gate(episode)
            result["checks"]["review_gate"] = gate
            if not gate["ok"]:
                result["issues"].extend("review gate: " + issue for issue in gate["issues"])
    if not is_read:
        # Quoted-span fidelity: every "..." span in the deliverables must appear
        # in one of the episode's extracted source texts.
        #
        # Run 047 ported pipeline/quoted_span_gate.py and left it with ZERO
        # callers -- reachable only as a hand-typed CLI command. So the one
        # check in this tree that compares a deliverable against the PAPER'S
        # ACTUAL WORDS was not on the publish path, and `publish --episode NNN`
        # could not reach it. Every other check here scores the script against
        # the CITATION RECORD (keys, numbered entries, years, Zotero links),
        # which is why a misquote inside quotation marks passed a three-reviewer
        # panel and every deterministic gate in published episodes 001 and 003.
        # That is run 045's lesson ("ask whether the reader is reachable from
        # the command the operator runs to ship") applied to a whole module.
        #
        # Union-of-sources: an episode may group several papers, so a span is
        # verified if it appears in ANY of them. Scoring per source reports
        # every span quoted from paper A as missing from paper B -- a false
        # positive shaped exactly like a fabrication.
        #
        # A missing source-KEY.txt is an ISSUE, not a waiver: the extracts are
        # gitignored and regenerable, so a tree that lost them must be told.
        result["checks"]["quoted_spans"] = spans_check = {}
        try:
            from quoted_span_gate import extract_spans, verify_text
        except ImportError:  # pragma: no cover - module sits beside this file
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from quoted_span_gate import extract_spans, verify_text
        keys = [str(k) for k in (manifest.get("sources") or [])]
        whitelist = [str(w) for w in (manifest.get("quoted_span_whitelist") or [])]
        spans_check["sources"] = keys
        spans_check["whitelisted"] = len(whitelist)
        # An episode that declares NO sources waived this gate and the whole
        # citation apparatus below it. With keys == [] no source text is
        # loaded, so the `residual` intersection below stays None and every
        # quoted span is VACUOUSLY verified -- a deliverable could quote a
        # sentence present in no paper on earth and preflight returned
        # ok: true with an empty issue list. The same empty list skips the
        # ownership check, the manifest-key-in-notes check and the numbered
        # citation / year / Zotero-link loop.
        #
        # That is run 036's lesson ("a waiver is a gate with the sign
        # flipped") one level up from the comment below it: a missing
        # source-KEY.txt was already an issue rather than a waiver, while
        # declaring no sources at all skipped the check entirely. It is
        # reachable by the ordinary registration gap that hid 042 -- a slice
        # that renders and publishes without writing the manifest entry.
        #
        # An interview is built FROM papers, so zero declared sources is a
        # defect in every case; there is no legitimate interview episode this
        # refuses. Readings are unaffected (this whole block is interview-only
        # and a reading's key lives under read_source).
        # The zero-declared-sources refusal now lives with the lane-shared
        # citation apparatus above, so it covers readings too; keeping a second
        # interview-only copy here would be the open-coded duplicate run 044
        # warns about.
        texts = {}
        for key in keys:
            path = directory / f"source-{key}.txt"
            if path.exists():
                texts[key] = path.read_text(errors="replace")
            else:
                result["issues"].append(
                    f"quoted-span gate: extracted source text is missing for "
                    f"{key} (expected episodes/{episode}/source-{key}.txt); "
                    f"re-fetch it so quoted spans can be verified")
        spans_check["sources_present"] = sorted(texts)
        for name in ("script.md", "episode-notes.md"):
            deliverable = directory / name
            if not deliverable.exists():
                continue
            text = deliverable.read_text()
            residual = None
            for source_text in texts.values():
                missing = set(verify_text(source_text, text, whitelist)["unverified"])
                residual = missing if residual is None else (residual & missing)
            residual = sorted(residual or set())
            # Record whether the spans were actually scored against anything.
            # With no source texts present, `unverified: []` is not a pass --
            # it is an unscored file, and a report that cannot tell the two
            # apart is how this defect read as healthy.
            spans_check[name] = {
                "spans": len(extract_spans(text)),
                "unverified": residual,
                "checked_against_sources": bool(texts),
            }
            for span in residual:
                result["issues"].append(
                    f"quoted-span gate: {name} quotes \"{span}\", which appears "
                    f"in none of this episode's source texts")
    if require_audio:
        audio = list(directory.glob("*.mp3"))
        if len(audio) != 1 or audio[0].stat().st_size == 0:
            result["issues"].append("exactly one non-empty episode MP3 is required")
        else:
            digest = sha256(audio[0])
            result["checks"]["audio"] = {"path": str(audio[0].relative_to(ROOT)), "size": audio[0].stat().st_size, "sha256": digest}
            # Bind the verdict to the AUDIO it was earned on (the interview
            # lane's half of run 042's fix, which landed in the read lane
            # only).
            #
            # This block already computed the digest and compared it to
            # NOTHING, so the gate held the evidence and discarded it. Every
            # other check here scores script.md and episode-notes.md -- the
            # reviewer panel, both spoken disclosures, the citation and
            # evidence-boundary checks -- none of which can tell which
            # episode's audio sits in the directory. render_episode() records
            # the rendered bytes' digest in state.json artifacts.audio_sha256,
            # and reconcile() compares it, but reconcile is NOT in the publish
            # path: publish_local() runs preflight, verify_feed and
            # feed_coverage, and all three inspect the feed's structure. So a
            # swapped mp3 passed the publication gate with an empty issue list
            # and publish_feed.main() re-copied it into feed-site/ for the next
            # push to deploy.
            #
            # It grants nothing. An ABSENT digest is still acceptable: 001-003
            # lost theirs once to the artifacts-overwrite bug and are genuinely
            # published, so refusing a record that predates provenance would be
            # a false failure -- the same policy reconcile() applies. Only a
            # digest that is present and WRONG is refused, which means the mp3
            # on disk is not the mp3 that was rendered and gated.
            recorded = ((load_ledger().get("episodes") or {})
                        .get(episode, {}).get("artifacts") or {}).get("audio_sha256")
            result["checks"]["audio"]["recorded_sha256"] = recorded
            if isinstance(recorded, str) and recorded and recorded != digest:
                result["issues"].append(
                    f"audio does not match the digest recorded at render time "
                    f"(recorded {recorded[:12]}..., on disk {digest[:12]}...); "
                    f"the mp3 was replaced after it was rendered and gated")
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


# Tolerance for the advertised <itunes:duration> against the real decoded
# length. publish_feed.duration() ROUNDS to whole seconds, so a sub-second
# rounding difference is expected and benign; anything beyond a couple of
# seconds means the advertised figure does not describe the file.
DURATION_TOLERANCE_SECONDS = 2.0


def _parse_hhmmss(value: str) -> int | None:
    """Seconds for an HH:MM:SS (or H:MM:SS / MM:SS) duration string."""
    parts = (value or "").strip().split(":")
    if not parts or not all(p.isdigit() for p in parts) or len(parts) > 3:
        return None
    total = 0
    for part in parts:
        total = total * 60 + int(part)
    return total


def _audio_duration_seconds(path: Path) -> float | None:
    """Real decoded duration, or None when the file cannot be decoded.

    publish_feed.duration() parses the same ffmpeg stderr but SWALLOWS a miss,
    returning the literal string "00:00:00" for an undecodable file -- which is
    exactly why the advertised value cannot be trusted as its own evidence.
    """
    try:
        _, imageio_ffmpeg = _tts_imports()
        stderr = subprocess.run(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-i", str(path)],
            capture_output=True, text=True, timeout=120,
        ).stderr
    except Exception:
        return None
    match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", stderr)
    if not match:
        return None
    return (int(match.group(1)) * 3600 + int(match.group(2)) * 60
            + float(match.group(3)))


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
    # LOCKED voices (2026-11-03): Host Ava -3%, Dr. Rowan Field Andrew +18%.
    # Declared before the plan comparison because they are part of the cache
    # key: a voice or rate change must invalidate the parts cache, or the
    # episode ships the previous voice under the new configuration. Nothing
    # downstream inspects the audio's provenance, so no gate can catch it.
    voices = {"host": "en-US-AvaMultilingualNeural", "rowan": "en-US-AndrewMultilingualNeural", "guest": "en-US-AndrewMultilingualNeural"}
    rates = {"host": "-3%", "rowan": "+18%", "guest": "+18%"}
    plan = hashlib.sha256(script.read_bytes()).hexdigest()
    voice_plan = {role: f"{voices[role]}@{rates[role]}" for role in sorted(voices)}
    plan_file = parts / "render-plan.json"
    # Read the plan defensively, mirroring the read lane. A crashed or killed
    # render can leave a truncated plan behind, and a bare json.loads would
    # then abort every later render with JSONDecodeError rather than
    # rebuilding -- a permanently stuck episode that only a hand-deleted file
    # clears. An unreadable plan is treated as no plan, which forces a full
    # re-render: the safe direction.
    old_plan: dict[str, Any] = {}
    if plan_file.exists():
        try:
            old_plan = json.loads(plan_file.read_text())
        except (ValueError, OSError):
            old_plan = {}
    if not isinstance(old_plan, dict):
        old_plan = {}
    if (old_plan.get("script_sha256") != plan
            or old_plan.get("render_text_version") != RENDER_TEXT_VERSION
            or old_plan.get("voices") != voice_plan):
        force = True
        for old in parts.glob("*.mp3"):
            old.unlink()
    edge_tts, imageio_ffmpeg = _tts_imports()
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
            atomic_json(plan_file, {"schema_version": 1, "render_text_version": RENDER_TEXT_VERSION, "script_sha256": plan, "voices": voice_plan, "turns": len(turns), "parts": [p.name for p in files], "completed_at": utc_now()})
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


def _feed_item_number(item: "ET.Element") -> str:
    """Episode number for a feed item, read from its GUID then its enclosure.

    Same derivation feed_coverage() uses, and stable across the interview
    naming scheme and the read lane's `-reading` suffix.
    """
    guid = (item.findtext("guid") or "").strip()
    enclosure = item.find("enclosure")
    url = (enclosure.get("url") or "") if enclosure is not None else ""
    found = re.findall(r"episode-(\d+)", guid) or re.findall(r"episode-(\d+)", url)
    return found[0] if found else ""


PRODUCTION_TRANSITIONS = frozenset({
    "rendering", "rendered", "review_pending", "reviewed", "verified",
})


def _produced_in_pipeline(number: str, rec: dict[str, Any]) -> bool:
    """True if this episode shows positive evidence of local production.

    Either the ledger record passed through a production state, or a script
    exists on disk. The disk test is what still holds when a ledger rebuilt
    from manifest.json has erased the transition history (load_ledger()'s
    bootstrap maps published_and_moved -> "published" with a single synthetic
    transition).
    """
    for item in rec.get("transitions") or []:
        if isinstance(item, dict) and str(item.get("to", "")) in PRODUCTION_TRANSITIONS:
            return True
    return (ROOT / "episodes" / str(number) / "script.md").exists()


def decode_png(data: bytes) -> dict[str, Any]:
    """Decode a PNG far enough to prove a client can render it. Stdlib only.

    Returns ``{"ok": bool, "format": str|None, "width": int|None,
    "height": int|None, "error": str|None}``. Never raises: a caller inside
    verify_feed() must report a bad cover as an issue, not crash the audit.

    The walk is a real decode, not a sniff. It verifies the 8-byte signature,
    walks every chunk honouring its declared length, checks each chunk's
    CRC-32 against the stored value, reads width/height/bit-depth/colour-type
    out of IHDR, requires IDAT to be present, requires the stream to end with
    IEND, and zlib-decompresses the concatenated IDAT payload. Truncation,
    NUL-fill, a wrong container and silent corruption are each caught by a
    different arm, which is why the arms are kept separate.
    """
    out: dict[str, Any] = {"ok": False, "format": None, "width": None,
                           "height": None, "error": None}
    if not data:
        out["error"] = "file is empty"
        return out
    if not data.startswith(PNG_SIGNATURE):
        # Name the container we actually got, so the issue is actionable
        # rather than "not a PNG". A JPEG saved as cover.png is the real
        # operator mistake this arm exists for.
        if data[:3] == b"\xff\xd8\xff":
            out["format"] = "jpeg"
        elif data[:6] in (b"GIF87a", b"GIF89a"):
            out["format"] = "gif"
        elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            out["format"] = "webp"
        elif data[:2] == b"BM":
            out["format"] = "bmp"
        elif data.lstrip()[:5] == b"<?xml" or b"<svg" in data[:512]:
            out["format"] = "svg"
        out["error"] = (f"file is a {out['format']}, not a PNG"
                        if out["format"] else
                        "file does not start with the PNG signature")
        return out
    out["format"] = "png"
    pos = len(PNG_SIGNATURE)
    seen_ihdr = False
    seen_iend = False
    idat = bytearray()
    while pos < len(data):
        if pos + 8 > len(data):
            out["error"] = (f"file is truncated: {len(data) - pos} trailing "
                            f"bytes cannot hold a chunk header")
            return out
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        ctype = data[pos + 4:pos + 8]
        body_at = pos + 8
        if body_at + length + 4 > len(data):
            out["error"] = (f"file is truncated inside the "
                            f"{ctype.decode('latin-1')} chunk: it declares "
                            f"{length} bytes but only "
                            f"{max(0, len(data) - body_at)} remain")
            return out
        body = data[body_at:body_at + length]
        (stored_crc,) = struct.unpack(">I", data[body_at + length:body_at + length + 4])
        if zlib.crc32(ctype + body) & 0xFFFFFFFF != stored_crc:
            out["error"] = (f"the {ctype.decode('latin-1')} chunk fails its "
                            f"CRC-32, so the file is corrupt")
            return out
        if ctype == b"IHDR":
            if length < 13:
                out["error"] = "the IHDR chunk is too short to hold a size"
                return out
            w, h, depth, colour = struct.unpack(">IIBB", body[:10])
            out["width"], out["height"] = int(w), int(h)
            if w == 0 or h == 0:
                out["error"] = f"the image declares a zero dimension {w}x{h}"
                return out
            if depth not in (1, 2, 4, 8, 16):
                out["error"] = f"the image declares an invalid bit depth {depth}"
                return out
            if colour not in (0, 2, 3, 4, 6):
                out["error"] = f"the image declares an invalid colour type {colour}"
                return out
            seen_ihdr = True
        elif ctype == b"IDAT":
            idat += body
        elif ctype == b"IEND":
            seen_iend = True
        pos = body_at + length + 4
        if seen_iend:
            break
    if not seen_ihdr:
        out["error"] = "the file carries no IHDR chunk, so it declares no size"
        return out
    if not idat:
        out["error"] = "the file carries no IDAT chunk, so it holds no pixels"
        return out
    if not seen_iend:
        out["error"] = "the file never reaches its IEND chunk, so it is truncated"
        return out
    try:
        if not zlib.decompress(bytes(idat)):
            out["error"] = "the image data decompresses to nothing"
            return out
    except zlib.error as exc:
        out["error"] = f"the image data will not decompress: {exc}"
        return out
    out["ok"] = True
    return out


def _legacy_episode_numbers() -> set[str]:
    """Episodes that predate this pipeline, per the durable ledger plus disk.

    A waiver must rest on evidence of what it waives. Keying "imported history"
    on the ledger status literal "published" alone does NOT establish that:
    publish_local() writes exactly that status (verified -> published) and the
    load_ledger() bootstrap maps published_and_moved -> "published", so every
    episode produced here sits at it between publish and the Zotero move, and a
    rebuilt ledger puts the whole catalogue there at once. That demoted a
    fully-gated episode's missing-notes failure to a warning.

    So require all three: the literal status "published" (never the published*
    family), no in-pipeline production transition, and no script on disk. The
    first keeps run 036's test; the other two are positive evidence the episode
    was never produced here, and can only narrow the set.
    """
    try:
        ledger = json.loads(LEDGER_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return set()
    legacy = set()
    for number, rec in (ledger.get("episodes") or {}).items():
        if not isinstance(rec, dict) or rec.get("status") != "published":
            continue
        if _produced_in_pipeline(str(number), rec):
            continue
        legacy.add(str(number))
    return legacy


# Tolerance for the advertised <pubDate> against the production event the
# durable ledger records. publish_feed.py formats that timestamp to whole
# seconds, so the two should agree exactly; the allowance only absorbs
# formatting and timezone rounding, and is far below the 2.5-month drift the
# LEGACY_PUB_DATE sentinel produces.
PUBDATE_TOLERANCE_SECONDS = 120.0
# How far ahead of now a pubDate may sit before it is a defect. A feed is
# sorted by this field, so a future date pins an item to the top of every
# client forever; the allowance is for clock skew between this container and
# the deploy, not for scheduling.
PUBDATE_FUTURE_ALLOWANCE_SECONDS = 86400.0

# The feed's SYNDICATION ENVELOPE -- the five fields that tell a podcast
# client what KIND of document this is and how to read it:
#
#   <rss version="2.0">     the syndication format itself
#   xmlns:itunes=...        binds every itunes: field in the feed
#   xmlns:content=...       binds <content:encoded>, the published show notes
#   <enclosure type=...>    the audio MIME type, per item
#   <guid isPermaLink=...>  whether the GUID is an identity or a URL, per item
#
# Until run 071 NOTHING read any of them. robust_pipeline.py did not contain
# the strings "audio/mpeg", "isPermaLink" or "xmlns" on a single code line;
# the two namespace URIs appeared only as ET lookup helpers, never as a value
# compared against what the feed declares.
#
# This is the run-042/045/056/057/058/062/063/064/065/069/070 axis -- an
# advertised field with zero readers -- but one level ABOVE every previous
# instance. Those runs enumerated the channel's and the items' fields; this is
# the envelope that decides whether a client can read those fields at all. The
# previous runs asked "is each advertised value correct?"; the unread question
# was "is this document still an RSS 2.0 podcast feed?".
#
# Each class ships ok: true with an EMPTY issue list -- the verdict
# publish_local() refuses on and push_to_remote()'s wait loop breaks on to
# declare a deploy live:
#
#   * version "1.0" or absent: not RSS 2.0, so a strict client rejects the
#     whole feed and every episode disappears at once.
#   * xmlns:content bound to a wrong URI: <content:encoded> lands in a foreign
#     namespace, so the show notes -- a PUBLISHED DELIVERABLE carrying both
#     mandated disclosures -- are invisible to every client. Run 064's gate
#     stays green through it, because that gate finds the element with an
#     `x.tag.endswith("encoded")` portability fallback, which matches
#     regardless of which namespace the tag resolved into. A fallback written
#     for robustness masks the namespace defect exactly.
#   * xmlns:itunes bound to a wrong URI is caught only INCIDENTALLY, by run
#     068's channel-attribution arm reporting the fields as ABSENT when they
#     are present under the wrong namespace -- a true refusal with a
#     misleading message. Named here so the diagnosis points at the binding.
#   * type="video/mp4" or absent: a podcast client refuses to play an
#     enclosure whose declared type it does not handle, so the episode is
#     listed and unplayable.
#   * isPermaLink="true" (or absent, which RSS DEFAULTS to true): the client
#     reinterprets "moral-machines-episode-001" as a relative URL instead of a
#     permanent identity. GUID identity is what this show's docs call a hard
#     bug when it collides; this is the same field's OTHER half.
#
# FORM MATCHED PER FIELD (runs 066/068/070): all five are enumerated values
# from a closed set, so each is compared EXACTLY against the one legal value
# and a wrong-case variant is refused separately and named -- an envelope is
# machine-read, so "AUDIO/MPEG" is not a copy edit, it is a different string
# to a parser.
#
# No legacy waiver (run 036): the envelope is a property of the syndication
# format, not of any episode, so no episode's provenance can exempt it.
RSS_REQUIRED_VERSION = "2.0"
RSS_REQUIRED_NAMESPACES = {
    "itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
    "content": "http://purl.org/rss/1.0/modules/content/",
}
ENCLOSURE_REQUIRED_TYPE = "audio/mpeg"
GUID_REQUIRED_ISPERMALINK = "false"

# Every absolute URL the feed advertises -- the per-item <enclosure url>, the
# channel and per-item <itunes:image href>, the channel <image><url> and
# <link> -- is the only thing a subscriber ever resolves. Until run 063 NOTHING
# read the scheme, host or directory of any of them: every check in
# verify_feed() reduces an advertised URL to `Path(urlparse(u).path).name` and
# then rebuilds the URL it actually probes from FEED_BASE/`remote`. So the
# checks verify this tree's intentions against this tree's own base and are
# structurally unable to notice that the feed points somewhere else.
#
# publish_feed.py carries its own hardcoded BASE_URL and robust_pipeline.py
# carries FEED_BASE; the two were never related by any reader, so a drift
# between them -- or a wrong repo slug, a foreign host, or a relative URL that
# is invalid in RSS -- shipped green. Worst case is a cross-show prefix, which
# would hand Moral Machines subscribers Human in the Loop's audio: the GUID
# collision this show's docs call a hard bug, arriving through the URL instead.
#
# This is the run-042/045/057/058/062 axis on its last unread dimension. Those
# runs enumerated every advertised FIELD; the field's VALUE was still only ever
# read for its last path segment.
EXPECTED_ADVERTISED_BASES = (FEED_BASE,)

# A prefix that must never appear in this show's feed: the sibling show's repo.
# The two shows share this pipeline's code, and a retargeting slip in either
# BASE_URL constant is exactly how one would advertise the other's assets.
FORBIDDEN_ADVERTISED_SUBSTRINGS = ("human-in-the-loop",)


# The <guid> VALUE. A GUID is the subscriber's PERMANENT IDENTITY for an
# episode: a podcast client keys its played/downloaded/queued state on it, so a
# changed GUID re-delivers an old episode as new, and a COLLIDING GUID makes one
# episode shadow another. This show's docs call a cross-show GUID collision "a
# hard bug".
#
# Until run 065 nothing read the value. Every consumer reduced it to something
# else:
#
#   _feed_item_number()  re.findall(r"episode-(\d+)", guid) or ... url
#   verify_feed()        local_guids vs remote_guids  (run 056, set equality)
#   verify_feed()        len(guids) != len(set(guids)) (duplicates only)
#   feed_coverage()      the same episode-(\d+) derivation
#
# So the PREFIX was unread, the lane SUFFIX was unread, and the GUID's episode
# number was never compared against the enclosure's -- the `or` short-circuits,
# so once the guid yields digits the URL is never consulted. robust_pipeline.py
# did not contain the string "moral-machines" at all.
#
# Run 063 added FORBIDDEN_ADVERTISED_SUBSTRINGS for exactly this cross-show
# hazard but scoped it to advertised URLs, one field away from the field the
# docs name as the hard bug. This is the run-042/045/056/057/058/062/063/064
# axis on the last advertised field with no reader -- and the only one that is
# the episode's IDENTITY rather than one of its assets.
#
# publish_feed.py builds an interview GUID as f"moral-machines-{guid}" over
# f"episode-{num}", and a reading's as f"moral-machines-{rec['guid']}" over
# read_lane's f"episode-{number}-reading-{item_key}". Both are checked here
# against the lane the RECORD declares, never against the episode number
# (run 036), and with no legacy waiver: an import's GUID is its identity too.
GUID_REQUIRED_PREFIX = "moral-machines-"
GUID_READING_MARKER = "-reading"


# The item's ADVERTISED ORDINAL and KIND -- <itunes:episode> and
# <itunes:episodeType>.
#
# Every podcast client sorts the feed by the advertised episode number and
# prints it beside the title; episodeType tells the client whether an item is
# a `full` episode, a `trailer` or `bonus` (Apple pins a trailer OUTSIDE the
# numbered run, so a mislabelled episode disappears from the sequence a
# listener follows). publish_feed.py emits both on every item --
# <itunes:episode>{int(num)}</itunes:episode> and a hardcoded `full` -- and
# until run 069 NOTHING read either value.
#
# The sharp part is that <itunes:episode> HAD a reader and run 036 REMOVED it:
# it was keyed on the value "1" as a legacy waiver, which is not what the field
# means, and run 036 was right to delete that use. Nothing replaced it. So the
# field went from misread to unread, and a defect in it has been shippable
# since -- verify_feed() returning ok: true with an EMPTY issue list, which is
# exactly the verdict publish_local() refuses on and push_to_remote()'s wait
# loop breaks on to declare a deploy live.
#
# Scored against the GUID, never against the feed's own ordering: the GUID is
# this show's durable identity for an episode (run 065) and _feed_item_number()
# already derives the number from it. That makes the check a cross-field
# AGREEMENT test rather than a second opinion about what the number should be.
#
# No legacy waiver (run 036): an import's advertised ordinal is what a
# subscriber's client sorts it by just the same, and a waiver is a gate with
# the sign flipped.
EPISODE_TYPE_REQUIRED = "full"
EPISODE_TYPE_ALLOWED = ("full", "trailer", "bonus")


# The ITEM'S OWN ARTWORK REFERENCE and CONTENT RATING -- the per-item
# <itunes:image href=...> and <itunes:explicit>.
#
# publish_feed.py emits BOTH on every item it writes, in BOTH lanes (the
# interview line and the reading line each end
# `...<itunes:explicit>false</itunes:explicit><itunes:image href="{BASE_URL}/
# cover.png"/></item>`), and until run 072 nothing read either per-item value.
#
# Why the two existing guards do not reach them, which is the whole finding:
#
#   * Run 057 gated COVER ART, and its check is a document-wide SET UNION over
#     every image reference in the feed, which it then resolves to FILENAMES
#     and probes for existence. So it answers "do the referenced files exist",
#     not "does each item advertise artwork". Delete the artwork reference from
#     every item -- or from every item AND the channel -- and the surviving
#     <image><url> text node repopulates the union, the check still reports
#     files=['cover.png'], and the feed ships green. Its only absence arm is
#     `not cover_refs`, which an aggregate can satisfy while every item is
#     bare. A REPOINTED href IS caught, incidentally, because a new filename
#     enters the union; a REMOVED or EMPTIED one puts nothing in the set to
#     probe. An aggregate check cannot gate a per-element requirement.
#   * Run 063 gated an advertised URL's BASE and its absoluteness, so a
#     cross-show or relative item artwork URL is refused -- but a MISSING one
#     advertises no URL at all and is outside that guard by construction.
#   * Run 070 gated the CHANNEL's <itunes:explicit>. The item field of the
#     SAME NAME had no reader: run 032's lane-asymmetry axis rotated onto the
#     feed's two levels, exactly as run 067 found for <description>.
#
# That verdict is what publish_local() refuses on and what push_to_remote()'s
# wait loop breaks on to declare a deploy live, and an intact feed was proven
# INDISTINGUISHABLE from all ten mutation classes (same check-name list, same
# ok, same empty issue list).
#
# Form matched per field (runs 066/068/070). Artwork is an ASSET REFERENCE, so
# it is required to be present, non-empty and -- because run 057 probes files
# and run 063 probes bases -- to name the same artwork the channel advertises,
# which is a cross-field AGREEMENT test rather than a second opinion about
# which file is correct. The rating is an ENUMERATED value, so it is compared
# exactly against a closed set, with a wrong CASE refused separately and named
# as case (a rating is machine-read, like the syndication envelope in run 071).
#
# No legacy waiver (run 036): an imported item is rendered by the same clients,
# and an item with no artwork or a wrong rating is wrong for an import too.
ITEM_ARTWORK_REQUIRED = True


# The item's ADVERTISED SHOW-NOTES LINK -- the href inside <content:encoded>.
#
# publish_feed.py emits one on every item in both lanes (notes_html() writes
# `<a href="episode-NNN-notes.md">` and read_notes_html() the `-reading-notes`
# form), and the show notes are a PUBLISHED DELIVERABLE: they carry the
# unabridged disclosure, the evidence boundaries and every numbered citation
# with its Zotero link, deliberately left in full when David shortened the
# SPOKEN disclosure to one sentence. The link is the only route a listener has
# to them from a podcast client.
#
# Until this run the href was READ but never SCORED. The one block that
# touches it pulls each href out of the CDATA, reduces it to
# `Path(urlparse(href).path).name`, and asks only whether that filename
# exists locally / returns HTTP 200 live. So the VALUE -- which episode it
# names, whether it is there at all, and which SHOW's site it points at --
# was gated by nothing, and three classes shipped with verify_feed()
# returning ok: true and an EMPTY issue list, the verdict publish_local()
# refuses on and push_to_remote()'s wait loop breaks on to declare a deploy
# live:
#
#   * REPOINTED AT ANOTHER EPISODE. Episode 001 advertising
#     `episode-003-notes.md` sends every listener to the wrong paper's
#     citations, boundaries and Zotero links. The existence probe is
#     SATISFIED, because the file it names is a real published deliverable.
#   * ABSENT ENTIRELY. With no href the loop body never executes, so the
#     item's notes are probed zero times -- a check that iterates what it
#     finds cannot see what is missing (run 041's lesson, here per item).
#     The disclosure guard (064) still passes, because the mandated PHRASES
#     are all present; only the route to the full notes is gone.
#   * REPOINTED AT THE SIBLING SHOW. An absolute
#     absolute URL pointing at the SIBLING SHOW's Pages site is the
#     documented hard bug, and
#     it is the case the two neighbouring guards structurally cannot reach:
#     run 063's advertised_base iterates XML ATTRIBUTES plus `url`/`link`
#     ELEMENT TEXT, and this href is neither -- it lives inside a CDATA text
#     blob, outside that guard by construction. Meanwhile the existence
#     probe collapses the cross-show URL to its local filename and passes it.
#
# Scoped by control (run 073): an href naming a file that does NOT exist is
# already refused by the existence arm, so the unread classes are all
# RIGHT-SHAPE WRONG-TARGET plus outright absence -- the same
# measured-but-not-interpreted line run 058 drew for audio and run 074 for
# the cover, rotated onto a LINK: a probe that proves a target exists says
# nothing about whether it is the RIGHT target.
#
# Form matched per field (runs 066/068/070/074). A notes link is a
# CROSS-REFERENCE, so it is scored against the item's own identity -- the
# GUID-derived number, this show's durable identity for an episode (run 065)
# -- making it an AGREEMENT test rather than a second opinion about which
# file is correct. Both lane spellings are accepted for a reading, since
# publish_feed.py derives the reading's base independently.
#
# No legacy waiver (run 036): an imported episode's notes are reached by the
# same link in the same client, and a waiver is a gate with the sign flipped.
SHOW_NOTES_LINK_REQUIRED = True


# The CHANNEL'S OWN IDENTITY -- the show's name.
#
# Runs 056-065 enumerated and gated every advertised PER-ITEM field (the
# deployed item set, cover art, duration, pubDate, URL base, written
# disclosure, GUID) and the channel's ASSETS (the artwork href, the image
# url, index.html's existence and its episode list). Nothing read the
# channel's identity TEXT, in any of the four slots publish_feed.py writes
# it to:
#
#   <channel><title>              the show's name in every podcast client
#   <channel><image><title>       the artwork's caption
#   index.html <title>            the deployed landing page's name
#   index.html <h1>               the landing page's heading
#
# Those are the EXACT FOUR SLOTS run 004 found still reading "Human in the
# Loop: Moral Machine Edition" after this tree was cloned from the sibling
# show, and retargeted BY HAND. Nothing has held them since: a retargeting
# slip, a bad merge from the sibling tree, or an edit to publish_feed.py's
# hardcoded strings re-ships the sibling show's name to subscribers, and
# verify_feed() returned ok: true with an EMPTY issue list on it -- the
# verdict publish_local() refuses on and push_to_remote()'s wait loop breaks
# on to declare a deploy live.
#
# Run 063 installed FORBIDDEN_ADVERTISED_SUBSTRINGS for exactly this
# cross-show hazard, but scoped it to advertised URLs AND expressed it in
# SLUG form ("human-in-the-loop"), which cannot match the sibling show's
# PROSE name ("Human in the Loop") even where it is applied. So the module
# discusses this hazard by name in two places and held no test on the field
# that carries it -- run 042's lesson (a property a fix names but no gate
# reads) on the show's identity rather than on one of its assets.
#
# Checked against SHOW_TITLE, the name this tree owns, and against the
# sibling show's prose name. The channel title and the artwork caption must
# agree, and the landing page must name the same show as the feed: those two
# are generated from the same publish_feed.py constants, so a disagreement
# means a hand-edit or a partial write and should never be found by a
# listener. No legacy waiver (run 036): an imported episode is still carried
# by this show's feed, and a feed with the wrong name or no name is wrong for
# an import too.
# The channel's STRUCTURAL NAVIGATION and ARTWORK CONTAINER -- <channel><link>,
# the <channel><image> block itself, and its <url> and <link> children.
#
# These are not fields a client renders as prose; they are how a subscriber
# LEAVES the feed. <channel><link> is the show's homepage: every podcast client
# exposes it as the "visit website" affordance, and a directory submission uses
# it as the show's canonical page. <image><url> is the RSS 2.0 artwork a
# non-iTunes client renders, and <image><link> is where that artwork clicks
# through to.
#
# Until run 073 NOTHING read any of them. Every reader reduced them to
# something else, or skipped them entirely:
#
#   verify_feed() cover_art   a document-wide SET UNION over image refs,
#                             reduced to Path(urlparse(h).path).name and
#                             probed for existence -- so a REMOVED or EMPTIED
#                             <image><url> is repopulated by the surviving
#                             per-item <itunes:image href> and the union still
#                             reports files=['cover.png']
#   verify_feed() show_identity  guards its whole artwork arm behind
#                             `if channel_image is not None`, so a wholly
#                             ABSENT <image> block skips every artwork check
#                             rather than failing one
#   verify_feed() advertised_base  collects node.text for any tag ending in
#                             "url"/"link" and checks the HOST and DIRECTORY --
#                             so a <link> repointed at this show's own
#                             episode-001.mp3 is under the expected base and
#                             passes, and an ABSENT <link> advertises nothing
#                             and is outside that guard by construction
#
# This is run 072's per-element-vs-aggregate lesson with the granularity
# inverted. Run 072 found a field gated in aggregate and unread per element;
# here the per-element arm EXISTS and is skipped by its own presence guard,
# while the aggregate arm is satisfied by a DIFFERENT element's contribution.
# A presence guard written to avoid a crash is structurally unable to gate
# presence.
#
# publish_feed.py emits all four unconditionally from its one BASE_URL
# constant, so any disagreement is a hand-edit or a partial write. No legacy
# waiver (run 036): a dead homepage and missing RSS artwork are wrong for an
# import too, and a waiver is a gate with the sign flipped.
SHOW_HOMEPAGE = FEED_BASE + "/"


SHOW_TITLE = "Moral Machines"
# The sibling show's PROSE name, as it would appear in an identity field --
# distinct from FORBIDDEN_ADVERTISED_SUBSTRINGS' slug form, which is what a
# URL or a GUID carries.
FORBIDDEN_SHOW_TITLES = ("Human in the Loop",)

# The channel's own BLURB -- <channel><description> -- and the fifth slot run
# 004 retargeted off the sibling show by hand.
#
# Run 066 gated the four show-NAME slots and closed "the channel's identity
# text". This field was outside that: it is the show's self-description, which
# every podcast client renders beside the artwork as the show description, and
# it had ZERO readers. The item-level <description> of the SAME NAME is gated
# (run 038), so the asymmetry is channel-vs-item on one field name -- run 032's
# lane-asymmetry axis rotated onto the feed's two levels.
#
# Neither existing guard reaches it. FORBIDDEN_SHOW_TITLES is applied only to
# the title fields, and FORBIDDEN_ADVERTISED_SUBSTRINGS is SLUG form scoped to
# advertised URLs. Worse, the sibling show's blurb names neither show, so even
# applying both guards here unscoped would still ship it green -- a blurb needs
# a guard on its OWN content, which is run 066's "a guard's form must match the
# field's form" one step further: the same hazard needs a third representation.
#
# Form chosen to match the field. A title is exact, so run 066 compares it
# exactly; a blurb is editorial prose that is legitimately reworded, so an
# exact-match guard would false-fail on ordinary copy edits. Instead: it must
# be present and non-empty, must carry this show's durable project anchor, must
# not carry the sibling show's distinctive blurb phrasing or either show name,
# and must not be unfilled placeholder text. No legacy waiver (run 036) -- a
# show with no description, or with another show's description, is wrong for an
# import too.
#
# Deliberately NO required-content arm. An earlier draft of this gate demanded
# a project anchor ("NIH SEPA") in the blurb, and 16 pre-existing fixtures in
# four other gate suites failed on it -- the evidence that it mandated
# editorial CONTENT instead of detecting an identity defect. A blurb may
# legitimately describe the topic without naming the grant, and the topic
# itself may broaden (the parent Zotero collection already reaches past AV
# ethics into bioethics). The run-004 clone regression -- the hazard this gate
# exists for -- is caught by the sibling-blurb-phrase and sibling-name arms,
# which test what is WRONG rather than prescribing what must be said. Run 029's
# rule decided it: when a suite fails, establish which side is wrong before
# editing either.
# The sibling show's blurb, by its distinctive phrase. Deliberately a phrase
# from the blurb's own content, because the sibling's blurb names neither show
# and so is invisible to every name-based guard.
FORBIDDEN_SHOW_DESCRIPTIONS = ("learning, technology, and human judgment",)
# Unfilled-template sentinels, in the same spirit as duration()'s "00:00:00"
# and the LEGACY_PUB_DATE fallback: a value that means "nobody wrote this yet".
PLACEHOLDER_DESCRIPTION_TOKENS = ("todo", "tbd", "fixme", "lorem ipsum",
                                  "describe this podcast", "your show here",
                                  "xxx")

# The channel's ATTRIBUTION and CLASSIFICATION block -- <language>,
# <copyright>, <itunes:author>, <itunes:type>, <itunes:category> and the
# channel-level <itunes:explicit>.
#
# publish_feed.py writes all six on every feed it builds, and verify_feed()
# read NONE of them. Runs 056-069 each closed one advertised field with no
# reader; this is the whole remaining block, and it is the show's own
# bibliographic identity rather than one asset's address.
#
# What each failure costs a subscriber, which is why these are issues and not
# warnings:
#   <language>      directory language routing and the client's locale
#   <copyright>     the rights line; a WRONG holder misattributes the work
#   <itunes:author> the show's author line, rendered beside the title
#   <itunes:type>   episodic vs serial; 'serial' makes a client present the
#                   feed OLDEST-FIRST, silently reordering the whole catalogue
#   <itunes:category> the directory category; absent = uncategorised
#   <itunes:explicit> the content rating
#
# SHARPEST, and the reason this block is not cosmetic: <itunes:author> is an
# IDENTITY field that run 066's FORBIDDEN_SHOW_TITLES never reaches. Run 066
# gated the four show-NAME slots and the repro for this run proves the sibling
# show's prose name can sit in <itunes:author> with ok: true and an empty issue
# list. So the cross-show identity hazard run 063 installed a guard for, and
# run 066 extended to a second representation, has a THIRD slot -- run 066's
# "a guard's form must match the field's form" with the axis moved from the
# field's FORM to the field's LOCATION.
#
# Form chosen per field (run 066/068's rule). A language code, an iTunes type
# and an explicit flag are ENUMERATED, so they are compared exactly and
# case-insensitively against a closed set -- a wrong-case value is still a
# defect but is reported as such rather than as an unknown value. A copyright
# holder and an author are PROSE naming an institution, so they are required
# to be non-empty, to name the holder this tree owns, and to be free of the
# sibling show's identity; they are NOT compared exactly, because a rights line
# is legitimately reworded. A category is compared exactly against Apple's
# own vocabulary spelling, because a typo there is silently uncategorised.
#
# No legacy waiver (run 036): these are CHANNEL fields, so they are not a
# property of any one episode and an imported episode cannot make the show's
# own language, rights line or category wrong-but-acceptable.
SHOW_LANGUAGE = "en-us"
# The institution this show's rights line and author line must name. Matched
# as a SUBSTRING, case-insensitively, so "(c) 2026 Field Day Lab, UW-Madison"
# and "Copyright 2026, Field Day Lab" both pass while a different lab fails.
SHOW_COPYRIGHT_HOLDER = "Field Day Lab"
SHOW_ITUNES_AUTHOR = "Field Day Lab"
# <itunes:type>: Apple defines exactly two values. 'serial' would present the
# feed oldest-first, which is wrong for this show and invisible locally.
REQUIRED_ITUNES_TYPE = "episodic"
ALLOWED_ITUNES_TYPES = ("episodic", "serial")
# <itunes:category text="...">: the value is an ATTRIBUTE, not element text,
# which is why an element-text sweep over the feed never saw this field.
REQUIRED_ITUNES_CATEGORY = "Education"
# <itunes:explicit>: Apple accepts only these two spellings.
REQUIRED_ITUNES_EXPLICIT = "false"
ALLOWED_ITUNES_EXPLICIT = ("true", "false")

# ---------------------------------------------------------------------------
# COVER ART INTEGRITY. Run 057 wired the first reader for the artwork and
# stopped at EXISTENCE: present, non-empty, the tree-root copy equal to the
# feed-site copy, remote HTTP 200. Run 058 found the identical shape one
# asset over -- "enclosures are verified by byte length, which garbage at the
# right size satisfies", closed for audio by making <itunes:duration> the one
# check that proves an enclosure is real, playable audio -- and the artwork
# stayed on the measured-but-never-decoded side of that line.
#
# Proved against the unmodified module (run 074): four single-fault covers
# each returned ok: true with an EMPTY issue list, and an intact cover was
# INDISTINGUISHABLE from all four.
#
#   * a file of pure NUL bytes at exactly the right length -- local_bytes
#     reports healthy, site_sha256 == root_sha256 because BOTH copies are
#     garbage, and no podcast client can render it
#   * a TRUNCATED PNG, which keeps the \x89PNG signature, so any magic-byte
#     sniff passes and only a real decode catches it
#   * a JPEG saved as cover.png -- decodes fine, so a decode-only check is
#     not enough; the FORMAT must be read, since all five slots advertise .png
#   * a valid, decodable 200x120 PNG -- Apple rejects the whole show for a
#     non-square or undersized cover, and nothing here read width or height
#
# Why no other audit covers it (scoped by control, run 073's rule):
# feed_coverage() audits enclosures; registry_audit() relates ledger to
# manifest; deploy_drift() compares LOCAL bytes to REMOTE bytes, so identical
# garbage on both sides is "no drift"; and publish_feed.py has no copy site
# for the cover, which is exactly why a bad export lands in both copies at
# once. That verdict is publish_local()'s gate and push_to_remote()'s success
# criterion, so the show shipped unrenderable artwork and reported itself live.
#
# Stdlib only, deliberately: this tree's interpreter is 3.14, where `imghdr`
# was REMOVED, and PIL is not a dependency. A zlib+struct chunk walk is the
# whole of the format we advertise, so the gate adds no install surface.
#
# No legacy waiver (run 036): an advertised asset a client cannot render is a
# defect for an import too.
# ---------------------------------------------------------------------------
# THE TREE-ROOT MIRROR OF EVERY DEPLOYED DELIVERABLE.
#
# GitHub Pages for this repo serves the REPOSITORY ROOT, and push_to_remote()
# copies `feed-site/*` into the clone's root -- so the root IS the live site.
# This tree additionally keeps a second, git-TRACKED copy of every deployed
# artifact at its own root: feed.xml, index.html, each episode-NNN.mp3, each
# episode-NNN-notes.md, cover.png and cover.svg.
#
# publish_feed.py writes SITE/ only. It has NO copy site for the root, so the
# two sets are HAND-KEPT IN SYNC -- the exact situation run 057 documented for
# the cover art and closed with a root-vs-deployed sha256 arm. Run 057 closed
# it for cover.png and cover.svg ONLY; `ROOT / name` is still the module's one
# and only generic root reader, and it is reached solely from inside the
# cover_art loop over cover filenames. The other EIGHT root copies had zero
# readers.
#
# Proved against the unmodified module (run 078), each returning ok: true with
# an EMPTY issue list and a verdict byte-identical to the clean tree's:
#
#   * the root feed.xml with an entire <item> stripped -- an episode gone from
#     what Pages would serve
#   * the root index.html rewritten to name the SIBLING show (the documented
#     hard bug, which run 066's show_identity reads out of the feed and run
#     063's advertised_base cannot reach in a root-copy file at all)
#   * a root episode-NNN-notes.md truncated -- a published deliverable
#     carrying the unabridged disclosure, the evidence boundaries and every
#     numbered citation
#   * a root episode-001.mp3 holding episode 002's bytes -- the run-042/045
#     wrong-paper-audio class, with preflight() still ok: true
#
# Why no existing audit covers it (scoped by control, run 073's rule):
# verify_feed()'s local arms resolve every asset relative to the FEED'S OWN
# directory (`feed_path.parent`), which is feed-site/; feed_coverage() does
# the same; feed_sync() compares the COMMITTED feed-site against a fresh
# regeneration; deploy_drift() compares LIVE bytes to feed-site bytes, so the
# local root is outside its scope on both sides; and registry_audit() relates
# the ledger to the manifest. The cover CONTROL proves the detector works and
# the FILE SET was the whole difference: the identical perturbation on
# cover.png is refused by run 057's arm.
#
# Reachability is not hypothetical. This skill's own documented docs-only
# deploy path is a plain `git add -A && git commit && git push` with the token
# in the URL (used when robust_pipeline.py push is the wrong tool because the
# slice must not touch feed-site/). That path commits the LOCAL root copies
# verbatim, with no gate between a drifted root copy and the live site.
#
# Form matched to the field (runs 066/068/070/071): these are BYTE MIRRORS of
# a generated artifact, so they are compared by digest, not parsed -- the
# feed-site copy is already gated field-by-field by every check above, and a
# second parse would only re-ask a question already answered. The deployed
# copy is authoritative; the root copy must equal it.
#
# An ABSENT root copy is NOT an issue, exactly as run 057 ruled for the cover:
# the feed references feed-site/, publish_feed.py never writes the root, and a
# tree that simply does not keep a mirror is not a deploy defect. Only
# present-and-different refuses. No legacy waiver (run 036): a drifted mirror
# of an imported episode is served to subscribers just the same.
ROOT_MIRROR_SUFFIXES = (".xml", ".html", ".mp3", ".png", ".svg", ".md")
# Repo documentation that lives at the root by design and is NOT a mirror of
# anything in feed-site/. Matched exactly, so a notes file can never land here.
ROOT_MIRROR_EXEMPT_NAMES = ("README.md", "production-log.md", "style_guide.md")


COVER_REQUIRED_FORMAT = "png"
# Apple Podcasts: square, 1400x1400 minimum, 3000x3000 maximum.
COVER_MIN_PIXELS = 1400
COVER_MAX_PIXELS = 3000
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


# The three mutually exclusive disclosure texts publish_feed.py can place in an
# item's <content:encoded>, keyed by the lane each one is legitimate for.
#
# <content:encoded> is a PUBLISHED DELIVERABLE: it is what a podcast client
# renders as the episode description, and it carries the show's mandated
# WRITTEN disclosures. preflight() checks disclosures in script.md and
# episode-notes.md; this block is built independently by notes_html() /
# read_notes_html(), which branch on preproduced_episodes() and the read
# manifest. So the block preflight approves is not the block subscribers
# receive, and a wrong branch is invisible to every other check.
#
# preproduced_episodes() says so in its own docstring -- "No gate inspects
# <content:encoded>, so preflight/verify/coverage all stay green on it" --
# which documented the hole rather than closing it (run 042's lesson: when a
# fix names a property no gate reads, wire a reader in the same slice).
#
# Each phrase is a verbatim substring of the corresponding publish_feed.py
# branch. They are deliberately phrases, not whole paragraphs, so ordinary
# editorial rewording of the surrounding prose does not false-fail.
DISCLOSURE_INTERVIEW_REQUIRED = (
    "synthetic/dramatized interview",
    "fictional",
    "AI-generated summary",
)
DISCLOSURE_READING_REQUIRED = (
    "complete automated text-to-speech reading",
    "read verbatim by a synthetic voice",
)
# A reading must NOT carry the synthetic-interview disclosure, and must not
# name Rowan as a participant -- the style guide bars both, and
# read_notes_html() exists precisely to emit a separate block instead.
DISCLOSURE_READING_FORBIDDEN = (
    "synthetic/dramatized interview",
    "Rowan is a fictional composite",
)
# The pre-produced provenance statement asserts David supplied finished audio.
# It is true only for an episode whose manifest record declares
# `preproduced: true`; on a pipeline-rendered interview it is a false
# provenance claim AND it displaces both mandated interview disclosures.
DISCLOSURE_PREPRODUCED_PHRASE = "Pre-recorded audio provided by David Gagnon"


def _parse_rfc2822(value: str) -> datetime | None:
    """Seconds-resolution datetime for an RFC 2822 date, or None if malformed.

    <pubDate> is the one feed field whose syntax is fixed by the RSS spec
    rather than by this pipeline, so an unparseable value is not merely
    surprising -- a client that cannot read it either drops the item or dates
    it now.
    """
    text = (value or "").strip()
    if not text:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _expected_pubdate_epoch(number: str) -> tuple[float | None, str]:
    """When this episode was actually produced, per the durable registries.

    Re-derived from the same data publish_feed.py mines, so the gate compares
    the advertised date against evidence rather than against itself: an
    interview's pubDate comes from the ledger's `rendered` transition (falling
    back to `published` exactly as production_dates() does), and a reading's
    from its read-episodes.json `built_at`.

    Returns (epoch_seconds, source_label). A None epoch means the registries
    hold no production event -- a genuine pre-pipeline import -- for which the
    LEGACY_PUB_DATE sentinel is the correct value and nothing is compared.
    """
    if is_reading(str(number)):
        record = (load_read_manifest().get("episodes") or {}).get(str(number))
        if isinstance(record, dict):
            built = _parse_rfc2822_or_iso(record.get("built_at"))
            if built is not None:
                return built.timestamp(), "read-episodes.json built_at"
        return None, ""
    try:
        ledger = json.loads(LEDGER_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return None, ""
    record = (ledger.get("episodes") or {}).get(str(number))
    if not isinstance(record, dict):
        return None, ""
    transitions = [t for t in (record.get("transitions") or [])
                   if isinstance(t, dict)]
    for wanted in ("rendered", "published"):
        event = next((t for t in transitions
                      if str(t.get("to", "")) == wanted and t.get("at")), None)
        if event is None:
            continue
        moment = _parse_rfc2822_or_iso(event.get("at"))
        if moment is not None:
            return moment.timestamp(), f"ledger {wanted} transition"
    return None, ""


def _parse_rfc2822_or_iso(value: Any) -> datetime | None:
    """A ledger/registry timestamp, which is ISO 8601 with a Z suffix."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return _parse_rfc2822(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _under_advertised_base(url: str, base: str) -> bool:
    """True when `url` is `base` itself or sits beneath it as a PATH.

    A bare ``startswith`` is wrong here: the sibling-slug typo
    ``nih-sepa-genetics-podcasts`` is a string prefix of nothing but shares one
    with this show's base, so ``.../nih-sepa-genetics-podcast`` prefixes it and
    a wrong repo passes. Require the next character to be a path separator (or
    nothing at all), so only a real path boundary counts.
    """
    base = base.rstrip("/")
    if url == base:
        return True
    return url.startswith(base + "/")


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
                    status = response.status
                    remote_root = ET.fromstring(response.read())
                    if status != 200 or not remote_root.findall(".//item"):
                        raise IOError(f"HTTP {status} or no RSS items")
                # Compare the DEPLOYED item set against the local one.
                #
                # This check used to assert only "HTTP 200 and at least one
                # item", and every other remote probe below iterates the items
                # the LOCAL feed contains, resolving each asset by filename. So
                # a deploy in which the enclosures and notes landed but
                # feed.xml did not -- a partial push, or the documented
                # stale-repo-root trap where feed-site/ is updated and the root
                # copy is not -- returned ok: true with an empty issue list
                # while subscribers could not see the episode at all. The
                # assets verified green precisely because they were probed from
                # the local feed rather than from the one actually serving.
                #
                # That verdict is push_to_remote()'s success criterion: its
                # wait loop breaks on result["ok"] and reports the deploy from
                # it, so the one check standing between a half-finished push
                # and "live" could not see the half that was missing. The
                # live-vs-local md5 comparison the docs ask every slice to run
                # by hand detects this, which is exactly why it belongs on the
                # path rather than in operator discipline (run 041's lesson).
                #
                # Both directions are reported, because both are real deploy
                # drift: an item the local feed carries and the live one does
                # not is an episode that never reached listeners, and an item
                # live that local no longer carries means the deployed feed is
                # ahead of this tree. It grants nothing -- an intact deploy
                # yields two empty sets and the previous verdict stands, and
                # every addition is a refusal.
                local_guids = {(i.findtext("guid") or "").strip()
                               for i in root.findall(".//item")}
                remote_guids = {(i.findtext("guid") or "").strip()
                                for i in remote_root.findall(".//item")}
                local_guids.discard("")
                remote_guids.discard("")
                missing_live = sorted(local_guids - remote_guids)
                only_live = sorted(remote_guids - local_guids)
                result["checks"].append({
                    "name": "remote_feed", "url": remote_feed, "http": 200,
                    "local_items": len(local_guids),
                    "remote_items": len(remote_guids),
                    "missing_from_remote": missing_live,
                    "only_on_remote": only_live,
                })
                for guid in missing_live:
                    result["issues"].append(
                        f"deployed feed is stale: {guid} is in the local feed but "
                        f"not in {remote_feed}")
                for guid in only_live:
                    result["issues"].append(
                        f"deployed feed carries {guid}, which the local feed does "
                        f"not; the live site is ahead of this tree")
            except Exception as exc:
                result["issues"].append(f"remote feed check failed for {remote_feed}: {exc}")
        items = root.findall(".//item")
        legacy_numbers = _legacy_episode_numbers()
        result["legacy_exempt_episodes"] = sorted(legacy_numbers)
        guids = [item.findtext("guid", "") for item in items]
        if len(guids) != len(set(guids)):
            result["issues"].append("duplicate RSS GUID")
        result["checks"].append({"name": "feed_parse", "ok": True, "items": len(items)})
        # ------------------------------------------------------------------
        # The SYNDICATION ENVELOPE (run 071). See RSS_REQUIRED_VERSION above
        # for why each of these five fields had zero readers and what each
        # defect costs a subscriber. Enumerated values, compared exactly,
        # wrong case named separately, no legacy waiver (run 036).
        # ------------------------------------------------------------------
        envelope_check: dict[str, Any] = {"name": "syndication_envelope"}
        raw_feed_text = xml.decode("utf-8", errors="replace") if isinstance(xml, bytes) else str(xml)

        # --- <rss version> : enumerated -----------------------------------
        root_tag = root.tag.split("}")[-1]
        envelope_check["root_element"] = root_tag
        if root_tag != "rss":
            result["issues"].append(
                f"feed's root element is <{root_tag}>, not <rss>; a podcast "
                f"client reads nothing from a document that is not an RSS feed")
        version = root.get("version")
        envelope_check["rss_version"] = version
        envelope_check["expected_rss_version"] = RSS_REQUIRED_VERSION
        if version is None:
            result["issues"].append(
                "feed's <rss> element declares no version attribute, so a "
                "strict client cannot confirm it is RSS 2.0 and may reject "
                "the whole feed, taking every episode with it")
        elif version.strip() != RSS_REQUIRED_VERSION:
            if version.strip().casefold() == RSS_REQUIRED_VERSION.casefold():
                result["issues"].append(
                    f"feed declares <rss version={version!r}>, which differs "
                    f"from {RSS_REQUIRED_VERSION!r} only in case; a version "
                    f"string is machine-read, so it must match exactly")
            else:
                result["issues"].append(
                    f"feed declares <rss version={version!r}>, not "
                    f"{RSS_REQUIRED_VERSION!r}; this pipeline emits RSS 2.0 "
                    f"and a client reading another version loses every item")

        # --- the declared namespace bindings : enumerated -----------------
        #
        # ElementTree discards the prefix->URI map, so the DECLARED binding is
        # read from the raw bytes. That is the right source anyway: the
        # question is what the published feed tells a client, and a client
        # reads the declaration, not this tree's lookup helpers.
        declared: dict[str, str] = {}
        for prefix, uri in re.findall(
                r'xmlns:([A-Za-z_][\w.-]*)\s*=\s*"([^"]*)"', raw_feed_text[:4096]):
            declared.setdefault(prefix, uri)
        envelope_check["declared_namespaces"] = declared
        envelope_check["expected_namespaces"] = dict(RSS_REQUIRED_NAMESPACES)
        for prefix, expected_uri in sorted(RSS_REQUIRED_NAMESPACES.items()):
            actual = declared.get(prefix)
            if actual is None:
                result["issues"].append(
                    f"feed declares no xmlns:{prefix} binding, so every "
                    f"{prefix}: element in it is unbound and the feed does "
                    f"not parse as XML at all")
            elif actual.strip() != expected_uri:
                if actual.strip().casefold() == expected_uri.casefold():
                    result["issues"].append(
                        f"feed binds xmlns:{prefix} to {actual!r}, which "
                        f"differs from {expected_uri!r} only in case; a "
                        f"namespace URI is compared byte-for-byte by every "
                        f"parser, so it must match exactly")
                else:
                    result["issues"].append(
                        f"feed binds xmlns:{prefix} to {actual!r} instead of "
                        f"{expected_uri!r}; every {prefix}: field in the feed "
                        f"lands in a foreign namespace and is invisible to a "
                        f"client, while this tree's own endswith() lookups "
                        f"still find it and stay green")

        # --- per-item <enclosure type> and <guid isPermaLink> -------------
        enclosure_types: dict[str, Any] = {}
        permalink_flags: dict[str, Any] = {}
        for item in items:
            number = _feed_item_number(item) or (item.findtext("guid") or "?").strip()
            enclosure_el = item.find("enclosure")
            if enclosure_el is not None:
                declared_type = enclosure_el.get("type")
                enclosure_types[number] = declared_type
                if declared_type is None:
                    result["issues"].append(
                        f"episode {number} advertises an <enclosure> with no "
                        f"type attribute, so a podcast client cannot tell the "
                        f"file is audio and may refuse to play it")
                elif declared_type.strip() != ENCLOSURE_REQUIRED_TYPE:
                    if declared_type.strip().casefold() == ENCLOSURE_REQUIRED_TYPE:
                        result["issues"].append(
                            f"episode {number} advertises enclosure type "
                            f"{declared_type!r}, which differs from "
                            f"{ENCLOSURE_REQUIRED_TYPE!r} only in case; a MIME "
                            f"type is machine-read, so it must match exactly")
                    else:
                        result["issues"].append(
                            f"episode {number} advertises enclosure type "
                            f"{declared_type!r}, not {ENCLOSURE_REQUIRED_TYPE!r}; "
                            f"every episode this pipeline renders is an mp3, so "
                            f"the item is listed and unplayable")
            guid_el = item.find("guid")
            if guid_el is not None:
                flag = guid_el.get("isPermaLink")
                permalink_flags[number] = flag
                if flag is None:
                    result["issues"].append(
                        f"episode {number} advertises a <guid> with no "
                        f"isPermaLink attribute, which RSS DEFAULTS to true, "
                        f"so a client reads the episode's permanent identity "
                        f"as a relative URL")
                elif flag.strip() != GUID_REQUIRED_ISPERMALINK:
                    if flag.strip().casefold() == GUID_REQUIRED_ISPERMALINK:
                        result["issues"].append(
                            f"episode {number} advertises isPermaLink="
                            f"{flag!r}, which differs from "
                            f"{GUID_REQUIRED_ISPERMALINK!r} only in case; the "
                            f"attribute is machine-read, so it must match exactly")
                    else:
                        result["issues"].append(
                            f"episode {number} advertises isPermaLink={flag!r}; "
                            f"this show's GUIDs are opaque identities, not URLs, "
                            f"and a client that resolves one re-delivers or "
                            f"shadows the episode")
        envelope_check["enclosure_types"] = enclosure_types
        envelope_check["permalink_flags"] = permalink_flags
        envelope_check["expected_enclosure_type"] = ENCLOSURE_REQUIRED_TYPE
        envelope_check["expected_ispermalink"] = GUID_REQUIRED_ISPERMALINK
        result["checks"].append(envelope_check)
        # ------------------------------------------------------------------
        # Cover art. The feed advertises it in five slots -- the channel's
        # <itunes:image href>, the channel's <image><url>, and one
        # <itunes:image href> per item -- and until run 057 NOTHING read any
        # of them. Every other asset in this function is probed (enclosures
        # by byte length, notes by name, the deployed item set by GUID), so
        # the artwork was the one advertised file no gate looked at.
        #
        # It is reachable by an ordinary operator sequence, not a contrived
        # one: publish_feed.py copies each episode's mp3 and notes into
        # feed-site/ on every run but has NO copy site for the cover, so the
        # two copies (tree root + feed-site/) are hand-kept in sync. Edit one
        # and forget the other, or lose the feed-site copy, and `publish`
        # returned ok: true with an empty issue list while every podcast
        # client showed broken artwork. That verdict is also
        # push_to_remote()'s success criterion, so a deploy whose cover never
        # landed reported itself live.
        #
        # No waiver, including for a legacy item: an advertised file that
        # 404s is a defect for an import too, and a waiver is a gate with the
        # sign flipped (run 036). Drift between the root and feed-site copies
        # is reported only when both exist and differ -- an absent root copy
        # is not a deploy defect, since the feed never references it.
        cover_refs: set[str] = set()
        _itunes_ns = "http://www.itunes.com/dtds/podcast-1.0.dtd"
        for node in root.iter():
            if node.tag.endswith("image"):
                href = (node.get("href") or "").strip()
                if href:
                    cover_refs.add(href)
                url_node = node.find("url")
                if url_node is not None and (url_node.text or "").strip():
                    cover_refs.add((url_node.text or "").strip())
        cover_names = sorted({Path(urllib.parse.urlparse(h).path).name
                              for h in cover_refs if h})
        cover_check: dict[str, Any] = {
            "name": "cover_art",
            "advertised": sorted(cover_refs),
            "files": cover_names,
        }
        if not cover_refs:
            result["issues"].append("feed advertises no cover art")
        for name in cover_names:
            if feed_path:
                local_cover = feed_path.parent / name
                if not local_cover.exists():
                    result["issues"].append(
                        f"missing local cover art {name}")
                elif local_cover.stat().st_size == 0:
                    result["issues"].append(
                        f"local cover art {name} is empty")
                else:
                    cover_check["local_bytes"] = local_cover.stat().st_size
                    # The root copy is the editing source; publish_feed.py
                    # never derives feed-site/ from it, so a silent drift
                    # deploys artwork nobody approved.
                    root_cover = ROOT / name
                    if root_cover.exists() and root_cover.is_file():
                        site_digest = hashlib.sha256(
                            local_cover.read_bytes()).hexdigest()
                        root_digest = hashlib.sha256(
                            root_cover.read_bytes()).hexdigest()
                        cover_check["site_sha256"] = site_digest
                        cover_check["root_sha256"] = root_digest
                        if site_digest != root_digest:
                            result["issues"].append(
                                f"cover art {name} differs between the tree "
                                f"root and feed-site/ (root "
                                f"{root_digest[:12]} vs deployed "
                                f"{site_digest[:12]}); they are hand-kept in "
                                f"sync, so edit both")
                    # DECODE it. See COVER_REQUIRED_FORMAT above: every
                    # arm below was proved to ship ok: true with an empty
                    # issue list against the unmodified module, because run
                    # 057 stopped at existence and run 058 closed this exact
                    # axis for audio only. Dimensions are reported even when
                    # the decode fails, so a bad cover's issue is actionable.
                    if local_cover.suffix.lower() == ".png":
                        decoded = decode_png(local_cover.read_bytes())
                        cover_check["decoded"] = decoded["ok"]
                        cover_check["format"] = decoded["format"]
                        cover_check["width"] = decoded["width"]
                        cover_check["height"] = decoded["height"]
                        if not decoded["ok"]:
                            result["issues"].append(
                                f"cover art {name} is not renderable: "
                                f"{decoded['error']}; every podcast client "
                                f"shows this show with broken artwork")
                        else:
                            w = decoded["width"] or 0
                            h = decoded["height"] or 0
                            if w != h:
                                result["issues"].append(
                                    f"cover art {name} is {w}x{h}, which is "
                                    f"not square; podcast artwork must be "
                                    f"square or a directory rejects the show")
                            if min(w, h) < COVER_MIN_PIXELS:
                                result["issues"].append(
                                    f"cover art {name} is {w}x{h}, below the "
                                    f"{COVER_MIN_PIXELS}x{COVER_MIN_PIXELS} "
                                    f"minimum a podcast directory requires")
                            elif max(w, h) > COVER_MAX_PIXELS:
                                result["issues"].append(
                                    f"cover art {name} is {w}x{h}, above the "
                                    f"{COVER_MAX_PIXELS}x{COVER_MAX_PIXELS} "
                                    f"maximum a podcast directory accepts")
            if remote:
                cover_url = remote.rstrip("/") + "/" + name
                try:
                    with urllib.request.urlopen(cover_url, timeout=timeout) as response:
                        status = response.status
                        body = response.read(8)
                    if status != 200 or not body:
                        raise IOError(f"HTTP {status}")
                    cover_check.setdefault("remote", []).append(
                        {"url": cover_url, "http": status})
                except Exception as exc:
                    result["issues"].append(
                        f"remote cover art check failed for {cover_url}: {exc}")
        result["checks"].append(cover_check)

        # The channel's identity text. See SHOW_TITLE above for why this had
        # zero readers and why a slug-form URL guard does not cover it.
        channel = root.find("channel")
        channel_title = ((channel.findtext("title") or "").strip()
                         if channel is not None else "")
        channel_image = channel.find("image") if channel is not None else None
        image_title = ((channel_image.findtext("title") or "").strip()
                       if channel_image is not None else "")
        identity_check: dict[str, Any] = {
            "name": "show_identity",
            "expected": SHOW_TITLE,
            "channel_title": channel_title or None,
            "image_title": image_title or None,
        }
        if channel is None:
            result["issues"].append(
                "feed has no <channel> element, so it advertises no show "
                "identity at all")
        elif not channel_title:
            result["issues"].append(
                "feed has an empty channel <title>, so every podcast client "
                "shows a nameless show")
        else:
            if channel_title != SHOW_TITLE:
                result["issues"].append(
                    f"feed advertises the channel <title> {channel_title!r}, "
                    f"but this show is {SHOW_TITLE!r}; the channel title is "
                    f"the show's name in every subscriber's client")
            for bad in FORBIDDEN_SHOW_TITLES:
                if bad.lower() in channel_title.lower():
                    result["issues"].append(
                        f"feed advertises the channel <title> "
                        f"{channel_title!r}, which names the sibling show "
                        f"{bad!r}; the two shows must never share an identity")
        if channel_image is not None:
            if not image_title:
                result["issues"].append(
                    "feed's channel <image> has an empty <title>, so the "
                    "artwork advertises no show name")
            elif channel_title and image_title != channel_title:
                result["issues"].append(
                    f"feed's cover art caption <image><title> "
                    f"{image_title!r} disagrees with the channel <title> "
                    f"{channel_title!r}; publish_feed.py writes both, so they "
                    f"drift only through a hand-edit or a partial write")
        # The channel's BLURB. See FORBIDDEN_SHOW_DESCRIPTIONS above for why
        # this had zero readers and why neither name-based guard reaches it.
        channel_desc_el = (channel.find("description")
                           if channel is not None else None)
        channel_desc = ((channel_desc_el.text or "").strip()
                        if channel_desc_el is not None else "")
        identity_check["channel_description_chars"] = len(channel_desc)
        if channel is not None:
            if channel_desc_el is None:
                result["issues"].append(
                    "feed's <channel> has no <description> element, so the "
                    "show advertises no description at all")
            elif not channel_desc:
                result["issues"].append(
                    "feed has an empty channel <description>, so every "
                    "podcast client shows the show with no description")
            else:
                low = channel_desc.lower()
                for bad in FORBIDDEN_SHOW_DESCRIPTIONS:
                    if bad.lower() in low:
                        result["issues"].append(
                            f"feed's channel <description> carries the "
                            f"sibling show's blurb phrasing {bad!r}; the two "
                            f"shows must never share an identity")
                for bad in FORBIDDEN_SHOW_TITLES:
                    if bad.lower() in low:
                        result["issues"].append(
                            f"feed's channel <description> names the sibling "
                            f"show {bad!r}; the two shows must never share an "
                            f"identity")
                for token in PLACEHOLDER_DESCRIPTION_TOKENS:
                    if token in low:
                        result["issues"].append(
                            f"feed's channel <description> still carries the "
                            f"placeholder token {token!r}, so it was never "
                            f"written for this show")
        result["checks"].append(identity_check)

        # The channel's STRUCTURAL NAVIGATION and ARTWORK CONTAINER. See
        # SHOW_HOMEPAGE above for why all four had zero readers, and why
        # neither cover_art's union nor show_identity's presence-guarded
        # artwork arm nor advertised_base's host check reaches any of them.
        #
        # Form matched per field (runs 066/068/070/071): a URL is compared as
        # a URL (trailing slash normalized, since no client distinguishes
        # them), with a wrong-case host refused separately and NAMED as case,
        # because a homepage is machine-read by every directory.
        nav_check: dict[str, Any] = {"name": "channel_navigation",
                                     "expected_homepage": SHOW_HOMEPAGE}
        if channel is not None:
            def _same_url(a: str, b: str) -> bool:
                return a.rstrip("/") == b.rstrip("/")

            link_el = channel.find("link")
            channel_link = ((link_el.text or "").strip()
                            if link_el is not None else "")
            nav_check["channel_link"] = channel_link or None
            if link_el is None:
                result["issues"].append(
                    "feed's <channel> has no <link> element, so the show "
                    "advertises no homepage and every client's 'visit "
                    "website' affordance is dead")
            elif not channel_link:
                result["issues"].append(
                    "feed has an empty channel <link>, so the show "
                    "advertises no homepage")
            elif not _same_url(channel_link, SHOW_HOMEPAGE):
                if _same_url(channel_link.casefold(),
                             SHOW_HOMEPAGE.casefold()):
                    result["issues"].append(
                        f"feed advertises the channel <link> "
                        f"{channel_link!r}, which differs from "
                        f"{SHOW_HOMEPAGE!r} only in case; a homepage URL is "
                        f"machine-read by every podcast directory")
                else:
                    result["issues"].append(
                        f"feed advertises the channel <link> "
                        f"{channel_link!r}, but this show's homepage is "
                        f"{SHOW_HOMEPAGE!r}; the channel link is where every "
                        f"subscriber and directory is sent for the show")

            # The <image> block's PRESENCE is the gap show_identity's
            # `if channel_image is not None` arm skips rather than reports.
            nav_check["image_present"] = channel_image is not None
            if channel_image is None:
                result["issues"].append(
                    "feed's <channel> has no <image> element, so the show "
                    "advertises no RSS 2.0 artwork and a non-iTunes client "
                    "renders it with no cover at all")
            else:
                img_url_el = channel_image.find("url")
                img_url = ((img_url_el.text or "").strip()
                           if img_url_el is not None else "")
                nav_check["image_url"] = img_url or None
                itunes_href = ""
                itunes_img = channel.find(
                    "{http://www.itunes.com/dtds/podcast-1.0.dtd}image")
                if itunes_img is not None:
                    itunes_href = (itunes_img.get("href") or "").strip()
                nav_check["channel_itunes_image"] = itunes_href or None
                if img_url_el is None:
                    result["issues"].append(
                        "feed's channel <image> has no <url> element, so the "
                        "artwork container advertises no image file")
                elif not img_url:
                    result["issues"].append(
                        "feed has an empty channel <image><url>, so the "
                        "artwork container advertises no image file")
                elif itunes_href and not _same_url(img_url, itunes_href):
                    result["issues"].append(
                        f"feed's channel <image><url> {img_url!r} disagrees "
                        f"with the channel <itunes:image href> "
                        f"{itunes_href!r}; publish_feed.py writes both from "
                        f"one BASE_URL, so they drift only through a "
                        f"hand-edit or a partial write")

                img_link_el = channel_image.find("link")
                img_link = ((img_link_el.text or "").strip()
                            if img_link_el is not None else "")
                nav_check["image_link"] = img_link or None
                if img_link_el is None:
                    result["issues"].append(
                        "feed's channel <image> has no <link> element, so "
                        "its artwork clicks through to nothing")
                elif not img_link:
                    result["issues"].append(
                        "feed has an empty channel <image><link>, so its "
                        "artwork clicks through to nothing")
                elif not _same_url(img_link, SHOW_HOMEPAGE):
                    result["issues"].append(
                        f"feed's channel <image><link> {img_link!r} is not "
                        f"this show's homepage {SHOW_HOMEPAGE!r}; "
                        f"publish_feed.py writes it from the same BASE_URL "
                        f"as the channel <link>")
        result["checks"].append(nav_check)

        # The channel's ATTRIBUTION and CLASSIFICATION block. See
        # SHOW_LANGUAGE above for why all six fields had zero readers, what
        # each one costs a subscriber, and why <itunes:author> is an identity
        # slot that run 066's title guard cannot reach.
        itunes_ns = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
        attribution_check: dict[str, Any] = {"name": "channel_attribution"}
        if channel is not None:
            def _chan_text(tag: str) -> tuple[Any, str]:
                el = channel.find(tag)
                return el, ((el.text or "").strip() if el is not None else "")

            # --- <language> : enumerated, exact ---------------------------
            lang_el, lang = _chan_text("language")
            attribution_check["language"] = lang
            if lang_el is None:
                result["issues"].append(
                    "feed's <channel> has no <language> element, so a "
                    "directory cannot route the show by language")
            elif not lang:
                result["issues"].append(
                    "feed has an empty channel <language>, so the show "
                    "advertises no language at all")
            elif lang.lower() != SHOW_LANGUAGE.lower():
                result["issues"].append(
                    f"feed advertises the channel <language> {lang!r}, but "
                    f"this show is {SHOW_LANGUAGE!r}; every client and "
                    f"directory routes the show by this value")
            elif lang != SHOW_LANGUAGE:
                result["issues"].append(
                    f"feed advertises the channel <language> {lang!r}, which "
                    f"differs from {SHOW_LANGUAGE!r} only in case; a language "
                    f"tag is matched literally by some directories")

            # --- <copyright> : prose naming the holder --------------------
            copy_el, copyright_text = _chan_text("copyright")
            attribution_check["copyright"] = copyright_text
            if copy_el is None:
                result["issues"].append(
                    "feed's <channel> has no <copyright> element, so the "
                    "show publishes no rights line")
            elif not copyright_text:
                result["issues"].append(
                    "feed has an empty channel <copyright>, so the show "
                    "publishes no rights line")
            else:
                low = copyright_text.lower()
                if SHOW_COPYRIGHT_HOLDER.lower() not in low:
                    result["issues"].append(
                        f"feed advertises the channel <copyright> "
                        f"{copyright_text!r}, which does not name "
                        f"{SHOW_COPYRIGHT_HOLDER!r}; a rights line naming the "
                        f"wrong holder misattributes the whole show")
                for bad in FORBIDDEN_SHOW_TITLES:
                    if bad.lower() in low:
                        result["issues"].append(
                            f"feed's channel <copyright> names the sibling "
                            f"show {bad!r}; the two shows must never share an "
                            f"identity")

            # --- <itunes:author> : prose, AND an identity slot ------------
            author_el = channel.find(itunes_ns + "author")
            author = ((author_el.text or "").strip()
                      if author_el is not None else "")
            attribution_check["itunes_author"] = author
            if author_el is None:
                result["issues"].append(
                    "feed's <channel> has no <itunes:author> element, so the "
                    "show advertises no author beside its title")
            elif not author:
                result["issues"].append(
                    "feed has an empty channel <itunes:author>, so the show "
                    "advertises no author beside its title")
            else:
                low = author.lower()
                if SHOW_ITUNES_AUTHOR.lower() not in low:
                    result["issues"].append(
                        f"feed advertises the channel <itunes:author> "
                        f"{author!r}, which does not name "
                        f"{SHOW_ITUNES_AUTHOR!r}; the author line is rendered "
                        f"beside the show title in every client")
                # Run 066's identity guard, which is scoped to the title
                # fields and never reached this slot.
                for bad in FORBIDDEN_SHOW_TITLES:
                    if bad.lower() in low:
                        result["issues"].append(
                            f"feed's channel <itunes:author> names the "
                            f"sibling show {bad!r}; the two shows must never "
                            f"share an identity")

            # --- <itunes:type> : enumerated, exact ------------------------
            type_el = channel.find(itunes_ns + "type")
            show_type = ((type_el.text or "").strip()
                         if type_el is not None else "")
            attribution_check["itunes_type"] = show_type
            if type_el is None:
                result["issues"].append(
                    "feed's <channel> has no <itunes:type> element, so a "
                    "client must guess whether the show is episodic or serial")
            elif not show_type:
                result["issues"].append(
                    "feed has an empty channel <itunes:type>, so a client "
                    "must guess whether the show is episodic or serial")
            elif show_type.lower() not in ALLOWED_ITUNES_TYPES:
                result["issues"].append(
                    f"feed advertises the channel <itunes:type> "
                    f"{show_type!r}, which is not one of "
                    f"{list(ALLOWED_ITUNES_TYPES)}")
            elif show_type.lower() != REQUIRED_ITUNES_TYPE:
                result["issues"].append(
                    f"feed advertises the channel <itunes:type> "
                    f"{show_type!r}, but this show is "
                    f"{REQUIRED_ITUNES_TYPE!r}; 'serial' makes a client "
                    f"present the catalogue oldest-first, silently "
                    f"reordering every episode")
            elif show_type != REQUIRED_ITUNES_TYPE:
                result["issues"].append(
                    f"feed advertises the channel <itunes:type> "
                    f"{show_type!r}, which differs from "
                    f"{REQUIRED_ITUNES_TYPE!r} only in case; Apple matches "
                    f"this value literally")

            # --- <itunes:category> : the value is an ATTRIBUTE ------------
            cat_els = channel.findall(itunes_ns + "category")
            cats = [(e.get("text") or "").strip() for e in cat_els]
            attribution_check["itunes_categories"] = cats
            if not cat_els:
                result["issues"].append(
                    "feed's <channel> has no <itunes:category> element, so "
                    "the show is uncategorised in every directory")
            elif not any(cats):
                result["issues"].append(
                    "feed's channel <itunes:category> carries an empty text "
                    "attribute, so the show is uncategorised in every "
                    "directory")
            elif REQUIRED_ITUNES_CATEGORY not in cats:
                result["issues"].append(
                    f"feed advertises the channel categories {cats}, which do "
                    f"not include {REQUIRED_ITUNES_CATEGORY!r}; a category "
                    f"spelling outside Apple's vocabulary is silently "
                    f"uncategorised")

            # --- channel <itunes:explicit> : enumerated -------------------
            expl_el = channel.find(itunes_ns + "explicit")
            explicit = ((expl_el.text or "").strip()
                        if expl_el is not None else "")
            attribution_check["itunes_explicit"] = explicit
            if expl_el is None:
                result["issues"].append(
                    "feed's <channel> has no <itunes:explicit> element, so "
                    "the show advertises no content rating")
            elif not explicit:
                result["issues"].append(
                    "feed has an empty channel <itunes:explicit>, so the "
                    "show advertises no content rating")
            elif explicit.lower() not in ALLOWED_ITUNES_EXPLICIT:
                result["issues"].append(
                    f"feed advertises the channel <itunes:explicit> "
                    f"{explicit!r}, which is not one of "
                    f"{list(ALLOWED_ITUNES_EXPLICIT)}")
            elif explicit.lower() != REQUIRED_ITUNES_EXPLICIT:
                result["issues"].append(
                    f"feed advertises the channel <itunes:explicit> "
                    f"{explicit!r}, but this show is "
                    f"{REQUIRED_ITUNES_EXPLICIT!r}")
            elif explicit != REQUIRED_ITUNES_EXPLICIT:
                result["issues"].append(
                    f"feed advertises the channel <itunes:explicit> "
                    f"{explicit!r}, which differs from "
                    f"{REQUIRED_ITUNES_EXPLICIT!r} only in case")
        result["checks"].append(attribution_check)

        # Advertised URL prefix vs the base this show owns.
        #
        # Collected from every absolute URL the feed emits, then compared to
        # EXPECTED_ADVERTISED_BASES. Four refusals: a URL under no expected
        # base, a URL carrying a forbidden (cross-show) substring, a
        # non-absolute enclosure/image URL (invalid in RSS, and silently
        # unresolvable for a subscriber), and a feed that advertises no
        # absolute URL at all.
        #
        # Deliberately NOT keyed on `remote`: the question is where the feed
        # sends subscribers, which is a property of the published bytes and is
        # the same whether or not this run is probing a deployment. And no
        # legacy waiver (run 036) -- an imported episode's enclosure must still
        # resolve, so a wrong prefix is a defect for an import too.
        advertised: set[str] = set()
        relative: set[str] = set()
        for node in root.iter():
            for attr in ("url", "href"):
                raw = (node.get(attr) or "").strip()
                if raw:
                    if raw.startswith(("http://", "https://")):
                        advertised.add(raw)
                    elif node.tag.endswith(("enclosure", "image")):
                        relative.add(raw)
            if node.tag.endswith(("url", "link")) and not len(node):
                raw = (node.text or "").strip()
                if raw.startswith(("http://", "https://")):
                    advertised.add(raw)
        base_check: dict[str, Any] = {
            "name": "advertised_base",
            "expected_bases": list(EXPECTED_ADVERTISED_BASES),
            "advertised": sorted(advertised),
            "distinct_bases": sorted({
                base.rstrip("/") for url in advertised
                for base in EXPECTED_ADVERTISED_BASES
                if _under_advertised_base(url, base)}),
        }
        if not advertised:
            result["issues"].append(
                "feed advertises no absolute URL, so no enclosure or cover "
                "art can be resolved by a subscriber")
        for url in sorted(advertised):
            if not any(_under_advertised_base(url, base)
                       for base in EXPECTED_ADVERTISED_BASES):
                result["issues"].append(
                    f"feed advertises {url}, which is not under this show's "
                    f"base {EXPECTED_ADVERTISED_BASES[0]}; every subscriber "
                    f"resolves the advertised URL, not the local filename")
            for bad in FORBIDDEN_ADVERTISED_SUBSTRINGS:
                if bad in url.lower():
                    result["issues"].append(
                        f"feed advertises {url}, which carries the "
                        f"cross-show substring {bad!r}; the two shows must "
                        f"never share a URL or a GUID")
        for raw in sorted(relative):
            result["issues"].append(
                f"feed advertises the non-absolute URL {raw!r}; RSS "
                f"enclosure and artwork URLs must be absolute or no client "
                f"can resolve them")
        base_check["relative"] = sorted(relative)
        result["checks"].append(base_check)
        read_manifest_episodes = (load_read_manifest().get("episodes") or {})
        manifest_episodes = load_manifest().get("episodes", {})
        for item in items:
            # Legacy = what the ledger says, NOT what the feed numbers say.
            # This was keyed on `<itunes:episode> == "1"`, which publish_feed.py
            # emits for episode 001 (`{int(num)}`) -- a fully gated interview in
            # this tree, three-reviewer panel and all. So the exemption meant
            # for imported history landed on a current episode and demoted its
            # missing-notes failure (local AND live) to a warning, leaving
            # verify_feed ok: true and publish_local happy to ship it.
            # status() already defines legacy as the literal ledger status
            # "published" (pre-pipeline imports), distinct from the
            # published_and_moved / published_pending_zotero_move family this
            # tree's real episodes use; reuse that one definition.
            legacy_item = _feed_item_number(item) in legacy_numbers
            # ----------------------------------------------------------------
            # The advertised WRITTEN disclosure.
            #
            # Until run 064 NOTHING read this. robust_pipeline.py mentioned
            # <content:encoded> exactly twice, both in one block that pulls
            # notes.md hrefs out of it to probe those files -- so the hrefs
            # were verified and the prose around them was not. Reachable
            # classes, all of which returned ok: true with an EMPTY issue list
            # from verify_feed local AND --remote, plus coverage and preflight:
            #
            #   * an interview advertising the PRE-PRODUCED provenance (claims
            #     David supplied the audio, and LOSES both the
            #     fictional-correspondent and AI-generated disclosures)
            #   * an interview advertising the READING disclosure (tells
            #     listeners Rowan does not appear in an episode built on Rowan
            #     dialogue)
            #   * a reading advertising the SYNTHETIC-INTERVIEW disclosure
            #     (names Rowan in a verbatim reading -- exactly what
            #     read_notes_html() exists to prevent)
            #   * the block emptied entirely (every written disclosure gone)
            #
            # That verdict is what publish_local() refuses on and what
            # push_to_remote()'s wait loop breaks on to call a deploy live.
            # This is the run-042/045/056/057/058/062/063 axis once more: an
            # advertised field with zero readers. 057 was the cover art, 058
            # the duration, 062 the pubDate, 063 the URL prefix -- and this is
            # the one field whose CONTENT is a compliance statement.
            #
            # Lane is taken from the same discriminators the rest of the
            # pipeline uses: is_reading() for the read lane, and the manifest
            # `preproduced` flag for supplied audio (a property of the RECORD,
            # not of the episode number).
            encoded = item.find("content:encoded", {"content": "http://purl.org/rss/1.0/modules/content/"})
            if encoded is None:
                encoded = next((x for x in item if x.tag.endswith("encoded")), None)
            disc_number = _feed_item_number(item)
            disc_text = (encoded.text or "") if encoded is not None else ""
            disc_is_read = bool(disc_number) and is_reading(disc_number, read_manifest_episodes)
            disc_record = manifest_episodes.get(disc_number, {}) if disc_number else {}
            disc_preproduced = disc_record.get("preproduced") is True
            disclosure_check = {
                "name": "disclosure",
                "episode": disc_number or None,
                "lane": "read" if disc_is_read else "interview",
                "preproduced": disc_preproduced,
                "chars": len(disc_text),
            }
            if encoded is None:
                result["issues"].append(
                    f"feed item for episode {disc_number or '<unidentified>'} has "
                    f"no <content:encoded>, so it advertises none of the "
                    f"written disclosures the style guide mandates")
            elif not disc_text.strip():
                result["issues"].append(
                    f"feed item for episode {disc_number or '<unidentified>'} has "
                    f"an empty <content:encoded>; this is the block a podcast "
                    f"client renders and it carries the required written "
                    f"disclosures")
            elif disc_is_read:
                missing = [p for p in DISCLOSURE_READING_REQUIRED if p not in disc_text]
                for phrase in missing:
                    result["issues"].append(
                        f"reading {disc_number} advertises a <content:encoded> "
                        f"missing the verbatim-reading disclosure phrase "
                        f"{phrase!r}; publish_feed.read_notes_html() emits it")
                for phrase in DISCLOSURE_READING_FORBIDDEN:
                    if phrase in disc_text:
                        result["issues"].append(
                            f"reading {disc_number} advertises the "
                            f"synthetic-interview disclosure ({phrase!r}) in its "
                            f"<content:encoded>; the style guide bars it on a "
                            f"verbatim reading, where Rowan does not appear")
                if DISCLOSURE_PREPRODUCED_PHRASE in disc_text:
                    result["issues"].append(
                        f"reading {disc_number} advertises the pre-produced "
                        f"provenance statement, which is false for a "
                        f"pipeline-rendered reading")
                disclosure_check["missing"] = missing
            elif disc_preproduced:
                if DISCLOSURE_PREPRODUCED_PHRASE not in disc_text:
                    result["issues"].append(
                        f"episode {disc_number} is declared preproduced in the "
                        f"manifest but its <content:encoded> does not carry the "
                        f"pre-produced provenance statement")
            else:
                missing = [p for p in DISCLOSURE_INTERVIEW_REQUIRED if p not in disc_text]
                for phrase in missing:
                    result["issues"].append(
                        f"episode {disc_number} advertises a <content:encoded> "
                        f"missing the required interview disclosure phrase "
                        f"{phrase!r}")
                if DISCLOSURE_PREPRODUCED_PHRASE in disc_text:
                    result["issues"].append(
                        f"episode {disc_number} advertises the pre-produced "
                        f"provenance statement ('audio provided by David Gagnon "
                        f"... not reviewed or transcribed') but its manifest "
                        f"record does not declare preproduced: true; a "
                        f"pipeline-rendered episode must not claim supplied audio")
                for phrase in DISCLOSURE_READING_REQUIRED:
                    if phrase in disc_text:
                        result["issues"].append(
                            f"episode {disc_number} is an interview but its "
                            f"<content:encoded> advertises the verbatim-reading "
                            f"disclosure ({phrase!r})")
                disclosure_check["missing"] = missing
            result["checks"].append(disclosure_check)
            # ----------------------------------------------------------------
            # The advertised GUID -- the episode's permanent identity.
            #
            # See GUID_REQUIRED_PREFIX above for why this had zero readers.
            # Four refusals, all keyed on what the RECORD declares:
            #   * a GUID not carrying this show's prefix (a cross-show prefix
            #     is called out separately -- it is the documented hard bug)
            #   * an interview GUID carrying the read lane's `-reading` marker,
            #     or a reading's GUID lacking it
            #   * a GUID whose episode number disagrees with its enclosure's
            #   * a GUID that is absent or empty
            # No legacy waiver (run 036): an imported episode's GUID is the
            # subscriber's identity for it just the same.
            guid_value = (item.findtext("guid") or "").strip()
            guid_enclosure = item.find("enclosure")
            guid_url = ((guid_enclosure.get("url") or "")
                        if guid_enclosure is not None else "")
            guid_from_guid = re.findall(r"episode-(\d+)", guid_value)
            guid_from_url = re.findall(r"episode-(\d+)", guid_url)
            guid_number = _feed_item_number(item)
            guid_is_read = bool(guid_number) and is_reading(
                guid_number, read_manifest_episodes)
            guid_check = {
                "name": "guid",
                "episode": guid_number or None,
                "guid": guid_value,
                "lane": "read" if guid_is_read else "interview",
                "prefix_ok": guid_value.startswith(GUID_REQUIRED_PREFIX),
            }
            if not guid_value:
                result["issues"].append(
                    f"feed item for episode {guid_number or '<unidentified>'} "
                    f"has no <guid>; a subscriber has no stable identity for it "
                    f"and a client cannot tell it from a new episode")
            else:
                for bad in FORBIDDEN_ADVERTISED_SUBSTRINGS:
                    if bad in guid_value.lower():
                        result["issues"].append(
                            f"feed item for episode "
                            f"{guid_number or '<unidentified>'} advertises the "
                            f"GUID {guid_value!r}, which carries the cross-show "
                            f"substring {bad!r}; the two shows must never share "
                            f"a GUID")
                if not guid_value.startswith(GUID_REQUIRED_PREFIX):
                    result["issues"].append(
                        f"feed item for episode "
                        f"{guid_number or '<unidentified>'} advertises the GUID "
                        f"{guid_value!r}, which does not carry this show's "
                        f"required prefix {GUID_REQUIRED_PREFIX!r}; "
                        f"publish_feed.py emits it on every item")
                if guid_is_read and GUID_READING_MARKER not in guid_value:
                    result["issues"].append(
                        f"reading {guid_number} advertises the GUID "
                        f"{guid_value!r}, which lacks the read lane's "
                        f"{GUID_READING_MARKER!r} marker that distinguishes it "
                        f"from the interview item at the same number")
                if (not guid_is_read) and GUID_READING_MARKER in guid_value:
                    result["issues"].append(
                        f"episode {guid_number} is an interview but advertises "
                        f"the GUID {guid_value!r}, which carries the read "
                        f"lane's {GUID_READING_MARKER!r} marker")
                if guid_from_guid and guid_from_url and \
                        guid_from_guid[0] != guid_from_url[0]:
                    result["issues"].append(
                        f"feed item advertises the GUID {guid_value!r} naming "
                        f"episode {guid_from_guid[0]} while its enclosure "
                        f"{guid_url.rsplit('/', 1)[-1]!r} is episode "
                        f"{guid_from_url[0]}; the identity and the audio "
                        f"disagree")
                if not guid_from_guid:
                    result["issues"].append(
                        f"feed item for episode "
                        f"{guid_number or '<unidentified>'} advertises the GUID "
                        f"{guid_value!r}, which carries no episode-NNN token; "
                        f"the number is recoverable only from the enclosure URL")
            guid_check["guid_number"] = guid_from_guid[0] if guid_from_guid else None
            guid_check["enclosure_number"] = guid_from_url[0] if guid_from_url else None
            result["checks"].append(guid_check)
            # ----------------------------------------------------------------
            # The advertised ORDINAL and KIND of this item.
            #
            # See EPISODE_TYPE_REQUIRED above for why both fields had zero
            # readers and why run 036 is the reason rather than an oversight.
            # Five refusals, each keyed on the record's own GUID:
            #   * a number disagreeing with the GUID's episode number
            #   * a number that is absent, empty, or not a positive integer
            #   * an episodeType outside the Apple-specified vocabulary
            #   * an episodeType that is valid but not `full`, which silently
            #     moves a gated episode out of the numbered run
            #
            # There is deliberately NO separate "two items share an ordinal"
            # arm: that condition is unreachable past the checks above. Two
            # items advertising one ordinal either disagree with their GUIDs --
            # caught by the agreement arm here -- or carry the same GUID
            # number, which the pre-existing duplicate-GUID check refuses. A
            # first draft of this gate carried that arm and the proof harness
            # showed it could never fire; the arm was removed rather than the
            # claim weakened.
            ordinal_episode = guid_number or ""
            ordinal_node = next(
                (x for x in item if x.tag.endswith("episode")
                 and not x.tag.endswith("episodeType")), None)
            ordinal_text = ((ordinal_node.text or "").strip()
                            if ordinal_node is not None else "")
            type_node = next(
                (x for x in item if x.tag.endswith("episodeType")), None)
            type_text = ((type_node.text or "").strip()
                         if type_node is not None else "")
            ordinal_check: dict[str, Any] = {
                "name": "episode_number",
                "episode": ordinal_episode or None,
                "advertised": ordinal_text,
                "episode_type": type_text,
                "lane": "read" if guid_is_read else "interview",
            }
            if ordinal_node is None:
                result["issues"].append(
                    f"feed item for episode {ordinal_episode} advertises no "
                    f"<itunes:episode>, so every client orders it by date "
                    f"alone and prints no episode number")
            elif not ordinal_text:
                result["issues"].append(
                    f"feed item for episode {ordinal_episode} advertises an empty "
                    f"<itunes:episode>")
            elif not re.fullmatch(r"\d+", ordinal_text):
                result["issues"].append(
                    f"feed item for episode {ordinal_episode} advertises the "
                    f"malformed <itunes:episode> {ordinal_text!r}; the field "
                    f"must be a positive integer")
            elif int(ordinal_text) <= 0:
                result["issues"].append(
                    f"feed item for episode {ordinal_episode} advertises the "
                    f"<itunes:episode> {ordinal_text!r}; an ordinal of zero "
                    f"is not a position in any client's ordering")
            elif ordinal_episode and int(ordinal_text) != int(ordinal_episode):
                result["issues"].append(
                    f"feed item advertises <itunes:episode> {ordinal_text} "
                    f"while its GUID identifies episode {ordinal_episode}; the "
                    f"ordinal a client sorts and displays by disagrees with "
                    f"the episode's durable identity")
            if type_node is None:
                result["issues"].append(
                    f"feed item for episode {ordinal_episode} advertises no "
                    f"<itunes:episodeType>, which publish_feed.py emits as "
                    f"{EPISODE_TYPE_REQUIRED!r} on every item")
            elif type_text not in EPISODE_TYPE_ALLOWED:
                result["issues"].append(
                    f"feed item for episode {ordinal_episode} advertises the "
                    f"<itunes:episodeType> {type_text!r}, which is outside "
                    f"the specified vocabulary "
                    f"{list(EPISODE_TYPE_ALLOWED)}")
            elif type_text != EPISODE_TYPE_REQUIRED:
                result["issues"].append(
                    f"feed item for episode {ordinal_episode} advertises the "
                    f"<itunes:episodeType> {type_text!r}; every episode this "
                    f"pipeline produces is {EPISODE_TYPE_REQUIRED!r}, and a "
                    f"{type_text!r} is pinned outside the numbered run")
            result["checks"].append(ordinal_check)
            # ----------------------------------------------------------------
            # The item's OWN ARTWORK REFERENCE and CONTENT RATING.
            #
            # See ITEM_ARTWORK_REQUIRED above for why run 057's cover_art
            # union, run 063's URL-base guard and run 070's channel rating
            # gate all leave these two per-item fields unread.
            #
            # Refusals, each naming the episode:
            #   * no <itunes:image> on the item, or an empty/whitespace href
            #   * an item href naming artwork other than the channel's
            #   * no <itunes:explicit> on the item, or an empty value
            #   * a rating outside the specified vocabulary
            #   * a rating inside the vocabulary but not this show's
            #   * a rating differing from this show's only in CASE
            art_episode = ordinal_episode or ""
            art_node = next(
                (x for x in item if x.tag.endswith("image")), None)
            art_href = ((art_node.get("href") or "").strip()
                        if art_node is not None else "")
            rating_node = next(
                (x for x in item if x.tag.endswith("explicit")), None)
            rating_text = ((rating_node.text or "").strip()
                           if rating_node is not None else "")
            # The channel's artwork, for the agreement test. Taken from the
            # channel's own <itunes:image href> with the <image><url> text
            # node as the documented fallback, both of which publish_feed.py
            # writes from one BASE_URL constant.
            channel_art = ""
            _chan = root.find("channel")
            if _chan is not None:
                _chan_img = next(
                    (x for x in _chan if x.tag.endswith("image")
                     and (x.get("href") or "").strip()), None)
                if _chan_img is not None:
                    channel_art = (_chan_img.get("href") or "").strip()
                if not channel_art:
                    _legacy_img = _chan.find("image")
                    if _legacy_img is not None:
                        channel_art = (_legacy_img.findtext("url") or "").strip()
            artwork_check: dict[str, Any] = {
                "name": "item_artwork_rating",
                "episode": art_episode or None,
                "artwork": art_href or None,
                "channel_artwork": channel_art or None,
                "rating": rating_text,
                "lane": "read" if guid_is_read else "interview",
            }
            if art_node is None:
                result["issues"].append(
                    f"feed item for episode {art_episode} advertises no "
                    f"<itunes:image>, which publish_feed.py emits on every "
                    f"item; a client with no per-item artwork shows a blank "
                    f"tile in a now-playing view")
            elif not art_href:
                result["issues"].append(
                    f"feed item for episode {art_episode} advertises an "
                    f"empty <itunes:image> href, so its artwork resolves to "
                    f"nothing")
            elif channel_art and art_href != channel_art:
                result["issues"].append(
                    f"feed item for episode {art_episode} advertises the "
                    f"artwork {art_href!r} while the channel advertises "
                    f"{channel_art!r}; publish_feed.py writes both from one "
                    f"BASE_URL constant, so a disagreement means a hand-edit "
                    f"or a partial write")
            if rating_node is None:
                result["issues"].append(
                    f"feed item for episode {art_episode} advertises no "
                    f"<itunes:explicit>, which publish_feed.py emits as "
                    f"{REQUIRED_ITUNES_EXPLICIT!r} on every item; an item "
                    f"with no rating inherits nothing and is treated as "
                    f"unrated by a strict client")
            elif not rating_text:
                result["issues"].append(
                    f"feed item for episode {art_episode} advertises an "
                    f"empty <itunes:explicit>, so it advertises no content "
                    f"rating")
            elif rating_text.lower() not in ALLOWED_ITUNES_EXPLICIT:
                result["issues"].append(
                    f"feed item for episode {art_episode} advertises the "
                    f"<itunes:explicit> {rating_text!r}, which is not one of "
                    f"{list(ALLOWED_ITUNES_EXPLICIT)}")
            elif rating_text.lower() != REQUIRED_ITUNES_EXPLICIT:
                result["issues"].append(
                    f"feed item for episode {art_episode} advertises the "
                    f"<itunes:explicit> {rating_text!r}, but every episode "
                    f"this pipeline produces is "
                    f"{REQUIRED_ITUNES_EXPLICIT!r}")
            elif rating_text != REQUIRED_ITUNES_EXPLICIT:
                result["issues"].append(
                    f"feed item for episode {art_episode} advertises the "
                    f"<itunes:explicit> {rating_text!r}, which differs from "
                    f"{REQUIRED_ITUNES_EXPLICIT!r} only in case; a rating is "
                    f"machine-read")
            result["checks"].append(artwork_check)
            # Required human-readable fields. publish_feed.py reads an
            # interview item's title/description off pipeline/manifest.json and
            # defaults description to '' -- so an episode registered without a
            # `description` key ships a live item with an empty <description>,
            # which is how episode 002 went out. Nothing checked it: publish
            # returned ok: true and verify_feed returned ok: true with an empty
            # issue list, because every check it ran passed on a feed that was
            # structurally fine and editorially blank. verify_feed is what
            # publish_local() consults before shipping, so the assertion the
            # docs tell an operator to make by hand belongs here. No waiver --
            # an empty title or description is wrong for an import too, and a
            # waiver is a gate with the sign flipped (run 036).
            number = _feed_item_number(item) or "?"
            for field in ("title", "description"):
                field_value = (item.findtext(field) or "").strip()
                if not field_value:
                    result["issues"].append(
                        f"feed item for episode {number} has an empty <{field}>")
                    continue
                # ------------------------------------------------------
                # The field's VALUE, not merely its presence.
                #
                # Run 038 gated these two fields for EMPTINESS and nothing
                # ever read what they say. The channel <description> of the
                # SAME NAME is scored against PLACEHOLDER_DESCRIPTION_TOKENS
                # (run 067), so the asymmetry is channel-vs-item on one field
                # name -- run 072's granularity axis, where a field is gated
                # at one level and unread at the other.
                #
                # Unfilled boilerplate is the reachable defect. publish_feed.py
                # reads an interview item's title and description straight off
                # pipeline/manifest.json, so a stub value written at
                # registration ("TBD", "TODO") ships verbatim to every
                # subscriber as the episode's name and blurb -- the two fields
                # a listener reads FIRST, and the only two a podcast client
                # renders before any audio is fetched.
                #
                # No other audit can see it, because each reads its
                # expectations from the artifact under test:
                #   * run 038's arm is satisfied -- a placeholder is non-empty.
                #   * feedsync (076) regenerates feed.xml and index.html from
                #     the registries and compares bytes, so a bad registry
                #     INPUT regenerates IDENTICALLY forever and committed ==
                #     regenerated. It detects a hand-edit, never a bad input.
                #   * registry (053) compares ledger-vs-manifest membership
                #     and status, never a manifest field's editorial content.
                #   * coverage (005) relates published records to feed items
                #     and enclosure byte lengths.
                #
                # Form matched to the field (run 066). These are editorial
                # prose that is legitimately reworded, so there is NO
                # exact-match arm and deliberately NO required-content arm --
                # that would mandate content rather than detect a defect, the
                # mistake run 067 caught in its own draft. And deliberately NO
                # sibling-NAME arm: "human in the loop" is this show's
                # ordinary subject matter (episode 003 is about exactly that),
                # so a name guard here would refuse correct editorial copy.
                # What is tested is only what is WRONG: text that was never
                # written for this episode at all.
                #
                # No legacy waiver (run 036 -- a waiver is a gate with the
                # sign flipped): a placeholder title is wrong for an import
                # too.
                low = field_value.lower()
                for token in PLACEHOLDER_DESCRIPTION_TOKENS:
                    if token in low:
                        result["issues"].append(
                            f"feed item for episode {number} advertises the "
                            f"<{field}> {field_value!r}, which still carries "
                            f"the placeholder token {token!r}; it was never "
                            f"written for this episode and ships to every "
                            f"subscriber as the episode's "
                            f"{'name' if field == 'title' else 'blurb'}")
            # ----------------------------------------------------------
            # The advertised publication date.
            #
            # Every item carries a <pubDate> and until run 062 NOTHING read
            # it: the field appeared zero times in this module and in no
            # test. publish_feed.py derives an interview's value from
            # production_dates(), which mines state.json for the `rendered`
            # (fallback `published`) transition, and falls back to the
            # LEGACY_PUB_DATE constant 'Wed, 26 Aug 2026 03:45:00 +0000'
            # whenever no such event is found; a reading falls back to the
            # same constant on an unparseable `built_at`. That constant is a
            # FAILURE SENTINEL in exactly the sense duration()'s "00:00:00"
            # is -- it means "no production date was available" -- and a
            # fully-produced episode shipping it advertises itself as ~2.5
            # months older than it is.
            #
            # A feed is ordered by this field, so the consequence is not
            # cosmetic: a sentinel date buries a new episode below the whole
            # back catalogue in every date-sorted client, and a future date
            # pins an item to the top forever. Neither is visible anywhere
            # else -- the enclosure, duration, cover and deployed-item-set
            # checks all pass on an item whose date is wrong.
            #
            # This is the run-042/045/057/058 axis once more: an advertised
            # per-item field with zero readers. Like the duration check, the
            # advertised value is never its own evidence -- it is compared
            # against the production event the durable registries record,
            # re-derived here from the same data publish_feed.py mines.
            #
            # No waiver for a legacy item (run 036 -- a waiver is a gate with
            # the sign flipped): an absent, empty or malformed date is a
            # defect for an import too. A genuine import is accommodated
            # instead by EVIDENCE: the registries hold no production event
            # for it, so there is nothing to compare and the sentinel stands.
            advertised_pub = item.find("pubDate")
            pub_text = ((advertised_pub.text or "").strip()
                        if advertised_pub is not None else "")
            pub_check: dict[str, Any] = {
                "name": "pubdate", "episode": number,
                "advertised": pub_text or None,
            }
            if advertised_pub is None or not pub_text:
                result["issues"].append(
                    f"feed item for episode {number} has no <pubDate>")
            else:
                stamped = _parse_rfc2822(pub_text)
                if stamped is None:
                    result["issues"].append(
                        f"feed item for episode {number} has a malformed "
                        f"<pubDate> {pub_text!r}; expected an RFC 2822 date")
                else:
                    expected, origin = _expected_pubdate_epoch(number)
                    skew = stamped.timestamp() - time.time()
                    if skew > PUBDATE_FUTURE_ALLOWANCE_SECONDS:
                        result["issues"].append(
                            f"feed item for episode {number} advertises a "
                            f"<pubDate> {pub_text} that is "
                            f"{skew / 86400.0:.1f} days in the future, which "
                            f"pins it to the top of every date-sorted client")
                    if expected is not None:
                        pub_check["expected_source"] = origin
                        drift = abs(stamped.timestamp() - expected)
                        pub_check["drift_seconds"] = round(drift, 1)
                        if drift > PUBDATE_TOLERANCE_SECONDS:
                            result["issues"].append(
                                f"pubDate mismatch for episode {number}: the "
                                f"feed advertises {pub_text} but the {origin} "
                                f"records "
                                f"{datetime.fromtimestamp(expected, timezone.utc).strftime('%a, %d %b %Y %H:%M:%S +0000')}"
                                f" ({drift / 86400.0:.1f} days apart); "
                                f"re-publish so the date reflects production")
                    else:
                        pub_check["expected_source"] = (
                            "none: no production event in the registries")
            result["checks"].append(pub_check)
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
                else:
                    # ----------------------------------------------------
                    # Advertised duration vs the real decoded audio.
                    #
                    # Every item carries an <itunes:duration> and until run
                    # 058 NOTHING read it. publish_feed.py derives it from
                    # duration(), which parses ffmpeg stderr and returns the
                    # literal "00:00:00" whenever no Duration: line is found
                    # -- so an undecodable or truncated mp3 advertises a
                    # zero-length episode and every gate stayed green:
                    # enclosures are checked by BYTE LENGTH, which a file of
                    # garbage at the right size satisfies, and preflight()
                    # sizes and hashes the audio without ever decoding it.
                    #
                    # This is the run-042/045/057 axis again -- an advertised
                    # per-item field with zero readers. The cover art (057)
                    # and the deployed item set (056) were the previous two;
                    # the duration is the last one the feed emits. It is also
                    # the only check here that proves the enclosure is real
                    # AUDIO rather than bytes of the right length.
                    #
                    # No waiver, legacy included: a client that reads
                    # 00:00:00 renders an unplayable episode for an import
                    # too, and a waiver is a gate with the sign flipped
                    # (run 036). A missing local enclosure is already its own
                    # issue above, so this block only runs when the file is
                    # present and its length agrees.
                    duration_node = next(
                        (x for x in item if x.tag.endswith("duration")), None)
                    advertised = (
                        (duration_node.text or "").strip()
                        if duration_node is not None else "")
                    duration_check: dict[str, Any] = {
                        "name": "duration", "episode": number,
                        "advertised": advertised or None,
                    }
                    if duration_node is None or not advertised:
                        result["issues"].append(
                            f"feed item for episode {number} has no "
                            f"<itunes:duration>")
                    else:
                        claimed = _parse_hhmmss(advertised)
                        duration_check["advertised_seconds"] = claimed
                        if claimed is None:
                            result["issues"].append(
                                f"feed item for episode {number} has a "
                                f"malformed <itunes:duration> "
                                f"{advertised!r}; expected HH:MM:SS")
                        elif claimed == 0:
                            result["issues"].append(
                                f"feed item for episode {number} advertises "
                                f"<itunes:duration> 00:00:00, which is "
                                f"publish_feed.duration()'s failure sentinel "
                                f"for an mp3 it could not decode; re-render "
                                f"or re-publish {local.name}")
                        else:
                            actual = _audio_duration_seconds(local)
                            duration_check["actual_seconds"] = (
                                round(actual, 1) if actual is not None else None)
                            if actual is None:
                                result["issues"].append(
                                    f"enclosure {local.name} for episode "
                                    f"{number} could not be decoded, so its "
                                    f"advertised duration {advertised} "
                                    f"describes nothing; the file is the "
                                    f"right byte length but is not playable "
                                    f"audio")
                            elif abs(actual - claimed) > DURATION_TOLERANCE_SECONDS:
                                result["issues"].append(
                                    f"duration mismatch for {local.name}: the "
                                    f"feed advertises {advertised} "
                                    f"({claimed}s) but the audio decodes to "
                                    f"{actual:.0f}s")
                    result["checks"].append(duration_check)
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
                # ------------------------------------------------------
                # The advertised show-notes link's VALUE.
                #
                # See SHOW_NOTES_LINK_REQUIRED above. The probes below ask
                # only whether the target EXISTS; this asks whether it is
                # the RIGHT target. Scored against the item's GUID-derived
                # number, so it is a cross-field agreement test.
                # ------------------------------------------------------
                notes_number = _feed_item_number(item)
                notes_is_read = bool(notes_number) and is_reading(
                    notes_number, read_manifest_episodes)
                expected_notes = (
                    {f"episode-{notes_number}-reading-notes.md",
                     f"episode-{notes_number}-notes.md"}
                    if notes_is_read
                    else {f"episode-{notes_number}-notes.md"})
                notes_check: dict[str, Any] = {
                    "name": "show_notes_link",
                    "episode": notes_number or None,
                    "lane": "read" if notes_is_read else "interview",
                    "advertised": list(hrefs),
                    "expected": sorted(expected_notes),
                }
                if not hrefs:
                    result["issues"].append(
                        f"feed item for episode "
                        f"{notes_number or '<unidentified>'} advertises no "
                        f"show-notes link in its <content:encoded>; the "
                        f"notes carry the unabridged disclosure, the "
                        f"evidence boundaries and every numbered citation "
                        f"with its Zotero link, and this href is a "
                        f"listener's only route to them")
                for href in hrefs:
                    low = href.lower()
                    for bad in FORBIDDEN_ADVERTISED_SUBSTRINGS:
                        if bad in low:
                            result["issues"].append(
                                f"feed item for episode "
                                f"{notes_number or '<unidentified>'} "
                                f"advertises the show-notes link {href!r}, "
                                f"which carries the cross-show substring "
                                f"{bad!r}; the two shows must never share a "
                                f"URL or a GUID")
                    if low.startswith(("http://", "https://")) and not any(
                            _under_advertised_base(href, base)
                            for base in EXPECTED_ADVERTISED_BASES):
                        result["issues"].append(
                            f"feed item for episode "
                            f"{notes_number or '<unidentified>'} advertises "
                            f"the show-notes link {href!r}, which is not "
                            f"under this show's base "
                            f"{EXPECTED_ADVERTISED_BASES[0]}; a subscriber "
                            f"resolves the advertised URL, not the local "
                            f"filename")
                    name = Path(urllib.parse.urlparse(href).path).name
                    if notes_number and name not in expected_notes:
                        result["issues"].append(
                            f"feed item for episode {notes_number} "
                            f"advertises the show-notes link {href!r}, which "
                            f"resolves to {name!r} and not this episode's "
                            f"{sorted(expected_notes)[0]!r}; the link sends "
                            f"every listener to another episode's citations, "
                            f"evidence boundaries and Zotero links")
                result["checks"].append(notes_check)
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
        # ------------------------------------------------------------------
        # The human-facing landing page.
        #
        # publish_feed.py writes feed-site/index.html on EVERY publish and
        # push_to_remote() syncs the whole feed-site/ directory to the repo
        # root, so the page is a deployed deliverable exactly like feed.xml,
        # the enclosures, the show notes and the cover art. Until run 060
        # NOTHING read it: robust_pipeline.py contained zero references to
        # it, so deleting it, emptying it to zero bytes, corrupting it to
        # binary junk, or drifting it until it advertised episodes the feed
        # does not carry all returned ok: true with an EMPTY issue list --
        # a verdict indistinguishable from the intact tree.
        #
        # That verdict is what publish_local() refuses on and what
        # push_to_remote()'s wait loop breaks on to declare a deploy live, so
        # a push whose landing page never landed reported success. It is the
        # run-042/045/056/057/058 axis once more: 056 was the deployed item
        # set, 057 the cover art, 058 the advertised duration, and the index
        # page is the last file this pipeline deploys that no gate inspects.
        #
        # The drift half matters more than the existence half. The page is
        # generated from the same EP/read_episodes() derivation as the feed,
        # so the two agreeing is normally automatic -- which is precisely why
        # a disagreement means a partial write or a hand-edit, and why it
        # should never be discovered by a listener. An asset the page links
        # that is not on disk is a dead link for a human reader even when
        # every feed enclosure is perfect.
        #
        # No waiver, legacy included: a 404 or a dead link is wrong for an
        # import too, and a waiver is a gate with the sign flipped (run 036).
        if feed_path:
            index_path = feed_path.parent / "index.html"
            index_check: dict[str, Any] = {"name": "index_page",
                                          "file": str(index_path.name)}
            if not index_path.exists():
                result["issues"].append(
                    "missing local landing page index.html, which "
                    "publish_feed.py writes and push deploys")
            elif index_path.stat().st_size == 0:
                result["issues"].append("local landing page index.html is empty")
            else:
                index_text = index_path.read_text(errors="replace")
                index_check["bytes"] = index_path.stat().st_size
                if "<html" not in index_text.lower():
                    result["issues"].append(
                        "local landing page index.html is not HTML; it "
                        "contains no <html> element")
                else:
                    # The page's own identity must name the same show as the
                    # feed. Both come from publish_feed.py's hardcoded
                    # strings, so a disagreement is a hand-edit or a partial
                    # write -- and the page is a deployed deliverable a human
                    # reader sees first.
                    for slot, pattern in (("<title>", r"<title>([^<]*)</title>"),
                                          ("<h1>", r"<h1>([^<]*)</h1>")):
                        found = re.search(pattern, index_text,
                                          flags=re.IGNORECASE)
                        if found is None:
                            result["issues"].append(
                                f"landing page index.html has no {slot} "
                                f"element, so it advertises no show name")
                            continue
                        page_name = found.group(1).strip()
                        index_check[f"page_{slot.strip('<>/')}"] = page_name
                        if not page_name:
                            result["issues"].append(
                                f"landing page index.html has an empty "
                                f"{slot}, so it advertises no show name")
                        elif page_name != SHOW_TITLE:
                            result["issues"].append(
                                f"landing page index.html advertises "
                                f"{slot}{page_name!r}, but this show is "
                                f"{SHOW_TITLE!r}")
                        for bad in FORBIDDEN_SHOW_TITLES:
                            if bad.lower() in page_name.lower():
                                result["issues"].append(
                                    f"landing page index.html advertises "
                                    f"{slot}{page_name!r}, which names the "
                                    f"sibling show {bad!r}")
                    # Every local asset the page links must exist on disk.
                    linked = sorted(set(re.findall(
                        r'href="([^":/?#]+\.(?:mp3|md|xml|html|png|svg))"',
                        index_text)))
                    index_check["links"] = linked
                    for name in linked:
                        if name == index_path.name:
                            continue
                        if not (feed_path.parent / name).exists():
                            result["issues"].append(
                                f"landing page index.html links {name}, "
                                f"which is not deployed in "
                                f"{feed_path.parent.name}/")
                    # Every episode the feed carries must be listed, or the
                    # page and the feed disagree about the catalogue.
                    feed_numbers = {n for n in
                                    (_feed_item_number(i) for i in items) if n}
                    page_numbers = set(re.findall(r"episode-(\d+)", index_text))
                    index_check["feed_episodes"] = sorted(feed_numbers)
                    index_check["page_episodes"] = sorted(page_numbers)
                    for number in sorted(feed_numbers - page_numbers):
                        result["issues"].append(
                            f"landing page index.html omits episode "
                            f"{number}, which the feed carries")
                    for number in sorted(page_numbers - feed_numbers):
                        result["issues"].append(
                            f"landing page index.html advertises episode "
                            f"{number}, which the feed does not carry")
            if remote:
                index_url = remote.rstrip("/") + "/index.html"
                try:
                    with urllib.request.urlopen(index_url, timeout=timeout) as response:
                        status = response.status
                        body = response.read(64)
                    if status != 200 or not body:
                        raise IOError(f"HTTP {status}")
                    index_check["remote"] = {"url": index_url, "http": status}
                except Exception as exc:
                    result["issues"].append(
                        f"remote landing page check failed for {index_url}: {exc}")
            result["checks"].append(index_check)

        # ------------------------------------------------------------------
        # The TREE-ROOT MIRROR of every deployed deliverable. See
        # ROOT_MIRROR_SUFFIXES above for why eight of the ten root copies had
        # zero readers, why run 057's cover arm does not reach them, and why
        # the root is what GitHub Pages actually serves.
        #
        # Compared by digest against the feed-site copy, which is the
        # authoritative one and is already gated field-by-field above. An
        # absent root copy waives (run 057's ruling); only present-and-
        # different refuses. No legacy waiver (run 036).
        # ------------------------------------------------------------------
        if feed_path:
            site_dir = feed_path.parent
            mirror_check: dict[str, Any] = {"name": "root_mirror",
                                            "root": str(ROOT)}
            mirrored: list[str] = []
            absent: list[str] = []
            # Scoped to THIS tree's deployed directory. The mirror
            # relationship holds between ROOT and ROOT/"feed-site" -- the pair
            # publish_local() and push_to_remote() always use -- so comparing
            # an arbitrary caller-supplied feed-site against this tree's root
            # copies would report unrelated files as drift.
            expected_site = (ROOT / "feed-site").resolve()
            if site_dir.is_dir() and site_dir.resolve() == expected_site:
                for deployed in sorted(site_dir.iterdir()):
                    if not deployed.is_file():
                        continue
                    name = deployed.name
                    if name in ROOT_MIRROR_EXEMPT_NAMES:
                        continue
                    if deployed.suffix.lower() not in ROOT_MIRROR_SUFFIXES:
                        continue
                    root_copy = ROOT / name
                    if not (root_copy.exists() and root_copy.is_file()):
                        absent.append(name)
                        continue
                    site_digest = sha256(deployed)
                    root_digest = sha256(root_copy)
                    if site_digest == root_digest:
                        mirrored.append(name)
                    else:
                        result["issues"].append(
                            f"deployed deliverable {name} differs between the "
                            f"tree root and {site_dir.name}/ (root "
                            f"{root_digest[:12]} / {root_copy.stat().st_size} "
                            f"bytes vs deployed {site_digest[:12]} / "
                            f"{deployed.stat().st_size} bytes); publish_feed.py "
                            f"writes only {site_dir.name}/, so the two copies "
                            f"are hand-kept in sync and GitHub Pages serves "
                            f"the root -- re-copy it")
            mirror_check["mirrored"] = mirrored
            mirror_check["no_root_copy"] = absent
            result["checks"].append(mirror_check)

    except Exception as exc:
        result["issues"].append(f"feed parse/check failed: {exc}")
    result["ok"] = not result["issues"]
    return result


def _emitted_episode_numbers() -> set[str]:
    """Every episode number the next publish_feed.main() will put in the feed.

    Read from publish_feed's OWN derivation rather than re-implemented here, so
    the gate's scope cannot drift from what actually gets emitted and copied
    into feed-site/. Both lanes are covered: interview_episodes() reads the
    manifest plus the ledger status, read_episodes() reads read-episodes.json.

    A derivation that cannot be imported or that raises returns the empty set,
    leaving the caller's own selection to be gated as before: this helper can
    only ever widen the gated set, never narrow it.
    """
    try:
        try:
            from .publish_feed import interview_episodes, read_episodes
        except ImportError:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from publish_feed import interview_episodes, read_episodes
        numbers = {str(row[0]) for row in interview_episodes()}
        numbers |= {str(num) for num, _ in read_episodes()}
        return numbers
    except Exception:
        return set()


def publish_local(episodes: list[str] | None = None, remote: str | None = None) -> dict[str, Any]:
    """Build the checked-in local feed and verify it; never performs a git push.

    Genuinely imported history is treated as legacy and skips preflight. Any
    other episode must pass the review gate and audio preflight before it can
    enter the local feed.

    The exemption is keyed on _legacy_episode_numbers(), NOT on the ledger
    status literal "published". That literal does not establish imported
    history and never did: this function itself writes it (verified ->
    published), so every episode produced here occupies it between publish and
    the Zotero move to published_and_moved, and load_ledger()'s bootstrap maps
    published_and_moved -> "published", putting the WHOLE catalogue there at
    once whenever the ledger is rebuilt from manifest.json. Run 036 established
    exactly this and fixed the same one-part test in verify_feed(), but left it
    standing here -- in the actual publication gate, where the waiver skips the
    review gate, the disclosure and citation checks and the audio check
    together, while publish_feed.main() re-copies the episode's notes and audio
    to feed-site for the next push to deploy.

    _legacy_episode_numbers() requires all three of: the literal status
    "published", no in-pipeline production transition, and no script.md on
    disk. It can only ever narrow the exempt set, so this change adds refusals
    and grants nothing.
    """
    try:
        from .publish_feed import main as build_feed
    except ImportError:
        from publish_feed import main as build_feed
    ledger = load_ledger()
    selected = episodes or sorted(load_manifest().get("episodes", {}))
    checks = []
    legacy_numbers = _legacy_episode_numbers()
    # Gate every episode this publish will EMIT, not merely the ones named.
    #
    # `selected` controls which ledger records transition, and that is all it
    # ever controlled. It does NOT bound the blast radius: publish_feed.main()
    # rebuilds the whole feed from its own derivation (interview_episodes()
    # plus read_episodes()) and re-copies every emitted episode's audio and
    # notes into feed-site/ for the next push to deploy. So
    # `publish --episode 001` re-shipped every other episode without running a
    # single check on it, and a bare `publish` covered them only by the
    # accident of the manifest and the feed derivation agreeing.
    #
    # Proven reachable in BOTH lanes on real code: an interview whose review
    # panel is missing, and a reading whose audio was swapped after its verdict
    # (the run-042 provenance refusal), each stayed in the rebuilt feed and had
    # their bytes re-copied into feed-site/ while `publish --episode 001`
    # returned ok: true with an empty issue list. The reading case is the
    # sharper one, because read_episodes() emits on the registry's `verified`
    # flag alone and nothing on the publish path re-derived it.
    #
    # This is run 041's erasure check with the sign flipped: that one asks
    # whether the feed LOST an episode it should carry, this asks whether it
    # CARRIES one nothing gated. It grants nothing -- the selected set is still
    # gated exactly as before, legacy exemptions are unchanged, and every
    # addition is a refusal.
    for number in sorted(set(selected) | _emitted_episode_numbers()):
        if number not in legacy_numbers:
            check = preflight(number, require_audio=True, enforce_review=True)
            checks.append(check)
            if not check["ok"]:
                raise ValueError(f"publish preflight failed for {number}: {'; '.join(check['issues'])}")
    with PipelineLock(timeout=0):
        build_feed()
        result = verify_feed(ROOT / "feed-site" / "feed.xml", remote)
        if not result["ok"]:
            raise ValueError("local publication verification failed: " + "; ".join(result["issues"]))
        # Every episode the registries record as published must still HAVE an
        # item. verify_feed() only inspects the items the feed CONTAINS, so it
        # is structurally unable to see an episode that dropped out: publish
        # rebuilds the feed from the manifest plus the ledger status, and any
        # cause of an item leaving that derivation (a lost manifest entry, a
        # status moved outside the published family) erases a live episode while
        # every check passes on the shortened feed it actually built. That is
        # the erasure half of the run-005 silent-skip class, and the detector
        # for it already existed -- feed_coverage() -- but was read-only, CLI
        # only, and consulted by nothing in the publish path.
        #
        # It grants nothing: it cannot pass an episode verify_feed failed, it
        # only adds a refusal. Checked BEFORE any ledger transition so a
        # publish that would erase the catalogue leaves no state behind.
        coverage = feed_coverage(ROOT / "feed-site" / "feed.xml")
        if not coverage["ok"]:
            raise ValueError(
                "local publication coverage failed: " + "; ".join(coverage["issues"]))
        for number in selected:
            record = ledger.setdefault("episodes", {}).setdefault(number, {"status": "planned", "transitions": []})
            if record.get("status") == "rendered":
                transition(ledger, number, "verified", "local feed checks passed")
            if record.get("status") == "verified":
                transition(ledger, number, "published", "local feed built and verified; remote push remains manual")
        save_ledger(ledger)
    return {"ok": True, "episodes": selected, "preflight": checks, "verification": result, "coverage": coverage, "external_push": "not performed"}



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

def _deploy_drift_verdict(remote: str | None = None) -> dict[str, Any]:
    """deploy_drift()'s verdict for push_to_remote(), fail-open on a fault.

    Deliberately fail-open (run 055's rule for a helper on the publish path):
    a comparator that could raise would make every deploy impossible, which is
    a worse failure than the class it guards. An exception therefore yields
    ``ok: true`` with the reason recorded, while a DEFINITE ``ok: false`` from
    the comparator is a refusal and is never downgraded.

    deploy_drift() stays read-only and is still not a publication gate: it
    grants nothing, and publish_local()/verify_feed() continue not to call it.
    This is a POST-push deploy assertion, not an episode gate.
    """
    try:
        return deploy_drift(remote)
    except Exception as exc:  # pragma: no cover - comparator fault
        return {"ok": True, "issues": [],
                "unavailable": f"{type(exc).__name__}: {exc}"}


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
        #
        # The liveness criterion is TWO questions, not one. verify_feed()
        # answers "does the deployed feed parse, carry the right GUIDs, and
        # are its assets fetchable" -- and every one of its remote probes is
        # an EXISTENCE probe: show notes, cover art and the landing page are
        # checked for HTTP 200 plus a few bytes, enclosures for their
        # Content-Range total only, and the deployed feed by GUID set. So a
        # deploy whose feed text, notes, cover or landing page was rewritten,
        # or whose enclosure bytes were swapped at the same byte length,
        # satisfied it with an EMPTY issue list and was declared live.
        #
        # deploy_drift() asks the strictly different question -- do the
        # deployed BYTES equal the local bytes -- and already detected every
        # one of those classes. It was CLI-only, so the detector existed but
        # no gate and no shipping command reached it; the operator's own
        # live-vs-local md5 habit was the only thing covering the gap, one
        # slice late. That is run 041's lesson (when a read-only audit
        # detects a class the gates do not, wire it into the gate) and run
        # 045's (ask whether a field's reader is reachable from the command
        # the operator runs to SHIP, not merely whether a reader exists).
        #
        # Both must pass to break the wait loop, because Pages lag makes an
        # early iteration legitimately stale on either axis. Reported under
        # its own top-level key rather than folded into verify_feed's verdict
        # (run 041's third harness trap: a distinct assertion gets a distinct
        # key, never another check's dict).
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            v = verify_feed(str(ROOT / "feed-site" / "feed.xml"), remote=FEED_BASE)
            result["live"] = v
            d = _deploy_drift_verdict()
            result["drift"] = d
            if v["ok"] and d["ok"]:
                break
            time.sleep(30)
        live_ok = bool(result["live"]) and not result["live"]["issues"]
        drift = result.get("drift") or {}
        drift_ok = bool(drift.get("ok", True))
        result["ok"] = live_ok and drift_ok
        if not result["ok"]:
            issues = list(result["live"]["issues"]) if result.get("live") else []
            issues.extend(drift.get("issues", []) or [])
            result["issues"] = issues
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
    """Machine-readable health report for the scheduler and the watchdog.

    This is **monitoring, not a gate**. It grants nothing: ``preflight()``,
    ``review_gate()``, ``verify_feed()`` and the read lane's ``fidelity_gate()``
    are the publication gates and none of them consults this function.

    ``healthy`` used to be pinned ``False`` by construction, which made the
    signal worthless -- it could not come back true however clean the pipeline
    was. A ``planned`` stub has no ``script.md`` *by definition* -- that is what
    ``planned`` means -- yet it was failed by a deliverables preflight. 501 had
    been doing this for 53 attempts and was the sole reason this tree reported
    unhealthy.

    Each episode is therefore judged by the rules that apply to it, and the
    inapplicable findings are PRESERVED rather than discarded -- under
    ``planned_audit_issues`` / ``read_audit_issues``, mirroring the
    long-standing ``legacy_audit_issues`` treatment.

    Unlike the sibling Human in the Loop tree, ``preflight()`` here has been
    lane-aware since run 029 (it branches on manifest ``kind``), so a
    correctly-registered reading already passes the interview-rule half and
    needs no waiver. What it does NOT do is reach the read lane's gate:
    ``status()`` calls preflight with ``enforce_review=False``, so a reading
    recorded as published whose fidelity gate is not ``verified`` was reported
    healthy. That is the run-422 live-but-unrecorded class, and it is now
    detection this classifier GAINS.
    """
    ledger = load_ledger()
    read_episodes = (load_read_manifest().get("episodes") or {})
    report = {"generated_at": utc_now(), "ledger_updated_at": ledger.get("updated_at"), "episodes": {}, "healthy": True}
    for number, rec in sorted(ledger.get("episodes", {}).items()):
        pre = preflight(number, require_audio=False, enforce_review=False)
        state = str(rec.get("status") or "")
        entry = {"state": rec.get("status"), "attempts": rec.get("attempts", 0), "errors": rec.get("errors", [])[-3:]}
        # The reading test comes FIRST and deliberately so. The legacy arm
        # below keys on the exact status "published", so a reading carrying
        # that status instead of "published_and_moved" would be classified as
        # a legacy INTERVIEW and skip its fidelity gate altogether. A reading
        # can never be legacy: the lane postdates every episode in this tree.
        if is_reading(number, read_episodes):
            # A reading's gate is the automated word-fidelity verdict in
            # read-episodes.json, not the interview reviewer panel. Read it the
            # way fidelity_gate() and publish_feed.read_episodes() do.
            gate = read_episodes.get(str(number), {})
            verified = bool(gate.get("verified")) if isinstance(gate, dict) else False
            entry["kind"] = "read"
            entry["read_gate_verified"] = verified
            if state.startswith("published"):
                entry["preflight_ok"] = verified
                entry["issues"] = [] if verified else [
                    f"reading {number} is recorded as {state} but its fidelity gate "
                    "is not verified in pipeline/read-episodes.json"
                ]
            elif state == "planned":
                entry["preflight_ok"], entry["issues"] = True, []
            else:
                entry["preflight_ok"], entry["issues"] = pre["ok"], pre["issues"]
            if pre["issues"] and not entry["issues"]:
                entry["read_audit_issues"] = pre["issues"]
        elif number in _legacy_episode_numbers():
            # Legacy published episodes predate checked-in scripts/review
            # panels; retain their audit issues without treating them as an
            # active failure.
            entry["preflight_ok"], entry["issues"] = True, []
            if pre["issues"]:
                entry["legacy_audit_issues"] = pre["issues"]
        elif state == "planned":
            # A planned episode has not claimed to have deliverables yet, so
            # their absence is the expected state and not a defect.
            entry["preflight_ok"], entry["issues"] = True, []
            if pre["issues"]:
                entry["planned_audit_issues"] = pre["issues"]
        else:
            entry["preflight_ok"], entry["issues"] = pre["ok"], pre["issues"]
        report["episodes"][number] = entry
        if state in {"failed", "blocked", "rendering"} or not entry["preflight_ok"]:
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



def _feed_diff_sample(committed: str, regenerated: str,
                      window: int = 160, limit: int = 20) -> list[str]:
    """Human-readable sample of where two feed documents diverge.

    ``feed.xml`` writes each ``<item>`` on one very long line, so a unified
    diff truncated to a fixed prefix reports two lines whose visible portions
    are identical -- technically correct and operationally useless. For any
    differing pair longer than the window this emits a focused slice centred
    on the first differing character, which is what makes the changed value
    (a rewritten notes sentence, a retitled episode) legible.
    """
    import difflib

    sample: list[str] = []
    clines = committed.splitlines()
    rlines = regenerated.splitlines()
    matcher = difflib.SequenceMatcher(None, clines, rlines, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if len(sample) >= limit:
            sample.append("... diff truncated ...")
            break
        if tag == "replace" and (i2 - i1) == 1 and (j2 - j1) == 1:
            old, newline = clines[i1], rlines[j1]
            if max(len(old), len(newline)) > window:
                cut = next((k for k in range(min(len(old), len(newline)))
                            if old[k] != newline[k]),
                           min(len(old), len(newline)))
                start = max(0, cut - window // 2)
                sample.append(f"@@ line {i1 + 1} char {cut} @@")
                sample.append("- ..." + old[start:start + window] + "...")
                sample.append("+ ..." + newline[start:start + window] + "...")
                continue
        for k in range(i1, i2):
            sample.append(f"- {clines[k][:400]}")
        for k in range(j1, j2):
            sample.append(f"+ {rlines[k][:400]}")
    return sample


# Text artifacts publish_feed.main() writes into feed-site/ that feed_sync()
# compares byte-for-byte. .mp3 enclosures are excluded deliberately: they are
# copies of the episode audio, already audited for presence and advertised
# length by `coverage` and decoded by the run-058 duration check, and hashing
# them on every audit would make the command unaffordable.
SYNC_TEXT_SUFFIXES = {".html", ".json", ".svg", ".txt", ".xml"}


def feed_sync(site: Path | None = None) -> dict[str, Any]:
    """Audit that the committed feed-site bytes equal a fresh regeneration.

    READ-ONLY. ``publish_feed.py`` builds every file in ``feed-site/`` from
    the registries -- ``manifest.json`` (``title``, ``description``,
    ``number``, ``kind``), ``read-episodes.json`` (``verified``, ``coverage``,
    ``source_words``, ``citation``, ``title``) and ``state.json`` (the
    production timestamps the ``<pubDate>`` is formatted from) -- plus the
    on-disk enclosures and each episode's ``episode-notes.md``. Editing any of
    those WITHOUT re-running publish leaves the committed bytes stale, and
    every other audit in this tree still passes:

    * ``coverage`` asks whether every published episode has a feed item and
      whether each enclosure exists at its advertised length -- about the
      committed feed only.
    * ``registry`` asks whether ``state.json`` and ``manifest.json`` agree,
      and never reads ``feed-site/`` at all.
    * ``verify`` scores the committed document against itself and against
      disk: it reads every advertised field, but its expectations come from
      the same committed bytes, so a stale title is self-consistent.
    * ``reconcile`` compares each ``episodes/NNN`` directory to its ledger
      record and never reads the feed.
    * ``drift`` compares the LIVE bytes to the LOCAL bytes -- so once a stale
      commit is deployed, live equals local and the audit passes.

    None of them asks whether the committed bytes still equal the *generated*
    bytes, which is the one question that detects a registry edit that was
    never republished. In the sibling tree that class was caught only by an
    md5 diff against the live site, which needs network and only works after a
    deploy; this answers the same question locally and before the push.

    It audits every text artifact the generator writes -- ``feed.xml``, each
    ``<base>-notes.md`` and ``index.html`` -- because a check that regenerates
    a whole site and compares one output leaves the rest audited by nothing.
    The notes files matter most: a notes-body edit leaves ``feed.xml``
    byte-identical whenever the numbered citation entries are untouched, and
    the notes are a published deliverable carrying the unabridged disclosure,
    the evidence boundaries and every Zotero link.

    It is **not** a publication gate: it grants nothing, writes nothing into
    the pipeline, and does not replace ``preflight``/``review_gate``/
    ``verify_feed``/the read lane's fidelity gate. It renders into a private
    temporary directory, so ``feed-site/`` is never touched.

    ``ok: false`` with a populated ``diff_sample`` means: run
    ``publish --episode NNN`` to regenerate, inspect the diff, and deploy.
    """
    site_dir = Path(site) if site is not None else (ROOT / "feed-site")
    report: dict[str, Any] = {
        "ok": True,
        "site": str(site_dir),
        "committed_md5": None,
        "regenerated_md5": None,
        "committed_items": None,
        "regenerated_items": None,
        "diff_sample": [],
        "notes_checked": 0,
        "notes_stale": [],
        "notes_missing": [],
        "site_text_checked": 0,
        "site_text_stale": [],
        "site_text_missing": [],
        "issues": [],
    }
    committed = site_dir / "feed.xml"
    if not committed.is_file():
        report["ok"] = False
        report["issues"].append(f"no committed feed at {committed}")
        return report

    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_feedsync_publish_feed", PUBLISH_FEED_PATH)
    if spec is None or spec.loader is None:
        report["ok"] = False
        report["issues"].append(f"cannot load {PUBLISH_FEED_PATH}")
        return report
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # pragma: no cover - import-time failure
        report["ok"] = False
        report["issues"].append(f"publish_feed.py failed to import: {exc}")
        return report

    # Redirect the generator's output at its SITE global so the real
    # feed-site/ is never written. publish_feed.main() copies enclosures and
    # notes into SITE as well, which is why this needs a scratch directory
    # rather than only capturing the returned XML.
    scratch = Path(tempfile.mkdtemp(prefix="feedsync-"))
    real_site = getattr(module, "SITE", None)
    try:
        module.SITE = scratch
        try:
            # publish_feed.main() prints a progress line; this command's
            # stdout must stay parseable JSON, so swallow it.
            with contextlib.redirect_stdout(io.StringIO()):
                module.main()
        except SystemExit as exc:
            report["ok"] = False
            report["issues"].append(f"publish_feed.main() refused to build: {exc}")
            return report
        except Exception as exc:
            report["ok"] = False
            report["issues"].append(
                f"publish_feed.main() raised {type(exc).__name__}: {exc}")
            return report
        regenerated = scratch / "feed.xml"
        if not regenerated.is_file():
            report["ok"] = False
            report["issues"].append("publish_feed.main() produced no feed.xml")
            return report

        committed_text = committed.read_text()
        regenerated_text = regenerated.read_text()
        report["committed_md5"] = hashlib.md5(committed_text.encode()).hexdigest()
        report["regenerated_md5"] = hashlib.md5(regenerated_text.encode()).hexdigest()
        try:
            report["committed_items"] = len(
                ET.fromstring(committed_text).findall("./channel/item"))
            report["regenerated_items"] = len(
                ET.fromstring(regenerated_text).findall("./channel/item"))
        except ET.ParseError as exc:
            report["issues"].append(
                f"feed did not parse while counting items: {exc}")

        # publish_feed.main() also copies every episode's episode-notes.md
        # into SITE as "<base>-notes.md". Those are published deliverables --
        # the feed links them (run 075) and they are fetched live -- but
        # feed.xml stays byte-identical for a notes-body edit whenever the
        # numbered citation entries are untouched. The scratch render already
        # contains them, so this costs nothing extra.
        for regen_notes in sorted(scratch.glob("*-notes.md")):
            committed_notes = site_dir / regen_notes.name
            report["notes_checked"] += 1
            if not committed_notes.is_file():
                report["ok"] = False
                report["notes_missing"].append(regen_notes.name)
                report["issues"].append(
                    f"{regen_notes.name} is generated by publish_feed.py but "
                    f"is not committed in {site_dir.name}/")
                continue
            regen_md5 = hashlib.md5(regen_notes.read_bytes()).hexdigest()
            committed_md5 = hashlib.md5(committed_notes.read_bytes()).hexdigest()
            if regen_md5 != committed_md5:
                report["ok"] = False
                report["notes_stale"].append({
                    "file": regen_notes.name,
                    "committed_md5": committed_md5,
                    "regenerated_md5": regen_md5,
                    "committed_bytes": committed_notes.stat().st_size,
                    "regenerated_bytes": regen_notes.stat().st_size,
                })
                report["issues"].append(
                    f"committed {regen_notes.name} differs from the episode's "
                    f"current episode-notes.md; a notes edit was not republished")

        # The third class: index.html, the site's only human entry point,
        # built from the same derivation as the feed. verify_feed()'s
        # index_page check reads its <title>/<h1>, its local hrefs and its
        # episode-NNN number set -- so it catches an omitted episode and a
        # wrong show name, but NOT a rewritten episode title inside a list
        # entry, which is a value only the generator knows. Rather than
        # naming index.html, audit everything textual the generator wrote
        # except the two classes handled above, so a future artifact is
        # covered the day it is added.
        for regen in sorted(scratch.iterdir()):
            if not regen.is_file() or regen.is_symlink():
                continue
            if regen.name == "feed.xml" or regen.name.endswith("-notes.md"):
                continue
            if regen.suffix.lower() not in SYNC_TEXT_SUFFIXES:
                continue
            committed_file = site_dir / regen.name
            report["site_text_checked"] += 1
            if not committed_file.is_file():
                report["ok"] = False
                report["site_text_missing"].append(regen.name)
                report["issues"].append(
                    f"{regen.name} is generated by publish_feed.py but is not "
                    f"committed in {site_dir.name}/")
                continue
            regen_md5 = hashlib.md5(regen.read_bytes()).hexdigest()
            committed_md5 = hashlib.md5(committed_file.read_bytes()).hexdigest()
            if regen_md5 != committed_md5:
                report["ok"] = False
                report["site_text_stale"].append({
                    "file": regen.name,
                    "committed_md5": committed_md5,
                    "regenerated_md5": regen_md5,
                    "committed_bytes": committed_file.stat().st_size,
                    "regenerated_bytes": regen.stat().st_size,
                })
                report["issues"].append(
                    f"committed {regen.name} differs from what publish_feed.py "
                    f"generates now; a registry edit was not republished")

        if report["committed_md5"] != report["regenerated_md5"]:
            report["ok"] = False
            report["issues"].append(
                "committed feed-site/feed.xml differs from what publish_feed.py "
                "generates from the current registries; a registry was edited "
                "without republishing")
            # feed.xml puts each <item> on a single very long line, so a plain
            # unified diff truncated per line shows only the identical prefix.
            # Emit a window centred on the first divergence instead, so the
            # changed value is actually visible.
            report["diff_sample"] = _feed_diff_sample(
                committed_text, regenerated_text)
    finally:
        if real_site is not None:
            module.SITE = real_site
        shutil.rmtree(scratch, ignore_errors=True)
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
    sub.add_parser("registry")
    p = sub.add_parser("drift", help="audit the live site against local feed-site bytes")
    p.add_argument("--remote", default=None)
    p.add_argument("--text-only", action="store_true", dest="text_only")
    p = sub.add_parser("feedsync",
                       help="audit the committed feed against a fresh regeneration")
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
        elif args.command == "registry": result = registry_audit()
        elif args.command == "drift": result = deploy_drift(args.remote, text_only=args.text_only)
        elif args.command == "feedsync": result = feed_sync()
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
        if args.command in {"reconcile", "preflight", "review", "verify", "publish", "push", "status", "watchdog", "attempt", "coverage", "registry", "drift", "feedsync"}:
            return 0 if result.get("ok", result.get("healthy", True)) else 1
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
