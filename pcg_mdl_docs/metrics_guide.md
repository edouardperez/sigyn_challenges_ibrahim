# Metrics Guide — `metrics.json`

> **File:** `pcg_agent/config/metrics/metrics.json`  
> **Version:** 1.0  
> **Reader:** `pcg_agent/semantic_layer/mdl_reader.py` (`PCGSemanticLayer`)

---

## Table of Contents

1. [What Is metrics.json?](#1-what-is-metricsjson)
2. [Top-Level Structure](#2-top-level-structure)
3. [Metric Object](#3-metric-object)
4. [Formula & Result Expression Tree](#4-formula--result-expression-tree)
5. [Output Formats](#5-output-formats)
6. [Thresholds & Status Evaluation](#6-thresholds--status-evaluation)
7. [Sector Comparison](#7-sector-comparison)
8. [Caveats & Warnings](#8-caveats--warnings)
9. [Rubrique Alerts](#9-rubrique-alerts)
10. [How to Add a New Metric](#10-how-to-add-a-new-metric)
11. [How to Modify an Existing Metric](#11-how-to-modify-an-existing-metric)
12. [Validation & Safety](#12-validation--safety)
13. [Relationship to Other Config Files](#13-relationship-to-other-config-files)
14. [Full Field Reference](#14-full-field-reference)

---

## 1. What Is metrics.json?

The metrics file defines **calculated financial ratios** derived from rubriques (balance sheet and P&L items defined in `mdl_manifest.json`). Each metric:

- **References rubriques** as inputs (e.g., `endettement_brut`, `capitaux_propres`)
- **Defines a formula** (e.g., `endettement_brut / capitaux_propres`)
- **Provides an expression tree** for programmatic evaluation
- **Sets thresholds** for healthy/warning/critical status
- **Optionally enables sector benchmarking** against Banque de France data

Metrics are used by the `query_metric` tool and the `compare_sector` tool to provide contextualized financial analysis with automatic status evaluation.

---

## 2. Top-Level Structure

```json
{
  "metrics": [ ... ],
  "rubrique_alerts": { ... }
}
```

| Field | Purpose |
|---|---|
| `metrics` | Array of ratio definitions (the main content) |
| `rubrique_alerts` | Threshold rules for individual rubriques (not ratios) |

---

## 3. Metric Object

Each entry in the `metrics` array defines one financial ratio:

```json
{
  "metric_key": "taux_endettement_brut",
  "metric_type": "ratio",
  "display_name": "Taux d'Endettement Brut",
  "rubrique_keys": ["endettement_brut", "capitaux_propres"],
  "formula": "endettement_brut / capitaux_propres",
  "result": {
    "op": "divide",
    "left": "endettement_brut",
    "right": "capitaux_propres"
  },
  "output_format": "multiple",
  "higher_is_better": false,
  "thresholds": { ... },
  "sector_comparison": true,
  "caveat_if_low_equity": { ... }
}
```

### Field-by-field

| Field | Type | Required | Purpose |
|---|---|---|---|
| `metric_key` | string | **Yes** | Unique identifier (snake_case) — used in tools and other config |
| `metric_type` | string | **Yes** | Currently always `"ratio"` (future: waterfall, trend, etc.) |
| `display_name` | string | **Yes** | Human-readable label shown in reports |
| `rubrique_keys` | string[] | **Yes** | Rubriques used as inputs (must exist in mdl_manifest) |
| `formula` | string | **Yes** | Human-readable formula for documentation |
| `result` | object | **Yes** | Expression tree for programmatic evaluation |
| `output_format` | string | **Yes** | `"percentage"` or `"multiple"` |
| `higher_is_better` | bool | **Yes** | Direction indicator for threshold interpretation |
| `thresholds` | object | **Yes** | Status boundaries (healthy/warning/critical) |
| `sector_comparison` | bool | No | `true` enables BdF benchmarking (default: `false`) |
| `sector_specific` | string | No | NAF code if metric is sector-specific (e.g., `"96.02A"`) |
| `note` | string | No | Additional context or interpretation guidance |
| `caveat_if_low_equity` | object | No | Warning if denominator (CP) is too small |

---

## 4. Formula & Result Expression Tree

Every metric has **two representations** of the same calculation:

### `formula` (string)

A human-readable mathematical expression for documentation:

```json
"formula": "(endettement_brut - tresorerie_active) / capitaux_propres"
```

This is **not executed** — it's shown to users and the LLM for context.

### `result` (expression tree)

A recursive structure that the semantic layer evaluates programmatically:

```json
"result": {
  "op": "divide",
  "left": {
    "op": "subtract",
    "left": "endettement_brut",
    "right": "tresorerie_active"
  },
  "right": "capitaux_propres"
}
```

### Expression tree operators

| Operator | Args | Meaning |
|---|---|---|
| `"divide"` | `left`, `right` | `left / right` |
| `"multiply"` | `left`, `right` | `left * right` |
| `"add"` | `left`, `right` | `left + right` |
| `"subtract"` | `left`, `right` | `left - right` |

### Leaf nodes

Leaf nodes are **rubrique_key strings** that reference rubriques defined in `mdl_manifest.json`:

```json
"left": "endettement_brut"
```

The evaluator calls `build_rubrique_sql()` for each leaf node, executes the SQL, and substitutes the numeric result into the tree.

### Evaluation order

The semantic layer evaluates the tree **depth-first**:

1. Resolve all leaf nodes (rubrique_keys) → numeric values
2. Apply operators bottom-up
3. Return final numeric result

**Example:**

```
taux_endettement_net = (endettement_brut - tresorerie_active) / capitaux_propres

Tree:
    divide
    ├─ subtract
    │  ├─ endettement_brut     → 150000 (SQL query)
    │  └─ tresorerie_active    → 30000  (SQL query)
    └─ capitaux_propres        → 80000  (SQL query)

Evaluation:
    subtract: 150000 - 30000 = 120000
    divide:   120000 / 80000 = 1.5
    
Result: 1.5 (taux = 1.5x)
```

---

## 5. Output Formats

The `output_format` field controls how the numeric result is displayed:

| Format | Example Value | Display | Usage |
|---|---|---|---|
| `"percentage"` | `0.42` | `42.0%` | Margins, cost ratios (multiply by 100) |
| `"multiple"` | `1.5` | `1.5x` | Debt ratios, leverage (display as-is) |
| `"euros"` | `85000` | `85,000.00 EUR` | Absolute amounts in euros |

### Percentage

For ratios expressed as a fraction of a total (e.g., margin, cost as % of revenue):

```json
{
  "metric_key": "marge_ebe",
  "formula": "excedent_brut_exploitation / chiffre_affaires",
  "output_format": "percentage"
}
```

If EBE = 50,000 and CA = 200,000:
- Result = 0.25
- Display = **25.0%**

### Multiple

For ratios expressed as "times" or "multiples" (e.g., debt-to-equity):

```json
{
  "metric_key": "taux_endettement_brut",
  "formula": "endettement_brut / capitaux_propres",
  "output_format": "multiple"
}
```

If debt = 120,000 and equity = 80,000:
- Result = 1.5
- Display = **1.5x**

### Euros

For metrics that represent absolute monetary amounts (not ratios):

```json
{
  "metric_key": "capitaux_propres_nets",
  "formula": "capitaux_propres - capital_souscrit_non_appele",
  "output_format": "euros"
}
```

If CP = 90,000 and CSNA = 5,000:
- Result = 85000
- Display = **85,000.00 EUR**

**Note:** Use `"euros"` for:
- Calculated absolute amounts (e.g., net equity, working capital)
- Differences or deltas (e.g., variation year-over-year)
- Aggregated sums across multiple rubriques

Use `query_rubrique` (not `query_metric`) for querying single balance sheet or P&L items directly.

---

## 6. Thresholds & Status Evaluation

Thresholds define the **boundaries** between healthy, warning, and critical zones. The semantic layer evaluates the metric value against these thresholds and returns a status.

### Threshold structure

```json
"thresholds": {
  "healthy": { "max": 1.0, "label": "Endettement maîtrisé (< 1x)" },
  "warning": { "min": 1.0, "max": 3.0, "label": "Endettement élevé (1-3x)" },
  "critical": { "min": 3.0, "label": "Endettement excessif (> 3x)" }
}
```

Each threshold has:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `min` | float | No | Inclusive lower bound (omit for "no lower limit") |
| `max` | float | No | Exclusive upper bound (omit for "no upper limit") |
| `label` | string | **Yes** | Human-readable description of this zone |

### Evaluation logic (higher_is_better = false)

For metrics where **lower is better** (e.g., debt ratios, cost ratios):

```
healthy:  value < 1.0
warning:  1.0 ≤ value < 3.0
critical: value ≥ 3.0
```

### Evaluation logic (higher_is_better = true)

For metrics where **higher is better** (e.g., margins, profitability):

```json
"higher_is_better": true,
"thresholds": {
  "healthy": { "min": 0.10, "label": "Marge saine (> 10%)" },
  "warning": { "min": 0.05, "max": 0.10, "label": "Marge faible (5-10%)" },
  "critical": { "max": 0.05, "label": "Marge très faible (< 5%)" }
}
```

**Evaluation:**
```
critical: value < 0.05
warning:  0.05 ≤ value < 0.10
healthy:  value ≥ 0.10
```

### Return format

The semantic layer returns:

```json
{
  "metric_key": "taux_endettement_brut",
  "display_name": "Taux d'Endettement Brut",
  "value": 1.5,
  "output_format": "multiple",
  "status": {
    "level": "warning",
    "label": "Endettement élevé (1-3x)"
  },
  "rubrique_inputs": { ... }
}
```

---

## 7. Sector Comparison

When `"sector_comparison": true`, the semantic layer also returns the metric's position relative to sector benchmarks (Banque de France quartiles).

### Configuration

```json
{
  "metric_key": "taux_endettement_net",
  "sector_comparison": true
}
```

This enables the `compare_sector` tool, which:

1. Computes the metric value
2. Looks up benchmarks in `benchmarks_bdf.json`
3. Compares the value to Q1, median, Q3
4. Returns a position label

### Return format

```json
{
  "metric_key": "taux_endettement_net",
  "value": 1.2,
  "sector_position": {
    "q1": 0.8,
    "mediane": 1.5,
    "q3": 2.3,
    "position": "En dessous de la médiane secteur (1.5x)"
  }
}
```

### Sector-specific metrics

Some metrics only apply to specific sectors:

```json
{
  "metric_key": "poids_masse_salariale",
  "sector_specific": "96.02A",
  "note": "En coiffure, la masse salariale est le premier poste. Médiane secteur ~42%."
}
```

If the FEC is from a different sector, the tool returns a warning:

```json
{
  "maturity_warning": "Métrique spécifique au secteur 96.02A (coiffure) — interprétation limitée pour d'autres secteurs."
}
```

---

## 8. Caveats & Warnings

Some metrics have **context-dependent warnings** that appear when certain conditions are met.

### caveat_if_low_equity

For debt ratios, a low equity base makes the ratio mechanically high even if debt is normal:

```json
"caveat_if_low_equity": {
  "threshold_cp": 10000,
  "message": "CP très faibles — le ratio est mécaniquement élevé sans que l'endettement soit anormalement fort."
}
```

**Logic:**

```python
if capitaux_propres < 10000:
    caveats.append(message)
```

**Return format:**

```json
{
  "metric_key": "taux_endettement_brut",
  "value": 8.5,
  "status": { "level": "critical", ... },
  "caveats": [
    "CP très faibles — le ratio est mécaniquement élevé sans que l'endettement soit anormalement fort."
  ]
}
```

### Future caveat types

Planned (not yet implemented):
- `caveat_if_negative_denominator`: Warn if denominator is negative (e.g., negative equity)
- `caveat_if_low_revenue`: Warn if CA < threshold for cost ratios
- `caveat_if_missing_data`: Warn if required rubrique has zero/null value

---

## 9. Rubrique Alerts

The `rubrique_alerts` section defines **threshold rules for individual rubriques** (not ratios). These are triggered when querying a rubrique with `query_rubrique`.

### Structure

```json
"rubrique_alerts": {
  "tresorerie_active": {
    "critical": { "max": 0, "label": "Trésorerie négative — risque de cessation de paiements." }
  },
  "capitaux_propres": {
    "critical": { "max": 0, "label": "Capitaux propres négatifs — situation nette déficitaire." },
    "warning": { "max": 10000, "label": "Capitaux propres très faibles — capacité d'emprunt limitée." }
  }
}
```

### Evaluation

When `query_rubrique` is called for a rubrique with alerts:

```python
value = compute_rubrique("capitaux_propres")  # e.g., 8000

alerts = []
if value < 0:
    alerts.append({"level": "critical", "label": "Capitaux propres négatifs..."})
elif value < 10000:
    alerts.append({"level": "warning", "label": "Capitaux propres très faibles..."})
```

### Return format

```json
{
  "rubrique_key": "capitaux_propres",
  "label": "Capitaux Propres",
  "value": 8000,
  "alerts": [
    {
      "level": "warning",
      "label": "Capitaux propres très faibles — capacité d'emprunt limitée."
    }
  ]
}
```

### Common alert patterns

| Rubrique | Alert Type | Meaning |
|---|---|---|
| `tresorerie_active` | `max: 0` | Negative cash = payment risk |
| `capitaux_propres` | `max: 0` | Negative equity = insolvency |
| `excedent_brut_exploitation` | `max: 0` | Negative EBITDA = unprofitable operations |
| `resultat_net` | `max: 0` | Loss |

---

## 10. How to Add a New Metric

### Step 1: Identify the inputs

Determine which rubriques you need. They must already exist in `mdl_manifest.json`.

**Example:** Ratio de liquidité générale = Actif circulant / Passif circulant

- Inputs: `actif_circulant`, `passif_circulant`
- Check they exist in `mdl_manifest.json` (or add them first)

### Step 2: Write the formula

Express the calculation in both human and machine formats:

```json
{
  "metric_key": "ratio_liquidite_generale",
  "metric_type": "ratio",
  "display_name": "Ratio de Liquidité Générale",
  "rubrique_keys": ["actif_circulant", "passif_circulant"],
  "formula": "actif_circulant / passif_circulant",
  "result": {
    "op": "divide",
    "left": "actif_circulant",
    "right": "passif_circulant"
  }
}
```

### Step 3: Set output format and direction

```json
  "output_format": "multiple",
  "higher_is_better": true
```

### Step 4: Define thresholds

Research industry norms or accounting best practices:

```json
  "thresholds": {
    "healthy": { "min": 1.5, "label": "Liquidité confortable (> 1.5x)" },
    "warning": { "min": 1.0, "max": 1.5, "label": "Liquidité limitée (1.0-1.5x)" },
    "critical": { "max": 1.0, "label": "Liquidité insuffisante (< 1.0x)" }
  }
```

### Step 5: Enable sector comparison (optional)

```json
  "sector_comparison": true
```

(Requires benchmarks to exist in `benchmarks_bdf.json`)

### Step 6: Add caveats (optional)

```json
  "caveat_if_low_equity": {
    "threshold_cp": 5000,
    "message": "Base de capitaux propres très faible — interprétation du ratio limitée."
  }
```

### Step 7: Validate

Run `python test_smoke.py` — the semantic layer validates:
- All `rubrique_keys` exist
- Expression tree references match `rubrique_keys`
- No circular dependencies

---

## 11. How to Modify an Existing Metric

### Changing thresholds

Edit the `thresholds` block. No code changes needed:

```json
// Before
"healthy": { "max": 1.0, "label": "Endettement maîtrisé (< 1x)" }

// After (more conservative)
"healthy": { "max": 0.8, "label": "Endettement faible (< 0.8x)" }
```

### Changing the formula

Update both `formula` (string) and `result` (tree):

```json
// Before: taux_endettement_brut
"formula": "endettement_brut / capitaux_propres",
"result": {
  "op": "divide",
  "left": "endettement_brut",
  "right": "capitaux_propres"
}

// After: taux_endettement_net
"formula": "(endettement_brut - tresorerie_active) / capitaux_propres",
"result": {
  "op": "divide",
  "left": {
    "op": "subtract",
    "left": "endettement_brut",
    "right": "tresorerie_active"
  },
  "right": "capitaux_propres"
}
```

⚠️ **Important:** Update `rubrique_keys` array to match the new inputs:

```json
"rubrique_keys": ["endettement_brut", "tresorerie_active", "capitaux_propres"]
```

### Renaming a metric_key

Update references in:
- `agent_spec.json` → tool definitions
- `waterfalls.json` → if metric used in cascade logic
- `benchmarks_bdf.json` → if metric has sector benchmarks

---

## 12. Validation & Safety

### Startup validation

The semantic layer runs `_validate_metric_inputs()` on load:

| Check | What it catches |
|---|---|
| `rubrique_keys` field present | Missing declaration |
| Every key in `rubrique_keys` exists in `_fields` | Typo or missing rubrique |
| Keys in `result` tree = keys in `rubrique_keys` | Mismatch between formula and declaration |
| No circular dependencies | Metric A uses Metric B which uses Metric A |

**Example error:**

```
ValidationError: Metric 'taux_endettement_net' declares rubrique_keys 
['endettement_brut', 'capitaux_propres'] but expression tree references 
['endettement_brut', 'tresorerie_active', 'capitaux_propres']
```

### Runtime safety

- Division by zero returns `null` with a caveat
- Negative denominators are flagged (optional caveat)
- All SQL is SELECT-only (inherited from rubrique execution)

---

## 13. Relationship to Other Config Files

```
metrics.json
    │
    ├──→ mdl_manifest.json       rubrique_keys reference calculatedFields
    ├──→ benchmarks_bdf.json     metric_keys have sector quartiles
    ├──→ waterfalls.json         metrics used in waterfall explanations
    └──→ agent_spec.json         query_metric tool uses metric_keys
```

Metrics **depend on** rubriques (bottom-up):
1. Rubriques compile to SQL
2. Metrics evaluate rubrique results
3. Benchmarks compare metrics to sector data

---

## 14. Full Field Reference

### metrics[] entry

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `metric_key` | string | **Yes** | — | Unique identifier (snake_case) |
| `metric_type` | string | **Yes** | — | Currently always `"ratio"` |
| `display_name` | string | **Yes** | — | Human-readable label |
| `rubrique_keys` | string[] | **Yes** | — | Input rubriques (must exist in mdl_manifest) |
| `formula` | string | **Yes** | — | Human-readable formula |
| `result` | object | **Yes** | — | Expression tree for evaluation |
| `output_format` | string | **Yes** | — | `"percentage"` or `"multiple"` |
| `higher_is_better` | bool | **Yes** | — | Direction for threshold interpretation |
| `thresholds` | object | **Yes** | — | Status boundaries |
| `sector_comparison` | bool | No | `false` | Enable BdF benchmarking |
| `sector_specific` | string | No | — | NAF code if metric is sector-specific |
| `note` | string | No | — | Additional context |
| `caveat_if_low_equity` | object | No | — | Warning if CP < threshold |

### result (expression tree node)

| Field | Type | Required | Description |
|---|---|---|---|
| `op` | string | **Yes** | `"divide"`, `"multiply"`, `"add"`, `"subtract"` |
| `left` | string/object | **Yes** | Rubrique_key or nested expression |
| `right` | string/object | **Yes** | Rubrique_key or nested expression |

### thresholds

| Field | Type | Required | Description |
|---|---|---|---|
| `healthy` | object | **Yes** | Healthy zone definition |
| `warning` | object | **Yes** | Warning zone definition |
| `critical` | object | **Yes** | Critical zone definition |

### threshold zone

| Field | Type | Required | Description |
|---|---|---|---|
| `min` | float | No | Inclusive lower bound (omit for -∞) |
| `max` | float | No | Exclusive upper bound (omit for +∞) |
| `label` | string | **Yes** | Human-readable description |

### caveat_if_low_equity

| Field | Type | Required | Description |
|---|---|---|---|
| `threshold_cp` | float | **Yes** | CP threshold below which caveat is shown |
| `message` | string | **Yes** | Warning message |

### rubrique_alerts

```json
"rubrique_alerts": {
  "rubrique_key": {
    "critical": { "min": ..., "max": ..., "label": "..." },
    "warning": { "min": ..., "max": ..., "label": "..." }
  }
}
```

Each rubrique can have `critical` and/or `warning` threshold objects with the same structure as metric thresholds.

---

**Version:** 1.0  
**Last Updated:** 2026-04-05  
**Project:** PCG FEC Agent — Config-driven financial analysis for French accounting
