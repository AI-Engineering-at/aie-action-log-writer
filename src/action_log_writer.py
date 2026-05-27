#!/usr/bin/env python3
"""
action_log_writer.py — echo_log Phase 1 Action-Log Pipeline (v3)

Append-only Hash-chained JSONL-Writer für Brain/Worker/echo_log Actions.

Spec: ~/kb/ops/agent-actions/SCHEMA.md
Compliance: EU AI Act Art. 12+19 / DSGVO Art. 22 / IETF Agent-Audit-Trail

Usage:
    from action_log_writer import ActionLogger

    logger = ActionLogger(agent_id="brain-mac", role="orchestrator")
    logger.log(
        action="netbird.setup_key.revoke",
        target="docker-swarm2.nb.aie",
        params={"key_id": "abc123"},
        params_hashed_keys=[],
        classification="tier1",
        before_hash="sha256:...",
        after_hash="sha256:...",
        success=True,
        human_review=False,
    )

W76-4 Patch (2026-05-27):
- fcntl.flock(LOCK_EX) rund um read-prev-hash + append (M120 Race-Fix)
- Schema-Strenge: classification ∈ {tier0,tier1,tier2,tier3} (JOE §0.J)
- Self-Test isoliert in temp-dir

W77-b Patch (2026-05-27) — Bug-Fix v3 (siehe raw/2026-05-27-w77-b-...):
- Bug 1 (Mode-Inkonsistenz): log() öffnet jetzt **binary-mode** `"ab+"`
  durchgängig (matches last_chain_hash_of_day). _decode bleibt als
  defensives Helper, ist aber im Hot-Path nicht mehr load-bearing.
  Writes erfolgen als bytes (UTF-8 encoded) — kein Text/Bytes-Mismatch.
- Bug 2 (`global LOG_DIR` Smell): Modul-Mutation entfernt. ActionLogger
  akzeptiert jetzt optionalen `log_dir`-Parameter im Konstruktor;
  Self-Test injiziert tempdir per DI statt global zu mutieren. Kein
  Shared-State-Risiko mehr bei parallelen ActionLogger-Instanzen.
- Self-Test deckt beide Branches: (a) binary-mode-Roundtrip via
  ActionLogger.log + verify_chain, (b) text-mode-tolerance via direktes
  _decode-Probing auf str-Input.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import pathlib
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any

# Hash-Chain Constants
GENESIS_PREV_HASH = "sha256:" + "0" * 64
DEFAULT_LOG_DIR = pathlib.Path.home() / "kb" / "ops" / "agent-actions"

# Backwards-Compat-Alias (Pre-W77 Code referenziert LOG_DIR direkt; nicht mehr
# als Mutation-Target verwendet, nur als Default-Resolver).
LOG_DIR = DEFAULT_LOG_DIR

# Schema-Strenge (W76-4 / JOE §0.J)
VALID_TIERS = {"tier0", "tier1", "tier2", "tier3"}


def canonical_json(d: dict[str, Any]) -> str:
    """Deterministic JSON serialization for hash-stable chaining."""
    return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(s: str) -> str:
    return "sha256:" + hashlib.sha256(s.encode("utf-8")).hexdigest()


def _decode(buf) -> str:
    """Defensiv: toleriert bytes (rb/ab+-mode) und str (text-mode) reads.

    Im W77-v3-Hot-Path nicht mehr load-bearing (log() öffnet konsequent
    binary), bleibt als Vakzin gegen künftige Mode-Drift im Code.
    """
    if isinstance(buf, bytes):
        return buf.decode("utf-8", errors="ignore")
    return buf


def _read_last_chain_hash(f) -> str:
    """Read last entry's this_hash from open binary file handle.

    Caller MUST hold flock(LOCK_EX). Erwartet binary-mode-Handle
    (rb/ab+); _decode() schützt defensiv gegen text-mode-Drift.
    """
    f.seek(0, os.SEEK_END)
    size = f.tell()
    if size == 0:
        return GENESIS_PREV_HASH
    seek_to = max(0, size - 4096)
    f.seek(seek_to, os.SEEK_SET)
    tail = _decode(f.read())
    lines = [l for l in tail.splitlines() if l.strip()]
    if not lines:
        return GENESIS_PREV_HASH
    try:
        last = json.loads(lines[-1])
        return last.get("this_hash", GENESIS_PREV_HASH)
    except json.JSONDecodeError:
        return GENESIS_PREV_HASH


def last_chain_hash_of_day(day_path: pathlib.Path) -> str:
    """Return last entry's this_hash, or GENESIS_PREV_HASH if empty/new file.

    Lock-free read for verify/inspection use. NOT safe for race-free append —
    use ActionLogger.log() which locks read+append atomically.
    """
    if not day_path.exists() or day_path.stat().st_size == 0:
        return GENESIS_PREV_HASH
    with day_path.open("rb") as f:
        return _read_last_chain_hash(f)


class ActionLogger:
    """Append-only hash-chained JSONL writer.

    W76-4: read-prev-hash + append run under fcntl.flock(LOCK_EX) for
    race-free parallel Sub-Agent dispatch (M120 fix).

    W77-b: log_dir per DI (Konstruktor-Param) statt global-mutation.
    Default = ~/kb/ops/agent-actions. Tests injizieren tempdir hier.
    """

    VALID_TIERS = VALID_TIERS  # noqa: F811 — bewusste Re-Export für Backwards-Compat
    VALID_ROLES = {"orchestrator", "skill", "tool", "worker"}

    def __init__(
        self,
        agent_id: str,
        role: str,
        session_id: str | None = None,
        log_dir: pathlib.Path | None = None,
    ):
        if role not in self.VALID_ROLES:
            raise ValueError(f"role must be one of {self.VALID_ROLES}")
        self.agent_id = agent_id
        self.role = role
        self.session_id = session_id
        self.log_dir = pathlib.Path(log_dir) if log_dir is not None else DEFAULT_LOG_DIR
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _day_path(self) -> pathlib.Path:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self.log_dir / f"{today}.jsonl"

    def log(
        self,
        action: str,
        target: str,
        classification: str,
        success: bool,
        params: dict | None = None,
        params_hashed_keys: list[str] | None = None,
        before_hash: str | None = None,
        after_hash: str | None = None,
        error: str | None = None,
        human_review: bool = False,
        human_approver: str | None = None,
    ) -> dict[str, Any]:
        # Schema-Strenge §0.J (W76-4)
        if classification not in VALID_TIERS:
            raise ValueError(
                f"classification must be one of {sorted(VALID_TIERS)}, got {classification!r}"
            )
        if classification == "tier3" and not human_review:
            raise ValueError(
                "Tier-3 actions MUST have human_review=True (DSGVO Art. 22). "
                "Joe = APEX. Refusing to log autonomous tier-3."
            )
        if not success and error is None:
            raise ValueError("If success=False, error must be non-null")

        day_path = self._day_path()

        # Mask secrets in params (pre-lock, deterministic)
        clean_params = dict(params or {})
        for k in params_hashed_keys or []:
            if k in clean_params:
                v = str(clean_params[k])
                clean_params[k] = sha256_hex(v)[:14]  # sha256:<6 chars> preview

        # M120 Race-Fix: read-prev-hash + append unter EINEM fcntl.LOCK_EX.
        # W77-b: binary-mode "ab+" durchgängig (kein decode-Mismatch mit
        # text-mode mehr). Writes als bytes (UTF-8).
        with day_path.open("ab+") as f:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                prev_hash = _read_last_chain_hash(f)

                entry = {
                    "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "agent_id": self.agent_id,
                    "role": self.role,
                    "action": action,
                    "target": target,
                    "params": clean_params,
                    "params_hashed_keys": params_hashed_keys or [],
                    "before_hash": before_hash,
                    "after_hash": after_hash,
                    "success": success,
                    "error": error,
                    "classification": classification,
                    "human_review": human_review,
                    "human_approver": human_approver,
                    "session_id": self.session_id,
                    "prev_hash": prev_hash,
                }
                entry["this_hash"] = sha256_hex(prev_hash + canonical_json(entry))

                f.seek(0, os.SEEK_END)
                line_bytes = (json.dumps(entry, ensure_ascii=False) + "\n").encode("utf-8")
                f.write(line_bytes)
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return entry


def verify_chain(day_path: pathlib.Path) -> tuple[bool, str]:
    """Verify hash-chain integrity of a day-file. Returns (ok, reason)."""
    if not day_path.exists():
        return False, f"File not found: {day_path}"
    prev = GENESIS_PREV_HASH
    line_n = 0
    with day_path.open("r", encoding="utf-8") as f:
        for line in f:
            line_n += 1
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as e:
                return False, f"Line {line_n}: JSON-decode error: {e}"
            if entry.get("prev_hash") != prev:
                return (
                    False,
                    f"Line {line_n}: prev_hash mismatch (expected {prev[:20]}..., got {entry.get('prev_hash', '')[:20]}...)",
                )
            recomputed = sha256_hex(prev + canonical_json({k: v for k, v in entry.items() if k != "this_hash"}))
            if entry.get("this_hash") != recomputed:
                return False, f"Line {line_n}: this_hash mismatch (tampered?)"
            prev = entry["this_hash"]
    return True, f"OK: {line_n} entries verified, chain intact"


def verify_chain_segment(day_path: pathlib.Path, start_line: int, end_line: int | None = None) -> tuple[bool, str]:
    """Verify chain integrity for a subset of lines [start_line .. end_line].

    Use this to assert an own segment is intact even when a pre-existing
    break exists elsewhere in the file (W77 backwards-compat audit).
    1-indexed. end_line None = until EOF. Starts chain at recorded prev_hash
    of start_line (does not re-validate the cross-segment hand-off).
    """
    if not day_path.exists():
        return False, f"File not found: {day_path}"
    with day_path.open("r", encoding="utf-8") as f:
        lines = [l for l in f.read().splitlines() if l.strip()]
    end = end_line if end_line is not None else len(lines)
    if start_line < 1 or start_line > len(lines):
        return False, f"start_line {start_line} out of range (file has {len(lines)} lines)"
    try:
        first = json.loads(lines[start_line - 1])
    except json.JSONDecodeError as e:
        return False, f"Segment start L{start_line}: JSON-decode error: {e}"
    prev = first.get("prev_hash", GENESIS_PREV_HASH)
    for i in range(start_line - 1, min(end, len(lines))):
        try:
            entry = json.loads(lines[i])
        except json.JSONDecodeError as e:
            return False, f"Line {i+1}: JSON-decode error: {e}"
        if entry.get("prev_hash") != prev:
            return False, f"Line {i+1}: prev_hash mismatch within segment"
        recomputed = sha256_hex(prev + canonical_json({k: v for k, v in entry.items() if k != "this_hash"}))
        if entry.get("this_hash") != recomputed:
            return False, f"Line {i+1}: this_hash mismatch (tampered?)"
        prev = entry["this_hash"]
    return True, f"OK: segment L{start_line}-L{min(end, len(lines))} intact"


def _run_self_test() -> int:
    """Isolated self-test in temp-dir via DI (W77-b: kein global mehr)."""
    with tempfile.TemporaryDirectory() as td:
        td_path = pathlib.Path(td)
        logger = ActionLogger(
            agent_id="brain-mac-selftest",
            role="orchestrator",
            session_id="W77-selftest",
            log_dir=td_path,
        )
        # Branch A: Binary-mode-Roundtrip (Hot-Path)
        logger.log(
            action="test.dry_run",
            target="local",
            classification="tier0",
            success=True,
            params={"foo": "bar"},
        )
        e2 = logger.log(
            action="test.dry_run.2",
            target="local",
            classification="tier0",
            success=True,
        )
        print(f"Wrote 2 entries. Last this_hash: {e2['this_hash'][:24]}...")
        ok, reason = verify_chain(logger._day_path())
        print(f"Verify (binary-mode write path): {'OK' if ok else 'FAIL'} {reason}")
        if not ok:
            return 1

        # Branch B: _decode defensive-Branch (text-input → str passthrough,
        # bytes-input → decode). Vakzin gegen Mode-Drift.
        assert _decode(b"hello") == "hello", "_decode bytes-branch failed"
        assert _decode("hello") == "hello", "_decode str-branch failed"
        assert _decode(b"\xc3\xa4") == "ä", "_decode UTF-8 bytes-branch failed"
        print("OK _decode branches (bytes + str + UTF-8) verified")

        # Branch C: last_chain_hash_of_day (rb-mode helper) liest gleichen
        # Chain-Head wie inkrementeller log()-Read.
        head = last_chain_hash_of_day(logger._day_path())
        if head != e2["this_hash"]:
            print(f"FAIL last_chain_hash_of_day mismatch: {head} vs {e2['this_hash']}")
            return 1
        print("OK last_chain_hash_of_day == last log() this_hash")

        # Schema-Strenge-Test (W76-4 / §0.J)
        try:
            logger.log(
                action="test.bad_tier",
                target="local",
                classification="tier99",
                success=True,
            )
            print("FAIL Schema-Strenge: bad tier NICHT abgelehnt")
            return 1
        except ValueError as e:
            print(f"OK Schema-Strenge: bad tier abgelehnt ({e})")
        # Tier-3 ohne human_review
        try:
            logger.log(
                action="test.bad_tier3",
                target="local",
                classification="tier3",
                success=True,
            )
            print("FAIL Tier-3 ohne human_review NICHT abgelehnt")
            return 1
        except ValueError:
            print("OK Tier-3 ohne human_review abgelehnt")
        return 0


def main():
    """CLI: action_log_writer.py {verify [path] | verify-segment <path> <start> [<end>] | self-test}"""
    if len(sys.argv) >= 2 and sys.argv[1] == "verify":
        target = pathlib.Path(sys.argv[2]) if len(sys.argv) >= 3 else (
            DEFAULT_LOG_DIR / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.jsonl"
        )
        ok, reason = verify_chain(target)
        print(f"{'OK' if ok else 'FAIL'} {target}: {reason}")
        sys.exit(0 if ok else 1)
    elif len(sys.argv) >= 2 and sys.argv[1] == "verify-segment":
        if len(sys.argv) < 4:
            print("Usage: action_log_writer.py verify-segment <path> <start_line> [<end_line>]")
            sys.exit(2)
        target = pathlib.Path(sys.argv[2])
        start = int(sys.argv[3])
        end = int(sys.argv[4]) if len(sys.argv) >= 5 else None
        ok, reason = verify_chain_segment(target, start, end)
        print(f"{'OK' if ok else 'FAIL'} {target} L{start}-{end or 'EOF'}: {reason}")
        sys.exit(0 if ok else 1)
    elif len(sys.argv) >= 2 and sys.argv[1] == "self-test":
        sys.exit(_run_self_test())
    else:
        print(__doc__)
        print("\nCLI: action_log_writer.py {verify [path] | verify-segment <path> <start> [<end>] | self-test}")
        sys.exit(0)


if __name__ == "__main__":
    main()
