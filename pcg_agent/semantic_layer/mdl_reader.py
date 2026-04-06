"""L2/L3 — PCG Semantic Layer: the bridge between rubrique_keys and SQL.

Architecture: dual-path reader over a unified MDL manifest.

Each rubrique in mdl_manifest.json carries two sub-blocks:

    "semantic"   — label, synonyms, description, logic, tags, relationships.
                   Sent to the LLM planner. Never contains SQL or account prefixes.

    "execution"  — macro, include_prefixes, prefix_match_length, etc.
                   Consumed by the SQL builder. Never sent to the LLM.

SEMANTIC PATH (LLM context):
    get_semantic_context()  -> semantic{} blocks for a set of rubrique_keys
    resolve_concept()       -> keyword match → rubrique_keys + semantic context
    build_domain_context()  -> compact planner context (labels, ratios, keys)

EXECUTION PATH (SQL builder):
    build_rubrique_sql()    -> SELECT for one rubrique value
    build_trend_sql()       -> SELECT grouped by period
    build_breakdown_sql()   -> top-N sub-accounts
    compute_metric()        -> declarative expression tree evaluator
    evaluate_alerts()       -> threshold checks
    evaluate_sector()       -> position vs BdF benchmarks
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional


class PCGSemanticLayer:
    """Central semantic layer — single reader over a unified MDL manifest."""

    POLARITY_EXPR: dict[str, str] = {
        "credit_moins_debit": "credit - debit",
        "debit_moins_credit": "debit - credit",
    }

    def __init__(self, config_dir: str | Path):
        self.config_dir = Path(config_dir)

        self._mdl: dict = {}
        self._macros: dict[str, dict] = {}
        self._metrics: list[dict] = []
        self._rubrique_alerts: dict = {}
        self._benchmarks: dict = {}
        self._waterfalls: list[dict] = []
        self._sector_profiles: dict = {}

        # Keyed by rubrique_key — stores the full field dict {semantic{}, execution{}}
        self._fields: dict[str, dict] = {}
        self._metric_index: dict[str, dict] = {}

        self._load_all()

    # ── Loading ──────────────────────────────────────────────────────────

    def _load_all(self) -> None:
        self._load_mdl()
        self._load_metrics()
        self._load_sector_profiles()
        self._validate_metric_inputs()

    def _load_json(self, relative_path: str) -> dict:
        path = self.config_dir / relative_path
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _load_mdl(self) -> None:
        self._mdl = self._load_json("semantic/mdl_manifest.json")
        self._macros = self._mdl["macros"]
        model = self._mdl["models"][0]
        for field in model["calculatedFields"]:
            key = field["rubrique_key"]
            self._fields[key] = field

    def _load_metrics(self) -> None:
        data = self._load_json("metrics/metrics.json")
        self._metrics = data["metrics"]
        self._rubrique_alerts = data.get("rubrique_alerts", {})
        for metric in self._metrics:
            self._metric_index[metric["metric_key"]] = metric

        self._benchmarks = self._load_json("metrics/benchmarks_bdf.json")

        waterfalls_data = self._load_json("metrics/waterfalls.json")
        self._waterfalls = waterfalls_data["waterfalls"]

    def _validate_metric_inputs(self) -> None:
        """Validate rubrique_keys declared in metrics.json against two checks.

        1. Every declared rubrique_key exists in mdl_manifest.json (_fields).
        2. The declared rubrique_keys set matches the keys actually used in the
           result{} expression tree — catches copy-paste drift in either direction.

        Called once at startup so config errors are caught immediately rather
        than silently returning 0.0 at query time.

        Raises:
            ValueError: Lists every violation found.
        """
        errors: list[str] = []
        for metric in self._metrics:
            mk = metric["metric_key"]
            declared: list[str] = metric.get("rubrique_keys", [])

            if not declared:
                errors.append(f"  metric '{mk}' is missing 'rubrique_keys' field")
                continue

            # Check 1: every declared key exists in the manifest
            for rk in declared:
                if rk not in self._fields:
                    errors.append(
                        f"  metric '{mk}': declared rubrique_key '{rk}' "
                        f"not found in mdl_manifest.json"
                    )

            # Check 2: declared set matches what the expression actually uses
            derived = set(self._extract_components(metric["result"]))
            declared_set = set(declared)
            extra = declared_set - derived
            missing = derived - declared_set
            if extra:
                errors.append(
                    f"  metric '{mk}': rubrique_keys declares {sorted(extra)} "
                    f"but expression does not use them"
                )
            if missing:
                errors.append(
                    f"  metric '{mk}': expression uses {sorted(missing)} "
                    f"but rubrique_keys does not declare them"
                )

        if errors:
            raise ValueError(
                "metrics.json has invalid rubrique_keys:\n" + "\n".join(errors)
            )

    def _load_sector_profiles(self) -> None:
        data = self._load_json("ontology/sector_profiles.json")
        self._sector_profiles = data["profiles"]

    # ── SQL Builder — private helpers (EXECUTION PATH only) ──────────────

    def _prefix_condition(
        self,
        prefixes: list[str],
        length: int,
        column: str,
        operator: str,
    ) -> str:
        """Generate: LEFT(column, n) IN ('10','11','12').

        Prefixes come exclusively from the validated JSON config — never from
        user input — so inlining them as SQL literals is safe.
        """
        quoted = ", ".join(f"'{p}'" for p in prefixes)
        return f"LEFT({column}, {length}) {operator} ({quoted})"

    def _solde_condition(self, condition_type: str) -> str:
        """Return the per-row SQL condition for a balance-direction filter.

        Conditions are expressed in absolute debit/credit terms, independent of
        any rubrique's polarity — they describe the natural direction of the
        account balance.

            solde_positive — account has a net debit balance:  (debit - credit) > 0
            solde_negative — account has a net credit balance: (credit - debit) > 0

        Examples:
            512 (banque) debit balance  → solde_positive → trésorerie active
            512 (banque) credit balance → solde_negative → trésorerie passive (overdraft)
            109 (CSNA)   debit balance  → solde_positive → excludes from capitaux propres
        """
        if condition_type == "solde_positive":
            return "(debit - credit) > 0"
        if condition_type == "solde_negative":
            return "(credit - debit) > 0"
        raise ValueError(f"Unknown condition_type: {condition_type!r}")

    def _build_simple(self, exec_spec: dict, macro: str) -> str:
        """Compile a simple rubrique (one CASE WHEN block) from execution spec.

        Supports three layers of filtering on top of the standard include_prefixes:

            conditional_includes  — OR-added to the include condition.
                Each entry is included when its prefix matches AND the per-row
                solde condition is met.

            exclude_prefixes      — static NOT IN, always applied.

            conditional_excludes  — AND NOT applied per entry.
                Each entry is excluded when its prefix matches AND the per-row
                solde condition is met.

        Final CASE WHEN logic:
            (std_includes OR cond_inc_1 OR ...)
            AND [NOT IN static_excludes]
            AND NOT (cond_excl_1_prefix AND cond_excl_1_solde)
            AND NOT (cond_excl_2_prefix AND cond_excl_2_solde) ...
        """
        polarity = self._macros[macro]["polarity"]
        value_expr = self.POLARITY_EXPR[polarity]

        include = exec_spec["include_prefixes"]
        inc_len = exec_spec["prefix_match_length"]
        exclude = exec_spec.get("exclude_prefixes", [])
        exc_len = exec_spec.get("exclude_prefix_match_length", inc_len + 1)

        # ── Build include clause ──────────────────────────────────────────
        inc_cond = self._prefix_condition(include, inc_len, "numero_compte", "IN")

        cond_inc_parts: list[str] = []
        for ci in exec_spec.get("conditional_includes", []):
            ci_len = len(ci["prefixes"][0])
            ci_prefix = self._prefix_condition(ci["prefixes"], ci_len, "numero_compte", "IN")
            ci_solde = self._solde_condition(ci["condition"])
            cond_inc_parts.append(f"({ci_prefix} AND {ci_solde})")

        if cond_inc_parts:
            include_clause = f"({inc_cond} OR {' OR '.join(cond_inc_parts)})"
        else:
            include_clause = inc_cond

        when_clause = include_clause

        # ── Static excludes ───────────────────────────────────────────────
        if exclude:
            exc_cond = self._prefix_condition(exclude, exc_len, "numero_compte", "NOT IN")
            when_clause += f" AND {exc_cond}"

        # ── Conditional excludes ──────────────────────────────────────────
        for ce in exec_spec.get("conditional_excludes", []):
            ce_len = len(ce["prefixes"][0])
            ce_prefix = self._prefix_condition(ce["prefixes"], ce_len, "numero_compte", "IN")
            ce_solde = self._solde_condition(ce["condition"])
            when_clause += f" AND NOT ({ce_prefix} AND {ce_solde})"

        return f"SUM(CASE WHEN {when_clause} THEN {value_expr} ELSE 0 END)"

    def _build_composite(self, parts: list[dict]) -> str:
        """Compile a composite rubrique (multiple CASE WHEN blocks summed).

        Each part may carry an optional 'condition' field:
            solde_positive — row included only when (debit - credit) > 0
            solde_negative — row included only when (credit - debit) > 0
        """
        cases = []
        for part in parts:
            polarity = part["polarity"]
            value_expr = self.POLARITY_EXPR[polarity]
            sign = part.get("sign", "positive")
            condition_type = part.get("condition", "")

            inc_cond = self._prefix_condition(
                part["include_prefixes"],
                part["prefix_match_length"],
                "numero_compte",
                "IN",
            )

            if condition_type:
                solde_cond = self._solde_condition(condition_type)
                case_expr = (
                    f"CASE WHEN {inc_cond} AND {solde_cond} "
                    f"THEN {value_expr} ELSE 0 END"
                )
            else:
                case_expr = f"CASE WHEN {inc_cond} THEN {value_expr} ELSE 0 END"

            if sign == "negative":
                case_expr = f"(-1 * {case_expr})"

            cases.append(case_expr)

        return f"SUM({' + '.join(cases)})"

    def _build_agg_expr(self, rubrique_key: str) -> str:
        """Build the aggregate expression (SUM(...)) for a rubrique.

        Reads exclusively from the execution{} block.
        """
        exec_spec = self._fields[rubrique_key]["execution"]
        macro = exec_spec.get("macro", "solde_passif")
        if macro == "composite":
            return self._build_composite(exec_spec["composite_parts"])
        return self._build_simple(exec_spec, macro)

    def _build_where(
        self,
        exercice: int,
        mois: Optional[int] = None,
        exclude_journals: Optional[list[str]] = None,
    ) -> str:
        """Build the WHERE clause for exercice / mois / journal filters.

        exercice and mois are always validated integers from the dispatcher.
        Journal codes come from config, not user input.
        """
        clauses = [f"exercice = {int(exercice)}"]
        if mois is not None:
            clauses.append(f"mois = {int(mois)}")
        if exclude_journals:
            quoted = ", ".join(f"'{j}'" for j in exclude_journals)
            clauses.append(f"journal_code NOT IN ({quoted})")
        return " AND ".join(clauses)

    # ── SEMANTIC PATH: context for the LLM ───────────────────────────────

    def get_semantic_context(self, rubrique_keys: list[str]) -> list[dict]:
        """Return semantic{} blocks for a list of rubrique_keys.

        Only the semantic sub-block is returned — execution{} is never exposed.
        Used by the planner and synthesizer nodes.
        """
        return [
            {"rubrique_key": key, **self._fields[key]["semantic"]}
            for key in rubrique_keys
            if key in self._fields
        ]

    def resolve_concept(self, query: str) -> list[dict]:
        """Resolve a natural-language query to matching rubrique concepts.

        Searches labels, synonyms, and tags from the semantic{} blocks.
        Returns up to 5 matches sorted by relevance score.
        """
        query_lower = query.lower().strip()
        results = []

        for key, field in self._fields.items():
            sem = field["semantic"]
            score = 0

            label = sem["display_name"].lower()
            if query_lower == label or query_lower == key:
                score = 100
            elif query_lower in label:
                score = 80

            for syn in sem.get("synonyms", []):
                if query_lower == syn.lower():
                    score = max(score, 90)
                elif query_lower in syn.lower() or syn.lower() in query_lower:
                    score = max(score, 70)

            for tag in sem.get("tags", []):
                if query_lower in tag.lower() or tag.lower() in query_lower:
                    score = max(score, 40)

            if sem.get("description"):
                desc_lower = sem["description"].lower()
                for word in query_lower.split():
                    if len(word) > 3 and word in desc_lower:
                        score = max(score, 30)

            if score > 0:
                results.append({
                    "rubrique_key": key,
                    "display_name": sem["display_name"],
                    "score": score,
                    "description": sem.get("description", ""),
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:5]

    def get_concept(self, rubrique_key: str) -> Optional[dict]:
        """Return the semantic{} block for a rubrique_key, or None."""
        field = self._fields.get(rubrique_key)
        return field["semantic"] if field else None

    def build_domain_context(self, naf_code: str = "96.02A") -> dict:
        """Build compact domain context for the LLM planner.

        Gives the planner labels, keys, and relationships — no SQL.
        """
        active = self.get_active_concepts(naf_code)
        disabled = self.get_disabled_concepts(naf_code)

        concepts_for_planner = []
        for key in active:
            field = self._fields.get(key)
            if field:
                sem = field["semantic"]
                concepts_for_planner.append({
                    "rubrique_key": key,
                    "label": sem["display_name"],
                    "synonyms": sem.get("synonyms", []),
                    "domain_category": sem.get("domain_category", ""),
                    "higher_is_better": sem.get("higher_is_better"),
                    "relationships": sem.get("relationships", {}),
                })

        metrics_for_planner = []
        profile = self._sector_profiles.get(naf_code, {})
        for mk in profile.get("key_metrics", []):
            m = self._metric_index.get(mk)
            if m:
                metrics_for_planner.append({
                    "metric_key": mk,
                    "metric_type": m.get("metric_type", "ratio"),
                    "display_name": m["display_name"],
                    "formula": m["formula"],
                    "higher_is_better": m.get("higher_is_better"),
                })

        return {
            "active_concepts": concepts_for_planner,
            "disabled_concepts": disabled,
            "available_metrics": metrics_for_planner,
            "waterfall_keys": [w["waterfall_key"] for w in self._waterfalls],
        }

    # ── EXECUTION PATH: SQL builders ─────────────────────────────────────

    def get_rubrique_expression(self, rubrique_key: str) -> Optional[str]:
        """Return the compiled aggregate expression for a rubrique_key, or None."""
        if rubrique_key not in self._fields:
            return None
        return self._build_agg_expr(rubrique_key)

    def build_rubrique_sql(
        self,
        rubrique_key: str,
        exercice: int,
        mois: Optional[int] = None,
    ) -> str:
        """Build a SELECT query that computes one rubrique value for a period.

        Reads exclusively from the execution{} block. No SQL hardcoded in manifest.
        """
        if rubrique_key not in self._fields:
            raise ValueError(f"Unknown rubrique_key: {rubrique_key}")
        agg_expr = self._build_agg_expr(rubrique_key)
        where = self._build_where(exercice, mois)
        return f"SELECT {agg_expr} AS valeur FROM fec WHERE {where}"

    def build_trend_sql(
        self,
        rubrique_key: str,
        from_year: int,
        to_year: int,
        granularity: str = "annual",
    ) -> str:
        """Build SQL for a rubrique's trend over multiple periods."""
        if rubrique_key not in self._fields:
            raise ValueError(f"Unknown rubrique_key: {rubrique_key}")
        agg_expr = self._build_agg_expr(rubrique_key)
        where = f"WHERE exercice BETWEEN {int(from_year)} AND {int(to_year)}"
        if granularity == "monthly":
            return (
                f"SELECT exercice, mois, {agg_expr} AS valeur "
                f"FROM fec {where} "
                f"GROUP BY exercice, mois "
                f"ORDER BY exercice, mois"
            )
        return (
            f"SELECT exercice, {agg_expr} AS valeur "
            f"FROM fec {where} "
            f"GROUP BY exercice "
            f"ORDER BY exercice"
        )

    def build_breakdown_sql(
        self,
        rubrique_key: str,
        exercice: int,
        top_n: int = 10,
    ) -> str:
        """Build SQL to decompose a rubrique into its sub-accounts (top N)."""
        field = self._fields.get(rubrique_key)
        if field is None:
            raise ValueError(f"Unknown rubrique_key: {rubrique_key}")

        exec_spec = field["execution"]
        macro = exec_spec.get("macro", "solde_passif")

        if macro == "composite":
            first_part = exec_spec["composite_parts"][0]
            polarity = first_part["polarity"]
            include_prefixes = first_part["include_prefixes"]
            prefix_match_length = first_part["prefix_match_length"]
            exclude_prefixes: list[str] = []
            exclude_prefix_match_length = prefix_match_length + 1
        else:
            polarity = self._macros[macro]["polarity"]
            include_prefixes = exec_spec["include_prefixes"]
            prefix_match_length = exec_spec["prefix_match_length"]
            exclude_prefixes = exec_spec.get("exclude_prefixes", [])
            exclude_prefix_match_length = exec_spec.get(
                "exclude_prefix_match_length", prefix_match_length + 1
            )

        amount_expr = f"SUM({self.POLARITY_EXPR[polarity]})"
        prefix_cond = self._prefix_condition(
            include_prefixes, prefix_match_length, "numero_compte", "IN"
        )
        where_clause = f"exercice = {int(exercice)} AND {prefix_cond}"

        if exclude_prefixes:
            exc_cond = self._prefix_condition(
                exclude_prefixes, exclude_prefix_match_length, "numero_compte", "NOT IN"
            )
            where_clause += f" AND {exc_cond}"

        return (
            f"SELECT numero_compte, libelle_compte, "
            f"{amount_expr} AS montant "
            f"FROM fec "
            f"WHERE {where_clause} "
            f"GROUP BY numero_compte, libelle_compte "
            f"HAVING ABS({amount_expr}) > 0.01 "
            f"ORDER BY ABS({amount_expr}) DESC "
            f"LIMIT {top_n}"
        )

    # ── EXECUTION PATH: metric computation ───────────────────────────────

    def get_metric_def(self, metric_key: str) -> Optional[dict]:
        """Return the full metric definition dict, or None."""
        return self._metric_index.get(metric_key)

    def _extract_components(self, expr: str | dict) -> list[str]:
        """Walk a result expression tree and collect all rubrique_keys it references.

        Leaf nodes are plain strings (rubrique_keys).
        Branch nodes are dicts with "op", "left", "right".

        Derived directly from the expression — can never drift out of sync.
        """
        if isinstance(expr, str):
            return [expr]
        keys: list[str] = []
        if "left" in expr:
            keys.extend(self._extract_components(expr["left"]))
        if "right" in expr:
            keys.extend(self._extract_components(expr["right"]))
        seen: set[str] = set()
        return [k for k in keys if not (k in seen or seen.add(k))]  # type: ignore[func-returns-value]

    def get_metric_components(self, metric_key: str) -> list[str]:
        """Return the rubrique_keys required to compute this metric.

        Reads the explicit 'rubrique_keys' field declared in metrics.json.
        Consistency with the result{} expression is enforced at startup by
        _validate_metric_inputs(), so this list is always correct.
        """
        m = self._metric_index.get(metric_key)
        if m is None:
            return []
        return m["rubrique_keys"]

    def _eval_expr(
        self, expr: str | dict, rubrique_values: dict[str, float]
    ) -> float:
        """Recursively evaluate a result expression tree against fetched values.

        Leaf:   a plain string → rubrique_key → looked up in rubrique_values.
        Branch: { "op": "...", "left": expr, "right": expr }

        Supported ops:
            divide   — left / right  (raises ZeroDivisionError when right ≈ 0)
            add      — left + right
            subtract — left - right
            multiply — left * right

        All values come from pre-fetched DuckDB results — never from user input.
        """
        if isinstance(expr, str):
            return rubrique_values.get(expr, 0.0)

        op = expr["op"]
        left = self._eval_expr(expr["left"], rubrique_values)
        right = self._eval_expr(expr["right"], rubrique_values)

        if op == "divide":
            if abs(right) < 0.01:
                raise ZeroDivisionError
            return left / right
        if op == "add":
            return left + right
        if op == "subtract":
            return left - right
        if op == "multiply":
            return left * right

        raise ValueError(f"Unknown expression op: {op!r}")

    def compute_metric(
        self, metric_key: str, rubrique_values: dict[str, float]
    ) -> Optional[float]:
        """Compute a metric value from pre-fetched rubrique values.

        Evaluates the result{} expression tree declared in metrics.json.
        No formula logic is hardcoded in Python — all metrics use the same
        recursive evaluator.

        Args:
            metric_key: The metric to compute.
            rubrique_values: Dict of rubrique_key -> float value.

        Returns:
            The computed value, or None if a divide-by-zero occurs.
        """
        m = self._metric_index.get(metric_key)
        if m is None:
            raise ValueError(f"Unknown metric_key: {metric_key!r}")
        try:
            return self._eval_expr(m["result"], rubrique_values)
        except ZeroDivisionError:
            return None

    # ── EXECUTION PATH: alert evaluation ─────────────────────────────────

    def evaluate_rubrique_alert(
        self, rubrique_key: str, value: float
    ) -> list[dict]:
        """Check if a rubrique value triggers any threshold alerts."""
        alerts = []
        rules = self._rubrique_alerts.get(rubrique_key, {})

        for level, rule in rules.items():
            triggered = False
            if "max" in rule and value <= rule["max"]:
                triggered = True
            if "min" in rule and value >= rule["min"]:
                triggered = True
            if triggered:
                alerts.append({
                    "level": level,
                    "rubrique_key": rubrique_key,
                    "value": value,
                    "message": rule["label"],
                })

        return alerts

    def evaluate_metric_alert(self, metric_key: str, value: float) -> dict:
        """Evaluate a metric against its thresholds. Returns status + label."""
        m = self._metric_index.get(metric_key)
        if m is None:
            return {"status": "unknown", "label": "Métrique inconnue"}

        thresholds = m.get("thresholds", {})
        for level in ["critical", "warning", "healthy"]:
            t = thresholds.get(level, {})
            in_range = True
            if "min" in t and value < t["min"]:
                in_range = False
            if "max" in t and value > t["max"]:
                in_range = False
            if in_range and t:
                return {"status": level, "label": t["label"]}

        return {"status": "unknown", "label": "Hors seuils définis"}

    def evaluate_metric_caveats(
        self, metric_key: str, rubrique_values: dict[str, float]
    ) -> list[str]:
        """Return contextual caveats for a metric (e.g. low equity warning)."""
        m = self._metric_index.get(metric_key)
        if m is None:
            return []

        caveats = []
        caveat_cfg = m.get("caveat_if_low_equity")
        if caveat_cfg:
            cp = rubrique_values.get("capitaux_propres", 0)
            if cp < caveat_cfg["threshold_cp"]:
                caveats.append(caveat_cfg["message"])
        return caveats

    # ── EXECUTION PATH: sector comparison ────────────────────────────────

    def _resolve_sector(self, naf_code: str) -> Optional[dict]:
        """Resolve a NAF code to its BdF sector data.

        Tries progressively broader matches: full code (e.g. '96.02A'),
        5-char class (e.g. '96.02'), then 2-char division (e.g. '96').
        """
        sectors = self._benchmarks.get("sectors", {})
        for key in (naf_code, naf_code[:5], naf_code[:2]):
            if key in sectors:
                return sectors[key]
        return None

    def get_sector_benchmark(
        self, metric_key: str, naf_code: str = "96.02A"
    ) -> Optional[dict]:
        """Return BdF benchmark data for a metric in a given sector."""
        sector = self._resolve_sector(naf_code)
        if sector is None:
            return None
        return sector.get("metrics", {}).get(metric_key)

    def get_benchmark_methodology(self) -> dict:
        """Return BdF benchmark methodology context for LLM synthesis."""
        return self._benchmarks.get("methodology", {})

    def evaluate_sector_position(
        self, metric_key: str, value: float, naf_code: str = "96.02A"
    ) -> dict:
        """Position a metric value against BdF sector benchmarks.

        Returns positioning data enriched with BdF methodology context
        (ratio name, formula, comparison nuance) so the synthesizer LLM
        can explain differences between FEC-derived metrics and BdF benchmarks.
        """
        benchmark = self.get_sector_benchmark(metric_key, naf_code)
        if benchmark is None:
            return {"position": "no_data", "message": "Pas de benchmark disponible"}

        q1 = benchmark["q1"]
        median = benchmark["mediane"]
        q3 = benchmark["q3"]

        if value <= q1:
            position = "below_q1"
        elif value <= median:
            position = "q1_to_median"
        elif value <= q3:
            position = "median_to_q3"
        else:
            position = "above_q3"

        result = {
            "position": position,
            "value": value,
            "q1": q1,
            "mediane": median,
            "q3": q3,
            "unit": benchmark.get("unit", "multiple"),
        }

        if "bdf_ratio" in benchmark:
            result["bdf_ratio"] = benchmark["bdf_ratio"]
        if "bdf_formula" in benchmark:
            result["bdf_formula"] = benchmark["bdf_formula"]
        for key in (
            "n_entreprises", "year", "bdf_formula",
            "our_computation", "bdf_computation", "ecarts", "also_see",
        ):
            if key in benchmark:
                result[key] = benchmark[key]
        if benchmark.get("approximate_mapping") is False:
            result["approximate_mapping"] = False

        return result

    # ── Accessors ─────────────────────────────────────────────────────────

    def get_all_rubrique_keys(self) -> list[str]:
        """Return all rubrique_keys defined in the MDL manifest."""
        return list(self._fields.keys())

    def get_active_concepts(self, naf_code: str = "96.02A") -> list[str]:
        """Return rubrique_keys active for a given sector."""
        profile = self._sector_profiles.get(naf_code, {})
        return profile.get("active_concepts", self.get_all_rubrique_keys())

    def get_disabled_concepts(self, naf_code: str = "96.02A") -> dict:
        """Return disabled concepts with reasons for a given sector."""
        profile = self._sector_profiles.get(naf_code, {})
        return profile.get("disabled_concepts", {})

    def get_sector_profile(self, naf_code: str = "96.02A") -> Optional[dict]:
        """Return the full sector profile."""
        return self._sector_profiles.get(naf_code)

    def get_waterfall_def(self, waterfall_key: str) -> Optional[dict]:
        """Return a waterfall definition by key."""
        for wf in self._waterfalls:
            if wf["waterfall_key"] == waterfall_key:
                return wf
        return None

    def get_view(self, view_name: str) -> Optional[dict]:
        """Return a view definition (grouped rubrique_keys)."""
        for view in self._mdl.get("views", []):
            if view["name"] == view_name:
                return view
        return None

    # ── Debug helper ──────────────────────────────────────────────────────

    def explain_sql(self, rubrique_key: str, exercice: int = 2024) -> dict:
        """Return a debug breakdown of how a rubrique compiles to SQL."""
        field = self._fields.get(rubrique_key)
        if field is None:
            raise ValueError(f"Unknown rubrique_key: {rubrique_key!r}")
        exec_spec = field["execution"]
        sql = self.build_rubrique_sql(rubrique_key, exercice)
        return {
            "rubrique_key": rubrique_key,
            "macro": exec_spec.get("macro"),
            "include_prefixes": exec_spec.get("include_prefixes"),
            "exclude_prefixes": exec_spec.get("exclude_prefixes"),
            "compiled_sql": sql,
        }
