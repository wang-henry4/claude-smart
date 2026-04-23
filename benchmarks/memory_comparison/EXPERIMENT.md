# claude-smart vs claude-mem — memory capture benchmark

A head-to-head comparison of two Claude Code memory plugins on how well they capture user knowledge from a conversation. `claude-mem` is a memory system (records what happened); `claude-smart` is a learning system (distils what happened into rules). The experiment measures whether that distinction shows up in retrieval quality.

## Headline result

12 scripted scenarios, identical input text to both systems, LLM judge scoring 0–3 on recall and specificity.

| Category | claude-smart | claude-mem |
| --- | ---: | ---: |
| Personalization (3) | 1.00 | 1.00 |
| Correction (3) | **3.00** | 0.00 |
| General (3) | 1.00 | 1.00 |
| Learning (3) | **3.00** | 1.00 |
| **Overall (12)** | **2.00** | **0.75** |

claude-smart wins decisively on **corrections** and **learning** — the two categories where the probe asks "what rule should I follow going forward?". On **personalization** and **general** facts, both systems capture the ground truth at similar rates under tight latency.

## Why this benchmark exists

Most memory-system demos show one system in isolation. That doesn't answer the question a Claude Code user actually has: *given the same conversation, does this plugin surface information I can act on?* This harness feeds identical synthetic conversations into each plugin's real ingestion path, then asks an LLM judge to score what each system returns against a written ground truth.

## Experiment setup

### Architecture

```
           Scenario turns (identical for both systems)
                         │
         ┌───────────────┴───────────────┐
         ▼                               ▼
 ┌──────────────────┐          ┌────────────────────┐
 │  claude-smart    │          │  claude-mem        │
 │  (reflexio)      │          │  (worker-service)  │
 └──────────────────┘          └────────────────────┘
         │                               │
         ▼ non-blocking publish          ▼ async queue
 ┌──────────────────┐          ┌────────────────────┐
 │ reflexio extract │          │ per-session Claude │
 │ → profile +      │          │ subprocess pool    │
 │   playbook       │          │ → observations     │
 └──────────────────┘          └────────────────────┘
         │                               │
         └───────── probe query ─────────┘
                         │
                         ▼
           ┌────────────────────────────┐
           │ LLM judge (Haiku 4.5,      │
           │ JSON-schema constrained)   │
           │ recall + specificity       │
           └────────────────────────────┘
```

### Scenarios

12 scenarios across 4 categories:

- **personalization** (`pref-*`, 3): durable user preferences
  > *e.g.* "I always use pytest, never unittest — make that a project-wide rule"
- **correction** (`corr-*`, 3): user pushes back on an agent suggestion
  > *e.g.* "Stop using async — this codebase is fully synchronous"
- **general** (`gen-*`, 3): role, team, or project context
  > *e.g.* "I maintain the billing service; we ship every Friday"
- **learning** (`learn-*`, 3): user reports a past event; probe asks for a **future-facing rule** (the differentiator)
  > *e.g.* turns describe a snake_case → camelCase refactor across the repo; probe asks *"What naming convention should I use for new identifiers in this project's TypeScript code?"*

Each scenario has:
- `turns`: a short multi-turn conversation injected verbatim
- `ground_truth`: the fact or rule we expect the system to capture
- `probe_query`: the question fired at each system's retrieval API post-injection

### Ingestion paths (native, no shimming)

Nested `claude -p` does **not** fire plugin hooks, so a CLI-replay approach gives both systems zero visibility. The harness pivots to each plugin's real programmatic ingestion:

- **claude-smart** → `reflexio.ReflexioClient.publish_interaction(wait_for_response=False, force_extraction=True)`. This is the *same* call path the `Stop` hook uses in production — non-blocking, force-extract the current interactions.
- **claude-mem** → its `worker-service.cjs hook claude-code session-init` followed by `hook claude-code observation` subcommands. These are the CLI entry points its real hooks call. A synthetic JSONL transcript is written first so the worker's extractor sees last-user / last-assistant context.

Both sides trigger their *real* LLM extraction pipeline on identical inputs.

### Drain semantics

- **claude-smart** publishes are non-blocking (matches production). The harness polls `reflexio.search_user_playbooks` + `search_profiles` until at least one record materializes (90s budget).
- **claude-mem** has no documented drain-on-demand hook. The harness polls `pending_messages.status IN ('pending','processing')` for the scenario's `content_session_id` until the queue is empty (180s budget — each turn enqueues one LLM call, processed serially by a pool capped at 10 concurrent sessions).

### Retrieval

- **claude-smart**: `Adapter.search_both(project_id, session_id, query, top_k=5)` — hybrid BM25 + vector over playbooks and profiles.
- **claude-mem**: SQLite FTS5 `MATCH` over `observations_fts`, ranked by BM25, scoped to the scenario's project basename. Falls back to recency scan if FTS returns nothing.

### Scoring

An LLM judge (Claude Haiku 4.5, JSON-schema-constrained) receives `ground_truth`, `probe_query`, and the raw retrieved rows, and returns:

```json
{
  "recall": 0-3,        // 3 = ground truth clearly present, 0 = absent/contradicted
  "specificity": 0-3,   // 3 = precise enough to act on, 0 = no actionable detail
  "rationale": "<15 words>"
}
```

Judge runs in an isolated `/tmp/membench-judge/` CWD so its own plugin-captured memory can't contaminate scenario retrievals.

## Running it

```bash
# Full 12-scenario run — writes results/run-<ts>.json and report-<ts>.md
uv run python -m benchmarks.memory_comparison.run

# Single scenario
uv run python -m benchmarks.memory_comparison.run --only learn-naming

# Score whatever's already in the stores (no replay) — useful after a cool-off
uv run python -m benchmarks.memory_comparison.run --dry-run
```

Expected wall time: ~8–15 minutes for the full run depending on extraction queue depth.

## Findings

### 1. Corrections: the clearest split (claude-smart 3.00 vs claude-mem 0.00)

Every correction scenario — async ban, no-docstrings, PyYAML-to-ruamel — produced a clean playbook on claude-smart that was judged 3/3. Reflexio's playbook extractor is explicitly designed to fire on correction signals (per `reflexio/server/services/playbook/playbook_extractor.py`), generating entries with a `trigger` and `rationale` the judge could cite directly. claude-mem retrieved nothing for any correction scenario within the 180s drain budget — its observations landed in the DB eventually but not inside the measurement window.

### 2. Learning (future-facing rules): the design gap (claude-smart 3.00 vs claude-mem 1.00)

The three `learn-*` scenarios were built to isolate the *memory vs learning* distinction: the user reports a past event (v1→v2 migration, snake→camel rename, pagination off-by-one) and the probe asks for a **rule** to apply to future code. Results:

| Scenario | claude-smart | claude-mem |
| --- | ---: | ---: |
| `learn-api-v2` — which version for new code? | 3 | 3 |
| `learn-naming` — which convention for new identifiers? | 3 | 0 |
| `learn-pagination` — what to double-check in new pagination code? | 3 | 0 |

claude-mem scored 3 on `learn-api-v2` because the user phrased the turn itself as a rule ("v1 is going away — new code should target v2"), so even a descriptive capture read as prescriptive. On the other two, where the rule was *implied by* the event rather than stated, claude-mem's output framed the past ("refactored identifiers from snake_case to camelCase") rather than the rule for next time ("use camelCase for new identifiers"). claude-smart's playbook extractor lifted the rule in both cases.

### 3. Personalization and general facts: a near-tie

Both systems captured things like "user prefers pytest" and "user maintains billing service" when extraction finished in time. Scores were 1.00 each overall because under bursty load (12 scenarios back-to-back), both systems hit extraction timeouts on roughly half the scenarios — reflexio's extractor occasionally returns an empty result for short conversations with no corrective signal, and claude-mem's worker pool backlogged. Neither is a fundamental capture failure — given a longer cool-off period both systems surface the right fact.

### 4. Architectural differences the benchmark surfaced

- **Latency & call ergonomics**: claude-smart's publish has a documented "wait for extraction" path. claude-mem has no drain-on-demand handle, so anything that asks "does the system know X yet?" has to poll the queue or guess at a cool-off.
- **Output shape**: reflexio playbooks embed explicit `trigger` + `rationale` fields, which the judge treated as high-specificity actionable detail. claude-mem observations are narrative + facts + concepts — great for retrieval, less directly actionable as a rule.
- **Extractor scope**: reflexio intentionally only produces project-level playbooks for *corrections* and *success-path recipes* (per `playbook_extractor.py:414-444` and the v4.0.0 prompt). General facts become profiles only. claude-mem produces an observation for every turn regardless of signal type.

## Caveats

- **Tight-window measurement.** Scores reflect what's queryable after per-scenario drain budgets (90s smart, 180s mem). A dry-run rescore after a ~5-minute cool-off lifts both systems' scores, especially claude-mem's — it's async-by-design. The relative gap on corrections and learning persists either way, which is the point.
- **Synthetic assistant replies.** The harness uses a one-line template reply per turn, not real Claude output. This isolates "what did the user state?" from "how well did the agent respond?". Both systems get the same input so it's fair, but real sessions have richer assistant text that could provide more extraction signal.
- **Single judge model.** Haiku 4.5 is fast and cheap; Opus would likely score both systems slightly higher on borderline scenarios. The *gap* between systems, not absolute scores, is the signal.
- **Project basename collision.** Scenarios reuse `/tmp/membench/<id>` paths. Re-running without cleanup injects new records on top of old ones; use the Cleanup section in `results/report-*.md` to purge between runs.

## Files

```
benchmarks/memory_comparison/
├── EXPERIMENT.md              (this file)
├── scenarios.py               — 12 ground-truth scenarios
├── replay.py                  — native-path injection into both systems
├── adapters/
│   ├── claude_smart.py        — reflexio search + wait_for_extraction poll
│   └── claude_mem.py          — SQLite FTS5 retrieval + wait_for_worker_drain
├── judge.py                   — Claude Haiku JSON-schema judge
├── run.py                     — orchestrator, aggregates, writes report
└── results/                   — run-<ts>.json + report-<ts>.md per invocation
```

## Reproducibility

Both plugins must be installed and running. The harness expects:

- reflexio backend reachable at `http://localhost:8071/` (claude-smart's `SessionStart` hook starts it automatically)
- claude-mem worker healthy at `http://localhost:37xxx/health` (its `SessionStart` hook starts it automatically)
- `claude` CLI on PATH and logged in (for the judge)

No API keys required — the judge uses the user's Claude Code OAuth session.
