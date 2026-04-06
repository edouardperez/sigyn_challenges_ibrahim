# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Config-driven financial analysis agent for French FEC (Fichier des Écritures Comptables) files. Uses LangGraph + Google Gemini to analyze accounting entries, compute financial ratios, and compare against Banque de France sector benchmarks.

**Target dataset:** RD CANNES hairdressing salon (NAF: 96.02A), ~9,375 FEC entries.

## Commands

```bash
# Setup
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt

# Run server (port 8000, Swagger at /docs)
python main.py
# or
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Smoke test (no API key required — tests full pipeline without LLM)
python test_smoke.py
```

## Architecture: 6-Layer Config-Driven System

Business logic lives in **JSON config, not Python code**. Python references `rubrique_key` strings; SQL lives in `mdl_manifest.json`.

```
L5: agent_spec.json        — Tool definitions, planner policy, security guardrails
L4: metrics/ + waterfalls/ — Ratio formulas, alert thresholds, BdF benchmarks
L3: ontology/              — PCG taxonomy, concepts, sector profiles
L2: mdl_manifest.json      — 50+ rubriques (dual-path: semantic{} + execution{})
L1: duckdb_engine.py       — Zero-copy SQL on pandas DataFrame ('fec' table)
L0: fec_loader.py          — xlsx/csv → normalized DataFrame
```

## LangGraph Flow

```
START → context_builder → planner (Gemini) → executor (loop) → [_router]
         ↓ error                                                      ↓
       replanner ←────────────────────────────────────────────────────┘
         ↓ done
       synthesizer → END
```

- **Max 8 steps per plan, 2 replan attempts** (configured in `agent_spec.json`)
- **LLM never writes SQL** — it only references `rubrique_key` strings
- All queries are SELECT-only (`BLOCK_PATTERNS` in `dispatcher.py` + `agent_spec.json`)

## Critical Pattern: Config-First Development

**Never hardcode SQL or account numbers in Python.**

```python
# ❌ Wrong
value = df[df["numero_compte"].str[:2].isin(["10","11","12"])]["credit"].sum()

# ✅ Correct
sql = semantic.build_rubrique_sql("capitaux_propres", exercice=2024)
value = engine.fetch_one(sql)["valeur"]
```

## Key Files

| File | Role |
|------|------|
| `pcg_agent/semantic_layer/mdl_reader.py` | Core semantic logic — dual-path reader |
| `pcg_agent/graph/graph.py` | LangGraph StateGraph wiring |
| `pcg_agent/config/semantic/mdl_manifest.json` | 50+ rubriques with SQL expressions |
| `pcg_agent/tools/dispatcher.py` | Routes 8 tools, enforces read-only security |
| `pcg_agent/api/routes.py` | `/upload-fec` and `/chat` endpoints |
| `pcg_agent/api/_runtime.py` | Global sessions dict (engine + df + chat_history) |
| `test_smoke.py` | End-to-end pipeline test without LLM |
| `AGENTS.md` | Coding guidelines and patterns |
| `pcg_data_agent_architecture_finale.md` | Detailed architecture spec (1,333 lines) |

## Semantic Layer: Dual-Path Design

Each rubrique in `mdl_manifest.json` has two blocks:
- **`semantic{}`** — For LLM context: `display_name`, `synonyms`, `description`, `tags`, `domain_category`
- **`execution{}`** — For SQL building: `macro`, `include_prefixes`, `exclude_prefixes`

Available macros: `solde_actif`, `solde_passif`, `solde_charge`, `solde_produit`, `sql_expression`

## Available Tools (via dispatcher)

1. `resolve_concept(query)` — Fuzzy match user term → rubrique_keys
2. `query_rubrique(rubrique_key, exercice, mois?)` → Raw aggregated value
3. `query_metric(metric_key, exercice)` → Ratio + alert + sector position
4. `get_trend(rubrique_key, from_year, to_year, granularity)` → Time series
5. `get_breakdown(rubrique_key, exercice, top_n)` → Sub-account breakdown
6. `get_waterfall(waterfall_key, exercice, include_cca_as_qfp?)` → Multi-step cascade
7. `compare_sector(metric_key, exercice, naf_code?)` → vs. BdF quartiles
8. `get_sig(exercice)` → Soldes Intermédiaires de Gestion

## Environment

Requires `GEMINI_API_KEY` in `.env`. Model: `gemini-2.0-flash`.
