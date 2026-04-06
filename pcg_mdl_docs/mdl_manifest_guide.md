# MDL Manifest Guide — `mdl_manifest.json`

> **File:** `pcg_agent/config/semantic/mdl_manifest.json`
> **Version:** 3.1
> **Reader:** `pcg_agent/semantic_layer/mdl_reader.py` (`PCGSemanticLayer`)

---

## Table of Contents

1. [What Is the MDL Manifest?](#1-what-is-the-mdl-manifest)
2. [Top-Level Structure](#2-top-level-structure)
3. [Macros](#3-macros)
4. [The Model Object](#4-the-model-object)
5. [Rubrique: The Core Building Block](#5-rubrique-the-core-building-block)
6. [The `semantic{}` Block — LLM Context](#6-the-semantic-block--llm-context)
7. [The `execution{}` Block — SQL Generation](#7-the-execution-block--sql-generation)
8. [Simple Rubriques](#8-simple-rubriques)
9. [Composite Rubriques](#9-composite-rubriques)
10. [Conditional Includes & Excludes](#10-conditional-includes--excludes)
11. [Views](#11-views)
12. [The Dual-Path Architecture](#12-the-dual-path-architecture)
13. [How to Add a New Rubrique](#13-how-to-add-a-new-rubrique)
14. [How to Modify an Existing Rubrique](#14-how-to-modify-an-existing-rubrique)
15. [Validation & Safety](#15-validation--safety)
16. [Relationship to Other Config Files](#16-relationship-to-other-config-files)
17. [Full Field Reference](#17-full-field-reference)

---

## 1. What Is the MDL Manifest?

The MDL (Modeling Definition Language) Manifest is the **single source of truth** for every financial rubrique (concept) in the PCG Agent. It defines:

- **What** each rubrique means (for the LLM)
- **How** each rubrique compiles to SQL (for the query engine)

> **Terminology:** **MDL** is *Modeling* Definition Language (same naming as Wren AI’s semantic layer), not “Measurement” Definition Language.

These two concerns are kept in separate sub-blocks (`semantic{}` and `execution{}`), read through two independent code paths — the LLM never sees SQL details, and the SQL builder never sees semantic labels.

Think of it like a dictionary where each entry has:
- A **definition** side (what a word means) → `semantic{}`
- A **pronunciation** side (how to say it) → `execution{}`

The reader (`PCGSemanticLayer`) loads this file once at startup and exposes two separate APIs — one for each side.

---

## 2. Top-Level Structure

```json
{
  "catalog": "pcg_fec_analysis",
  "version": "3.1",
  "source": "FEC (Fichier des Écritures Comptables)",

  "macros": { ... },
  "models": [ ... ],
  "views":  [ ... ]
}
```

| Field       | Purpose |
|-------------|---------|
| `catalog`   | Identifier for this analysis config |
| `version`   | Schema version (currently 3.1) |
| `source`    | The data source these rubriques apply to |
| `macros`    | Reusable polarity definitions (solde_actif, solde_passif) |
| `models`    | Array with one FEC model containing columns and calculatedFields |
| `views`     | Named groups of rubrique_keys for dashboard layouts |

---

## 3. Macros

Macros define the **polarity** — the direction of the balance calculation:

```json
"macros": {
  "solde_passif": {
    "description": "Solde crédit - débit pour comptes de passif.",
    "polarity": "credit_moins_debit"
  },
  "solde_actif": {
    "description": "Solde débit - crédit pour comptes d'actif.",
    "polarity": "debit_moins_credit"
  }
}
```

### Why polarity matters

In French accounting (Plan Comptable Général / PCG), every journal entry has a `debit` and `credit` column. Whether the **balance** is debit-minus-credit or credit-minus-debit depends on the nature of the account:

| Account type | Macro | Formula | Example |
|---|---|---|---|
| Assets (actif): cash, equipment, receivables | `solde_actif` | `debit - credit` | Banque (512): debit = money coming in |
| Liabilities & equity (passif): debts, capital, revenue | `solde_passif` | `credit - debit` | Capital (101): credit = more capital |
| Expenses (charges) | `solde_actif` | `debit - credit` | Salaires (641): debit = expense incurred |
| Revenue (produits) | `solde_passif` | `credit - debit` | Ventes (707): credit = revenue earned |

**Rule of thumb:**
- If the account's natural increase is on the **debit** side → use `solde_actif`
- If the account's natural increase is on the **credit** side → use `solde_passif`

---

## 4. The Model Object

The manifest has one model representing the FEC table:

```json
{
  "name": "FEC",
  "tableReference": "fec",
  "properties": {
    "forbidden_operations": ["INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE"],
    "exclude_journals_for_flux": ["AN"]
  },
  "columns": [ ... ],
  "calculatedFields": [ ... ]
}
```

- `tableReference` — the DuckDB table name (`fec`)
- `forbidden_operations` — SQL operations that are blocked (read-only enforcement)
- `exclude_journals_for_flux` — journal codes to exclude for flow analysis (`AN` = opening balance entries)
- `columns` — physical columns with type and capability flags
- `calculatedFields` — the array of rubrique definitions (the main content)

---

## 5. Rubrique: The Core Building Block

Each entry in `calculatedFields` is a **rubrique** — a financial concept derived from FEC journal entries. Every rubrique has exactly three parts:

```json
{
  "rubrique_key": "capitaux_propres",
  "semantic": { ... },
  "execution": { ... }
}
```

| Part | Read by | Contains |
|---|---|---|
| `rubrique_key` | Both paths | Unique identifier, used everywhere in the system |
| `semantic{}` | LLM planner only | Human-readable labels, descriptions, relationships |
| `execution{}` | SQL builder only | Account prefixes, polarity, conditions |

**`rubrique_key` is the join key** — it connects this definition to metrics, waterfalls, benchmarks, sector profiles, and views defined in other config files.

---

## 6. The `semantic{}` Block — LLM Context

This block provides everything the LLM planner needs to understand a rubrique — without any SQL implementation details.

```json
"semantic": {
  "display_name": "Capitaux Propres",
  "synonyms": ["fonds propres", "equity", "CP", "situation nette"],
  "description": "Ressources propres : capital + réserves + RAN + résultat.",
  "logic": {
    "inclusion": "Comptes 10 à 14 du PCG.",
    "exclusion": "Compte 109 (capital souscrit non appelé).",
    "intuition": "Optional — explains the accounting rationale."
  },
  "higher_is_better": true,
  "importance_level": 9,
  "domain_category": "bilan_passif",
  "bilan_section": "Passif — Capitaux propres",
  "tags": ["bilan", "passif", "solvabilite", "pcg_classe1"],
  "relationships": {
    "part_of": "total_passif",
    "used_in_ratio": ["taux_endettement_brut", "taux_endettement_net"],
    "related_to": ["compte_courant_associes"]
  },
  "reclassement": { ... }
}
```

### Field-by-field

| Field | Type | Required | Purpose |
|---|---|---|---|
| `display_name` | string | **Yes** | Human-readable label shown in reports |
| `synonyms` | string[] | **Yes** | Alternative names for fuzzy matching |
| `description` | string | **Yes** | One-line explanation of the rubrique |
| `logic.inclusion` | string | **Yes** | Which PCG accounts are included |
| `logic.exclusion` | string | No | Which PCG accounts are excluded |
| `logic.intuition` | string | No | Accounting rationale |
| `higher_is_better` | bool/null | **Yes** | Direction indicator for analysis (`null` = ambiguous) |
| `importance_level` | int (1-10) | **Yes** | Priority for the planner |
| `domain_category` | string | **Yes** | One of: `bilan_actif`, `bilan_passif`, `compte_de_resultat`, `tresorerie`, `zone_grise` |
| `bilan_section` | string | No | Display section for bilan presentation |
| `tags` | string[] | **Yes** | Searchable classification tags |
| `relationships` | object | No | Links to other rubriques and metrics |
| `reclassement` | object | No | For ambiguous accounts (e.g., CCA) that can be reclassified |

### Important rules

- **Never put SQL, account numbers as lists, or prefix logic in `semantic{}`** — use natural language only
- Account numbers in description/logic are fine as context (e.g., "Compte 109"), but the actual prefix arrays go in `execution{}`
- `synonyms` directly power the fuzzy search in `resolve_concept()` — be generous with them

---

## 7. The `execution{}` Block — SQL Generation

This block tells the SQL builder which accounts to query and how to aggregate them. It compiles to a `SUM(CASE WHEN ... THEN ... ELSE 0 END)` expression.

There are two patterns: **simple** and **composite**.

---

## 8. Simple Rubriques

A simple rubrique sums all matching rows with one polarity. This is the most common pattern.

```json
"execution": {
  "macro": "solde_passif",
  "include_prefixes": ["10", "11", "12", "13", "14"],
  "prefix_match_length": 2,
  "exclude_prefixes": ["109"],
  "exclude_prefix_match_length": 3
}
```

### What it compiles to

```sql
SUM(
  CASE WHEN LEFT(numero_compte, 2) IN ('10','11','12','13','14')
            AND LEFT(numero_compte, 3) NOT IN ('109')
       THEN credit - debit    -- from macro solde_passif
       ELSE 0
  END
)
```

### Fields

| Field | Type | Required | Default | Meaning |
|---|---|---|---|---|
| `macro` | string | **Yes** | — | Which polarity to use: `solde_actif` or `solde_passif` |
| `include_prefixes` | string[] | **Yes** | — | Account number prefixes to include |
| `prefix_match_length` | int | **Yes** | — | How many leading characters to match |
| `exclude_prefixes` | string[] | No | `[]` | Account prefixes to always exclude |
| `exclude_prefix_match_length` | int | No | `prefix_match_length + 1` | Character length for exclude matching |
| `conditional_includes` | array | No | `[]` | Include prefixes only when balance condition met |
| `conditional_excludes` | array | No | `[]` | Exclude prefixes only when balance condition met |
| `reclassement` | string | No | — | Set to `"conditional"` for ambiguous accounts |

### How prefix matching works

`prefix_match_length` controls how many characters from `numero_compte` are compared:

```
Account: 1061   prefix_match_length: 2   →  LEFT('1061', 2) = '10'  ✓ matches "10"
Account: 109    prefix_match_length: 2   →  LEFT('109',  2) = '10'  ✓ matches "10"
Account: 109    prefix_match_length: 3   →  LEFT('109',  3) = '109' ✓ used for exclude
```

The system generates `LEFT(numero_compte, N) IN (...)` in SQL. The length of the prefix strings in the array must match `prefix_match_length`.

---

## 9. Composite Rubriques

When a rubrique combines accounts with **different polarities** or **different conditions**, use `macro: "composite"` with a `composite_parts` array.

```json
"execution": {
  "macro": "composite",
  "composite_parts": [
    {
      "include_prefixes": ["70", "71", "72", "74"],
      "prefix_match_length": 2,
      "polarity": "credit_moins_debit"
    },
    {
      "include_prefixes": ["60", "61", "62", "63", "64"],
      "prefix_match_length": 2,
      "polarity": "debit_moins_credit",
      "sign": "negative"
    }
  ]
}
```

### What it compiles to

```sql
SUM(
  CASE WHEN LEFT(numero_compte, 2) IN ('70','71','72','74')
       THEN credit - debit ELSE 0 END
  +
  (-1 * CASE WHEN LEFT(numero_compte, 2) IN ('60','61','62','63','64')
             THEN debit - credit ELSE 0 END)
)
```

### Part fields

| Field | Type | Required | Default | Meaning |
|---|---|---|---|---|
| `include_prefixes` | string[] | **Yes** | — | Account prefixes |
| `prefix_match_length` | int | **Yes** | — | Characters to match |
| `polarity` | string | **Yes** | — | `credit_moins_debit` or `debit_moins_credit` |
| `sign` | string | No | `"positive"` | `"negative"` wraps the CASE in `(-1 * ...)` |
| `condition` | string | No | — | `solde_positive` or `solde_negative` (see below) |

### When to use composite

Use composite when:
- **Different account classes have different polarities** (e.g., EBE = revenue minus expenses)
- **Some accounts need a balance condition** (e.g., bank accounts included only if positive)
- **You need to subtract one group from another** (use `sign: "negative"`)

---

## 10. Conditional Includes & Excludes

Sometimes an account should only be included or excluded **depending on its individual balance direction**. This is common for bank accounts (512) which can be positive (asset) or negative (overdraft = liability).

### Solde conditions

| Condition | SQL | Meaning |
|---|---|---|
| `solde_positive` | `(debit - credit) > 0` | Account has a net debit balance (typical for assets) |
| `solde_negative` | `(credit - debit) > 0` | Account has a net credit balance (typical for liabilities) |

These are **absolute** — they describe the direction of the account balance regardless of the rubrique's own polarity.

### In composite rubriques

Add `"condition"` to a part:

```json
{
  "include_prefixes": ["512", "530", "531"],
  "prefix_match_length": 3,
  "polarity": "debit_moins_credit",
  "condition": "solde_positive"
}
```

This means: include 512/530/531 rows **only when** their individual debit > credit (positive bank balance).

**Real-world example — trésorerie active vs passive:**

| Rubrique | Account 512 | Condition | Meaning |
|---|---|---|---|
| `tresorerie_active` | Included | `solde_positive` | Bank balance > 0 → it's cash |
| `tresorerie_passive` | Included | `solde_negative` | Bank balance < 0 → it's an overdraft |

### In simple rubriques

Add `conditional_excludes` or `conditional_includes` to the execution spec:

```json
"execution": {
  "macro": "solde_passif",
  "include_prefixes": ["10", "11", "12", "13", "14"],
  "prefix_match_length": 2,
  "conditional_excludes": [
    { "prefixes": ["109"], "condition": "solde_positive" }
  ]
}
```

This compiles to:

```sql
SUM(
  CASE WHEN LEFT(numero_compte, 2) IN ('10','11','12','13','14')
            AND NOT (LEFT(numero_compte, 3) IN ('109') AND (debit - credit) > 0)
       THEN credit - debit
       ELSE 0
  END
)
```

Meaning: include accounts 10-14, but **exclude 109 only when it actually has a debit balance** (CSNA not yet called up).

**`conditional_includes`** works the same way but is OR-added to the include clause:

```json
"conditional_includes": [
  { "prefixes": ["512"], "condition": "solde_positive" }
]
```

Compiles to: `(std_includes OR (LEFT(nc,3) IN ('512') AND (debit-credit) > 0))`

---

## 11. Views

Views are named groups of rubrique_keys used for dashboard layouts:

```json
"views": [
  {
    "name": "SIG_simplifie",
    "displayName": "Soldes Intermédiaires de Gestion (simplifié coiffure)",
    "rubrique_keys": ["chiffre_affaires", "masse_salariale", "excedent_brut_exploitation", "resultat_net"]
  }
]
```

No SQL logic here — views just reference existing rubrique_keys. They're consumed by `get_view()` in the reader.

---

## 12. The Dual-Path Architecture

The MDL reader (`PCGSemanticLayer`) enforces strict separation:

```
                     mdl_manifest.json
                     ┌──────────────────┐
                     │  rubrique_key    │
                     ├──────┬───────────┤
                     │ sem  │ execution │
                     └──┬───┴─────┬─────┘
                        │         │
            ┌───────────┘         └───────────┐
            ▼                                 ▼
    SEMANTIC PATH                      EXECUTION PATH
    get_semantic_context()             build_rubrique_sql()
    resolve_concept()                  build_trend_sql()
    build_domain_context()             build_breakdown_sql()
            │                          compute_metric()
            ▼                                 │
    LLM Planner                               ▼
    (sees labels, tags,                DuckDB Engine
     descriptions — never SQL)         (runs SQL — never sees labels)
```

**Strict rules:**
- The LLM **never** sees `execution{}` — no account prefixes, no polarity, no SQL fragments
- The SQL builder **never** reads `semantic{}` — no labels, no descriptions
- All cross-referencing happens through `rubrique_key` strings

---

## 13. How to Add a New Rubrique

### Step 1: Identify the PCG accounts

Look up the relevant accounts in the PCG (Plan Comptable Général). You need to know:
- Which account prefixes to include
- Which to exclude (if any)
- The polarity (asset/expense = `solde_actif`, liability/equity/revenue = `solde_passif`)
- Whether any accounts need conditional balance filtering

### Step 2: Write the entry

Add a new object inside `calculatedFields`:

```json
{
  "rubrique_key": "your_new_key",
  "semantic": {
    "display_name": "Your Display Name",
    "synonyms": ["alternative name 1", "alternative name 2"],
    "description": "One-line description of what this measures.",
    "logic": {
      "inclusion": "Which accounts are included and why.",
      "exclusion": "Which accounts are excluded and why."
    },
    "higher_is_better": true,
    "importance_level": 7,
    "domain_category": "bilan_actif",
    "tags": ["bilan", "actif", "your_tag"]
  },
  "execution": {
    "macro": "solde_actif",
    "include_prefixes": ["XXX"],
    "prefix_match_length": 3
  }
}
```

### Step 3: Validate

Run the smoke test or start the server — `_validate_metric_inputs()` runs at startup and will catch any inconsistency with `metrics.json`.

### Step 4: Wire it up (optional)

If this rubrique is used in a metric, add it to `metrics.json` and list it in that metric's `rubrique_keys`.

If it should appear in a dashboard, add its key to a `views` entry.

### Checklist

- [ ] `rubrique_key` is unique and uses `snake_case`
- [ ] `semantic{}` has all required fields (display_name, synonyms, description, logic, higher_is_better, importance_level, domain_category, tags)
- [ ] `execution{}` has `macro`, `include_prefixes`, `prefix_match_length`
- [ ] Prefix strings match the declared `prefix_match_length` in character count
- [ ] If used in a metric, added to that metric's `rubrique_keys` in `metrics.json`
- [ ] If it needs conditional filtering, `conditional_includes`/`conditional_excludes` or composite parts have the right `condition`

---

## 14. How to Modify an Existing Rubrique

### Changing semantic data (labels, descriptions, tags)

Edit the `semantic{}` block. No code changes needed — the reader loads it dynamically. This is the lowest-risk change.

### Changing which accounts are included

Edit the `execution{}` block:
- Update `include_prefixes` / `exclude_prefixes`
- Double-check `prefix_match_length` matches the string length

The generated SQL changes automatically on next startup — no Python changes needed.

### Changing from simple to composite

Replace the execution spec:

```json
// Before (simple)
"execution": {
  "macro": "solde_actif",
  "include_prefixes": ["512", "530"],
  "prefix_match_length": 3
}

// After (composite)
"execution": {
  "macro": "composite",
  "composite_parts": [
    {
      "include_prefixes": ["512"],
      "prefix_match_length": 3,
      "polarity": "debit_moins_credit",
      "condition": "solde_positive"
    },
    {
      "include_prefixes": ["530"],
      "prefix_match_length": 3,
      "polarity": "debit_moins_credit"
    }
  ]
}
```

### Renaming a rubrique_key

This requires updating **all** references across the config:
- `metrics.json` → `rubrique_keys` and `result` expressions
- `waterfalls.json` → cascade steps
- `sector_profiles.json` → active_concepts
- `views` in this manifest
- Any `relationships` in other rubriques' semantic blocks

---

## 15. Validation & Safety

### Startup validation

When `PCGSemanticLayer` loads, `_validate_metric_inputs()` checks:

| Check | What it catches |
|---|---|
| Every metric's `rubrique_keys` declared | Missing `rubrique_keys` field |
| Each declared key exists in `_fields` | Typo in a rubrique_key |
| Declared set = derived set from expression tree | Mismatch between `rubrique_keys` and `result{}` |

If any check fails, the server **refuses to start** with a detailed error message.

### SQL safety

- All operations are SELECT-only (`forbidden_operations` in manifest)
- Account prefixes come from config, never from user input
- The SQL builder inlines prefix strings as SQL literals (safe because they're validated config)
- The `_security_check()` in the dispatcher blocks any attempt to inject write operations

---

## 16. Relationship to Other Config Files

```
mdl_manifest.json (rubriques)
     │
     ├──→ metrics.json         rubrique_keys as inputs to metric formulas
     ├──→ waterfalls.json      rubrique_keys as cascade steps
     ├──→ benchmarks_bdf.json  metric_keys benchmarked (metrics reference rubriques)
     ├──→ sector_profiles.json active_concepts = list of rubrique_keys per sector
     └──→ agent_spec.json      tool definitions reference rubrique_key and metric_key
```

The manifest is the **foundation** — other files reference its `rubrique_key` values but never duplicate the SQL or semantic definitions.

---

## 17. Full Field Reference

### Top level

| Field | Type | Description |
|---|---|---|
| `catalog` | string | Analysis config identifier |
| `version` | string | Schema version |
| `source` | string | Data source description |
| `macros` | object | Polarity definitions |
| `models` | array | One FEC model entry |
| `views` | array | Named rubrique groups |

### Macro

| Field | Type | Values |
|---|---|---|
| `description` | string | Human explanation |
| `polarity` | string | `credit_moins_debit` or `debit_moins_credit` |

### Rubrique (calculatedField)

| Field | Type | Description |
|---|---|---|
| `rubrique_key` | string | Unique identifier (snake_case) |
| `semantic` | object | LLM-facing metadata |
| `execution` | object | SQL-facing compilation spec |

### semantic{} fields

| Field | Type | Required |
|---|---|---|
| `display_name` | string | Yes |
| `synonyms` | string[] | Yes |
| `description` | string | Yes |
| `logic` | object | Yes |
| `logic.inclusion` | string | Yes |
| `logic.exclusion` | string | No |
| `logic.intuition` | string | No |
| `higher_is_better` | bool/null | Yes |
| `importance_level` | int (1-10) | Yes |
| `domain_category` | string | Yes |
| `bilan_section` | string | No |
| `tags` | string[] | Yes |
| `relationships` | object | No |
| `relationships.part_of` | string | No |
| `relationships.used_in_ratio` | string[] | No |
| `relationships.related_to` | string[] | No |
| `reclassement` | object | No |

### execution{} fields (simple)

| Field | Type | Required | Default |
|---|---|---|---|
| `macro` | string | Yes | — |
| `include_prefixes` | string[] | Yes | — |
| `prefix_match_length` | int | Yes | — |
| `exclude_prefixes` | string[] | No | `[]` |
| `exclude_prefix_match_length` | int | No | `prefix_match_length + 1` |
| `conditional_includes` | array | No | `[]` |
| `conditional_excludes` | array | No | `[]` |
| `reclassement` | string | No | — |

### execution{} fields (composite)

| Field | Type | Required |
|---|---|---|
| `macro` | string (`"composite"`) | Yes |
| `composite_parts` | array | Yes |

### composite_parts[] entry

| Field | Type | Required | Default |
|---|---|---|---|
| `include_prefixes` | string[] | Yes | — |
| `prefix_match_length` | int | Yes | — |
| `polarity` | string | Yes | — |
| `sign` | string | No | `"positive"` |
| `condition` | string | No | — |

### conditional_includes[] / conditional_excludes[] entry

| Field | Type | Required |
|---|---|---|
| `prefixes` | string[] | Yes |
| `condition` | string (`solde_positive` / `solde_negative`) | Yes |

### View

| Field | Type | Description |
|---|---|---|
| `name` | string | Machine identifier |
| `displayName` | string | Human-readable title |
| `rubrique_keys` | string[] | Ordered list of rubriques in this view |
