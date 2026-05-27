---
title: Agent-Actions Schema (echo_log Phase 1 Action-Log-Pipeline)
stand: 2026-05-27
gelockt-am: 2026-05-27
mutability: append-only
classification: confidential
schicht: L2 OPS / Action-Log-Pipeline
trigger: echo-log-evolution.md §5 + Joe-Direktive 2026-05-27 echo_log-Phase-1-GO
cross-ref:
  - kb/projects/echo-log-evolution.md §5
  - kb/ops/AIE-COMPLIANCE-V3-CONSOLIDATED.md §5 Schicht-5 (Hash-Chain-Ledger)
  - IETF-Draft Agent-Audit-Trail (März 2026)
isc2-frame: DEC-050 Block 11+12+14+18+19
---

# §1 Zweck

Append-only Hash-chained JSONL-Log aller Brain-/Worker-/echo_log-Aktionen, gemäß:
- EU AI Act Art. 12 (Record-Keeping) + Art. 19 (Auto-Generated Logs, 6 Monate Retention minimum)
- DSGVO Art. 22 (Tier-3 = nie autonom)
- IETF-Draft Agent-Audit-Trail (Hash-Chain Tamper-Detection)
- echo-log-evolution.md §5 Pflicht-Felder

# §2 Speicherort

```
~/kb/ops/agent-actions/YYYY-MM-DD.jsonl
```

Eine Datei pro Tag, eine Zeile pro Aktion, **append-only**, NIE direct-edit.
Promtail-Mirror nach Loki (Job-Name `agent-actions`) für zentrale Korrelation.

# §3 Pflicht-Felder (verbindlich)

```jsonl
{
  "ts": "2026-05-27T01:30:00Z",
  "agent_id": "echo_log|security-watcher|compliance-watcher|auto-remediation|brain-mac|hermes|jim01|...",
  "role": "orchestrator|skill|tool|worker",
  "action": "<machine-readable>",
  "target": "<FQDN|IP|Resource-URN>",
  "params": {...},
  "params_hashed_keys": ["secret_key1", "secret_key2"],
  "before_hash": "sha256:...",
  "after_hash": "sha256:...",
  "success": true,
  "error": null,
  "classification": "tier0|tier1|tier2|tier3",
  "human_review": false,
  "human_approver": null,
  "session_id": "...",
  "prev_hash": "sha256:..."
}
```

## §3.1 Feld-Definitionen

| Feld | Typ | Pflicht | Bedeutung |
|---|---|---|---|
| `ts` | ISO-8601 UTC | ✅ | Aktionszeitpunkt |
| `agent_id` | string | ✅ | Verursacher |
| `role` | enum | ✅ | orchestrator / skill / tool / worker |
| `action` | string | ✅ | machine-readable, z.B. `netbird.setup_key.revoke` |
| `target` | string | ✅ | FQDN/IP/URN/Path |
| `params` | object | ✅ | Aktion-Parameter. Secrets via params_hashed_keys gehasht |
| `params_hashed_keys` | list | optional | Welche params-Keys nur als sha256:<8> drinstehen |
| `before_hash` | sha256 | optional | Pre-State-Hash (Config/Datei/API-Response) |
| `after_hash` | sha256 | optional | Post-State-Hash |
| `success` | bool | ✅ | Aktion erfolgreich |
| `error` | string\|null | ✅ wenn !success | Fehler-Meldung |
| `classification` | enum | ✅ | tier0..tier3 |
| `human_review` | bool | ✅ | true wenn vor Ausführung Joe-Approval |
| `human_approver` | string\|null | optional | wenn human_review=true: wer approved |
| `session_id` | string | optional | Brain-Session-ID für Cross-Action-Tracking |
| `prev_hash` | sha256 | ✅ | Hash der vorherigen JSONL-Zeile (Tamper-Detection-Chain) |

## §3.2 Tier-Klassifikation (aus echo-log-evolution.md §4)

| Tier | Erlaubt | Beispiele |
|---|---|---|
| **0** | sofort, immer | Loki-Query · Wazuh-Alert lesen · Grafana-Snapshot · MM-Post in @alerts |
| **1** | atomar+reversibel | NetBird-Setup-Key revoken · Cron-Token rotieren · ERPNext-Task anlegen · Promtail-Job deaktivieren |
| **2** | Config-Rollback nach failed Deploy | docker stack → letzter healthy SHA · sshd_config-Restore aus Backup · OPNsense-Config-Restore |
| **3** | **NIE autonom — Joe = APEX** | `rm`/`destroy` · NetBird-Peer permanent löschen · DB-DROP · Cross-Site-Policy · Self-Config |

# §4 Hash-Chain-Algorithmus

```python
this_hash = sha256(prev_hash + canonical_json(this_entry_without_prev_hash))
```

Genesis-Block: `prev_hash = "sha256:0000000000000000000000000000000000000000000000000000000000000000"`

Tamper-Detection: jede Manipulation einer alten Zeile bricht alle nachfolgenden Hashes.

# §5 Bewusst NICHT geloggt

- Chat-Inhalte mit Kunden-PII (nur Hash + Verweis)
- Vault-Secret-Werte (nur sha256:<8> Prefix in params_hashed_keys)
- Geheimnis-Strings (Tokens, Passwords, API-Keys) — nur Identifier
- Voice-Stream-Audio (nur Transkript-Hash)

# §6 Retention

- **Action-Logs: 5 Jahre** (EU AI Act Art. 12 Lifecycle dominiert DSGVO Art. 5 Abs. 1 lit. e)
- **Promtail-Loki-Mirror:** 90 Tage Hot, dann Cold-Archive auf .82-NAS
- **Tombstone-Pattern bei DSGVO-Art-17-Erasure:** Inhalt redacted, Hash-Chain bleibt intakt

# §7 Cross-Ref

- echo-log-evolution.md §5 (Original-Spec)
- aie-audit-chain MCP (Hash-Chain-Implementation)
- AIE-COMPLIANCE-V3-CONSOLIDATED.md §5
- IETF-Draft Agent-Audit-Trail
- existing W26-LiveTest-Beispiel-File `w26e-livetest-001-2026-05-25.jsonl` (in diesem Verzeichnis)

# §8 Status

- ✅ Schema dokumentiert (this file)
- ⏳ action_log_writer.py — siehe `~/kb/ops/scripts/action_log_writer.py` (Phase 1 Task 3)
- ⏳ Promtail-Job-Config (Phase 2 wenn .80-Loki Block A-E ready)
- ⏳ MCP-Integration via aie-audit-chain (Phase 2)
