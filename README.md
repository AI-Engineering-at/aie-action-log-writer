# aie-action-log-writer

> echo_log Phase-1 Action-Log Pipeline (v3): append-only, hash-chained JSONL writer for Brain / Worker-Bot / echo_log actions.

**Stand:** 2026-05-27
**Status:** Bauteil-Mac (Reife-5), LIVE-Use
**Visibility:** private (internal compliance infrastructure)
**Bauteil-ID:** #77 (M40 Reife-5)

## Zweck

ActionLogger schreibt append-only JSONL-Logs unter `~/kb/ops/agent-actions/YYYY-MM-DD.jsonl` mit:

- **SHA-256 Hash-Chain** über `canonical_json(record)` (`prev_hash` -> `this_hash`).
- **Tier-Validation** (`tier0` / `tier1` / `tier2` / `tier3`) gemaess echo_log §4 (T0 read-only, T1 autonom+log, T2 autonom+approval, T3 NIE autonom -> Hard-Block).
- **`fcntl.flock(LOCK_EX)`** rund um read-prev-hash + append (W76-4 Race-Fix, 8-Parallel-Writer green).
- **`verify_chain()`** rekonstruiert die Hash-Chain end-to-end fuer Audit-Beleg.

## Compliance-Anker

- **EU AI Act Art. 12** (Automatic Logging) -> Annex IV Erfuellung
- **EU AI Act Art. 19** (Record-Keeping)
- **DSGVO Art. 22** (Verbot vollautomatischer Personen-Decisions -> Tier-3 Hard-Block)
- **DSGVO Art. 32** (TOM-Nachweis-Spur)
- **IETF Agent-Audit-Trail** (`prev_hash`, `action_hash`, `params_redacted`, `before_hash`, `after_hash`, `decision`, `human_review`, `tier`)

## Struktur

```
aie-action-log-writer/
├── src/action_log_writer.py    # ActionLogger-Klasse + CLI
├── tests/test_action_log_writer.py
├── SCHEMA.md                    # JSONL-Schema (4910 B)
├── README.md
├── LICENSE
└── .github/workflows/ci.yml
```

## Quick Start

```python
from action_log_writer import ActionLogger

logger = ActionLogger(agent_id="brain-mac", role="orchestrator")
logger.log(
    action="docker.image.prune",
    target="swarm1.nb.aie",
    params={"force": True},
    params_hashed_keys=[],
    classification="tier1",
    before_hash="sha256:...",
    after_hash="sha256:...",
    success=True,
    human_review=False,
)
```

## CLI

```bash
# Self-test (in temp-dir, no side effects)
python src/action_log_writer.py --self-test

# Verify hash-chain integrity of a day-log
python src/action_log_writer.py --verify ~/kb/ops/agent-actions/2026-05-27.jsonl
```

## Compliance & Doctrine

- **Anti-Pattern A33 (KEIN-MOCK-ABSOLUT):** alle Logs basieren auf echten Actions, keine Pseudo-Eintraege.
- **ISC2-CC-Framing:** Integrity (Hash-Chain), Non-Repudiation (append-only), Auditability (`verify_chain`).
- **Append-only Code:** Refactor via DEC-Eintrag (kb/DECISIONS.md).
- **Schema-Strenge:** classification ∈ VALID_TIERS, sonst ValueError (JOE §0.J).

## Cross-Reference

- Bauteil-Inventar: `kb/ops/BAUTEILE-INVENTAR.md` (Eintrag #77, §2-Update W68-Retroactive)
- Build-Belege: `kb/raw/2026-05-27-w68-echolog-phase-1-konsolidierung.md`, `kb/raw/2026-05-27-w70-block-a0-disk-repair-swarm-prune.md`, `kb/raw/2026-05-27-w76-4-action-log-writer-fcntl.md`
- Schema: `SCHEMA.md` (Quelle: `~/kb/ops/agent-actions/SCHEMA.md`)
- Used-by (geplant): security-watcher, compliance-watcher, resilience-watcher, auto-remediation-controller (`~/kb/ops/skills-agents/defs/`)

## License

Proprietary — internal compliance infrastructure. See [LICENSE](LICENSE).
