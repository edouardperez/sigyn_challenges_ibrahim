# AGENTS.md — Coding Guidelines for PCG FEC Agent

This document provides coding guidelines for AI agents working on the **PCG FEC Agent** codebase—a config-driven financial analysis system for French accounting (FEC files) using LangGraph, Google Gemini (backend), and Next.js + assistant-ui (frontend).

---

## 🚀 Quick Start Commands

### Backend (Python/FastAPI)
```bash
# Install dependencies
pip install -r requirements.txt

# Setup environment
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Unix/MacOS

# Set API key in .env
echo "GEMINI_API_KEY=your_key_here" > .env

# Run server (auto-reload enabled)
python main.py
# OR: uvicorn main:app --reload --port 8000

# API docs: http://localhost:8000/docs
```

### Frontend (Next.js/TypeScript)
```bash
cd frontend

# Install dependencies
npm install

# Set OpenAI key in .env.local
echo "OPENAI_API_KEY=sk-..." > .env.local

# Run dev server (with Turbopack)
npm run dev

# Build for production
npm run build

# Lint/format (Biome)
npm run lint        # Check code
npm run lint:fix    # Auto-fix issues
npm run format      # Check formatting
npm run format:fix  # Auto-format
```

### Testing
```bash
# Backend: Run smoke test (validates full data pipeline, no API key needed)
python test_smoke.py

# Frontend: No test suite configured yet
```

---

## 📁 Project Structure

```
sygin/
├── main.py                              # FastAPI entry point
├── test_smoke.py                        # End-to-end smoke test (143 lines)
├── requirements.txt                     # Python dependencies
├── .env                                 # Environment variables (GEMINI_API_KEY)
├── data/                                # Sample / reference data files
│   ├── FEC_blckbx_cannes_2025.xlsx      # Sample FEC file (9,375 entries)
│   └── PCG simplifié.csv                # Reference PCG (simplified chart)
├── pcg_agent/                           # Main package (23 Python files)
│   ├── api/                             # FastAPI routes
│   │   ├── routes.py                    # /upload-fec, /chat endpoints
│   │   └── _runtime.py                  # Shared runtime state
│   ├── config/                          # Multi-layer config (JSON only)
│   │   ├── agent_spec.json              # Tools, planner policy, security
│   │   ├── semantic/mdl_manifest.json   # SQL expressions per rubrique
│   │   ├── ontology/                    # Concepts, taxonomy, business rules
│   │   └── metrics/                     # Ratios, benchmarks, waterfalls
│   ├── graph/                           # LangGraph orchestration
│   │   ├── graph.py                     # StateGraph builder
│   │   ├── state.py                     # AgentState, Plan, ToolResult
│   │   └── nodes/                       # Planner, executor, replanner, etc.
│   ├── ingestion/fec_loader.py          # L0: FEC xlsx/csv → DataFrame
│   ├── query_engine/duckdb_engine.py    # L1: DuckDB SQL execution
│   ├── semantic_layer/mdl_reader.py     # L2/L3: SQL builder + concepts
│   └── tools/                           # Waterfall, sector comparison, dispatch
└── frontend/                            # Next.js app (TypeScript + assistant-ui)
    ├── app/                             # Next.js App Router
    │   ├── api/chat/route.ts            # Chat API endpoint
    │   ├── assistant.tsx                # Runtime provider setup
    │   └── page.tsx                     # Landing page
    ├── components/                      # React components
    │   ├── assistant-ui/                # Chat UI (thread, attachments)
    │   ├── tool-ui/                     # Tool renderers (chart, table, etc)
    │   └── toolkit.tsx                  # Tool registry for LLM responses
    ├── lib/                             # Utilities (FEC adapter, utils)
    └── package.json                     # npm scripts + dependencies
```

---

## 🏗️ Architecture Overview

### 6-Layer Config-Driven System
- **L0:** FEC Ingestion (raw → normalized DataFrame)
- **L1:** DuckDB Query Engine (zero-copy SQL on pandas)
- **L2:** Semantic Layer (MDL manifest with SQL expressions)
- **L3:** Ontology Layer (concepts, taxonomy, business rules)
- **L4:** Metric Layer (ratios, benchmarks, waterfalls)
- **L5:** Agent Spec (tools, planner policy, security guardrails)

### LangGraph Flow
```
START → context_builder → planner → executor (loop) → synthesizer → END
                                         ↓
                                    replanner (on error)
```

### Design Philosophy
**Config-driven, not code-driven:** Business logic lives in JSON files, not Python code.
- ❌ **Wrong:** Hardcode SQL in Python functions
- ✅ **Right:** Reference `rubrique_key` in code, SQL expression in `mdl_manifest.json`

---

## 🎨 Code Style Guidelines

### Python Backend

**Import Order:**
```python
from __future__ import annotations  # ✅ Always first (Python 3.7+ compatibility)

# 1. Standard library
import json
from pathlib import Path
from typing import Any, Optional

# 2. Third-party packages
import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# 3. Local imports (absolute from package root, NEVER relative)
from pcg_agent.graph.state import AgentState
from pcg_agent.semantic_layer.mdl_reader import PCGSemanticLayer
```

**Rules:**
- ✅ Use absolute imports from `pcg_agent` package root
- ❌ Never use relative imports (`from . import ...`)
- ✅ Group imports: stdlib → third-party → local
- ✅ Always include `from __future__ import annotations`

**Naming Conventions:**
```python
# Variables/functions: snake_case
user_message = "Hello"
def build_rubrique_sql(rubrique_key: str) -> str:

# Classes: PascalCase
class FECIngestion:
class AgentState(TypedDict):

# Constants: UPPERCASE
COLUMN_MAP = {...}
PLANNER_SYSTEM_PROMPT = """..."""

# Private methods: _leading_underscore
def _validate(self, df: pd.DataFrame):
def _load_json(self, path: str) -> dict:
```

**Type Annotations:**
```python
# Modern type hints (Python 3.9+ style with | for Union)
def load(self, filepath: str | Path) -> pd.DataFrame:
def fetch_one(self, sql: str) -> dict[str, Any]:

# Optional for nullable types
plan: Optional[Plan] = None

# Type hints REQUIRED for all function signatures
```

**Docstrings:**
- Use Google-style docstrings (not NumPy or Sphinx)
- Module-level docstring at top of file
- One-line summary in imperative mood for functions
- Document Args, Returns, Raises (but omit types since they're in signature)

**File Paths:**
```python
from pathlib import Path

# Always use Path objects (not os.path)
BASE_DIR = Path(__file__).parent
config_dir = BASE_DIR / "pcg_agent" / "config"
filepath = Path(filepath)  # Convert str to Path
```

### TypeScript Frontend

**Imports:**
```typescript
// 1. React/Next.js core
import { useState } from "react";
import type { Metadata } from "next";

// 2. Third-party packages
import { openai } from "@ai-sdk/openai";
import type { Toolkit } from "@assistant-ui/react";

// 3. Local components (use @ alias)
import { Chart } from "@/components/tool-ui/chart";
import { cn } from "@/lib/utils";
```

**Naming:**
- Components: PascalCase (`MetricCardRenderer`, `WaterfallCard`)
- Functions/variables: camelCase (`statusTone`, `formatValue`)
- Types/Interfaces: PascalCase (`MetricCardBlock`, `ToolResult`)
- Constants: SCREAMING_SNAKE_CASE or camelCase for objects

**Strict Mode:**
- TypeScript strict mode is enabled (`tsconfig.json`)
- Always define types for props and return values
- Use `type` for objects, `interface` for extendable contracts
- Prefer `unknown` over `any` when type is uncertain

**Formatting:**
- Use Biome for linting and formatting (run `npm run lint:fix`)
- JSX uses double quotes, JavaScript uses single quotes where applicable

---

## 🔧 Data Structures & Patterns

### Pydantic for Validation
```python
# Use Pydantic BaseModel for data validation (NOT dataclasses)
class PlanStep(BaseModel):
    id: str
    tool: str
    args: dict[str, Any] = {}
    depends_on: list[str] = []

# Exception: TypedDict required for LangGraph state
class AgentState(TypedDict, total=False):
    user_message: str
    plan: Optional[Plan]
```

### Error Handling
```python
# Custom exceptions for domain errors
class SecurityError(Exception):
    pass

# Raise with descriptive messages (include context)
if diff > 0.01:
    raise ValueError(
        f"Balance check failed: debit={total_debit:.2f}, "
        f"credit={total_credit:.2f}, diff={diff:.2f}"
    )

# Try-finally for resource cleanup
try:
    with open(tmp_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    # ... process file ...
finally:
    if tmp_path.exists():
        tmp_path.unlink()
```

### Security Patterns
```python
# SQL injection prevention (enforced in dispatcher)
BLOCK_PATTERNS = ["DROP", "DELETE", "INSERT", "UPDATE", "TRUNCATE", "UNION SELECT"]

def _security_check(sql: str) -> None:
    sql_upper = sql.upper()
    for pattern in BLOCK_PATTERNS:
        if pattern.upper() in sql_upper:
            raise SecurityError(f"Blocked SQL pattern detected: {pattern}")

# All queries MUST be SELECT-only (enforced in agent_spec.json)
```

---

## 🛡️ Critical Rules

### 1. Config-First Development
**Business logic belongs in JSON config, NOT Python code.**

Example (computing "Capitaux propres"):
```python
# ❌ WRONG: Hardcode SQL in Python
def get_capitaux_propres(df, exercice):
    sql = """
        SELECT SUM(credit - debit) 
        FROM fec 
        WHERE compte_prefix_2 IN ('10', '11', '12', '13')
    """
    return execute(sql)

# ✅ RIGHT: Reference rubrique_key, SQL lives in mdl_manifest.json
def get_capitaux_propres(semantic, exercice):
    sql = semantic.build_rubrique_sql("capitaux_propres", exercice=exercice)
    return semantic.engine.fetch_one(sql)
```

**Why?** Non-technical users can modify accounting rules without changing code.

### 2. Immutable Operations
```python
# ✅ All database operations are SELECT-only
# ❌ Never use INSERT, UPDATE, DELETE, DROP, TRUNCATE

# Enforced at two levels:
# 1. agent_spec.json guardrails: {"readonly": true}
# 2. Security check in dispatcher.py
```

### 3. Separation of Concerns
- **Planner (LLM):** Only manipulates `rubrique_key` strings, NEVER raw SQL
- **Semantic Layer:** Translates `rubrique_key` → SQL
- **Query Engine:** Executes SQL on DataFrame
- **Evaluator:** Applies thresholds and benchmarks

### 4. Testing Philosophy
**Test the data pipeline independent of LLM:**
- Smoke test validates: ingestion → query → evaluation
- Test with real FEC data (9,375 entries from sample file)
- Mock LLM calls for unit tests (future)
- Each layer should be testable in isolation

---

## 📝 Common Patterns

### Loading Config Files
```python
from pathlib import Path
import json

def _load_json(self, relative_path: str) -> dict:
    path = self.config_dir / relative_path
    with open(path, encoding="utf-8") as f:
        return json.load(f)

# Usage
self._mdl = self._load_json("semantic/mdl_manifest.json")
self._concepts = self._load_json("ontology/concepts.json")
```

### DataFrame Validation
```python
def _validate(self, df: pd.DataFrame) -> None:
    """Validate FEC DataFrame has required columns and balanced debits/credits."""
    required = ["compte", "debit", "credit", "libelle", "date"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    
    # Check balance
    total_debit = df["debit"].sum()
    total_credit = df["credit"].sum()
    diff = abs(total_debit - total_credit)
    if diff > 0.01:
        raise ValueError(
            f"FEC not balanced: debit={total_debit:.2f}, "
            f"credit={total_credit:.2f}, diff={diff:.2f}"
        )
```

### Tool Dispatcher Pattern
```python
# tools/dispatcher.py
def dispatch(
    tool: str,
    args: dict,
    engine: FECQueryEngine,
    semantic: PCGSemanticLayer,
) -> dict:
    """Route tool calls to appropriate handlers with security checks."""
    if tool == "query_rubrique":
        return query_rubrique(args, engine, semantic)
    elif tool == "query_ratio":
        return query_ratio(args, engine, semantic)
    # ...
    else:
        raise ValueError(f"Unknown tool: {tool}")
```

---

## 🚨 Common Pitfalls to Avoid

1. **Hardcoding SQL:** Always use `semantic.build_rubrique_sql()` instead of writing SQL strings
2. **Relative imports:** Use `from pcg_agent.x import y`, NOT `from . import y`
3. **Missing type hints:** All functions must have parameter and return type annotations
4. **Modifying DataFrames in-place:** FEC DataFrame is read-only (queries only)
5. **Forgetting `from __future__ import annotations`:** Required for `str | Path` syntax
6. **Using `os.path`:** Always use `pathlib.Path` instead
7. **Exposing raw SQL to LLM:** Planner should only see `rubrique_key` identifiers

---

## 📚 Key Files to Read

- `pcg_data_agent_architecture_finale.md` — 1,191-line architecture specification
- `pcg_agent/config/agent_spec.json` — Available tools, security guardrails
- `pcg_agent/config/semantic/mdl_manifest.json` — SQL expressions for each rubrique
- `pcg_agent/semantic_layer/mdl_reader.py` — Core semantic layer implementation
- `test_smoke.py` — Example of testing the full data pipeline

---

**Version:** 1.0  
**Last Updated:** 2026-04-04  
**Project:** PCG FEC Agent — Config-driven financial analysis for French accounting
