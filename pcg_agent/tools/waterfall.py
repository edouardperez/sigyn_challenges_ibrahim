"""Waterfall tool: builds a multi-rubrique cascade with computed subtotals.

A waterfall shows how financial aggregates build up step by step.
For example: CP -> + CCA -> = Resources -> Emprunts -> + CBC -> = Dette brute -> etc.
"""

from __future__ import annotations

from typing import Any

from pcg_agent.query_engine.duckdb_engine import FECQueryEngine
from pcg_agent.semantic_layer.mdl_reader import PCGSemanticLayer


def compute_waterfall(
    waterfall_key: str,
    exercice: int,
    include_cca_as_qfp: bool,
    engine: FECQueryEngine,
    semantic: PCGSemanticLayer,
) -> dict[str, Any]:
    """Execute a waterfall cascade, computing each rubrique and assembling subtotals.

    Each section in the waterfall has steps. Steps with a rubrique_key get their
    value from DuckDB. Steps with operator "subtotal" or "result" are computed
    from the preceding steps. Conditional steps (like CCA as quasi-FP) are
    included or zeroed based on user choice.
    """
    wf_def = semantic.get_waterfall_def(waterfall_key)
    if wf_def is None:
        raise ValueError(f"Unknown waterfall_key: {waterfall_key}")

    rubrique_cache: dict[str, float] = {}
    sections_result: list[dict] = []

    for section in wf_def["sections"]:
        running = 0.0
        steps_result: list[dict] = []

        for step in section["steps"]:
            operator = step.get("operator", "base")

            if "rubrique_key" in step:
                rk = step["rubrique_key"]
                is_conditional = step.get("conditional", False)

                if is_conditional and not include_cca_as_qfp:
                    value = 0.0
                else:
                    if rk not in rubrique_cache:
                        sql = semantic.build_rubrique_sql(rk, exercice)
                        row = engine.fetch_one(sql)
                        val = row.get("valeur", 0.0)
                        rubrique_cache[rk] = float(val) if val is not None else 0.0
                    value = rubrique_cache[rk]

                if operator == "base":
                    running = value
                elif operator == "add":
                    running += value
                elif operator == "subtract":
                    running -= value

                steps_result.append({
                    "label": step["label"],
                    "rubrique_key": rk,
                    "value": value,
                    "operator": operator,
                    "conditional": is_conditional,
                })

            elif "ref" in step:
                ref_key = step["ref"]
                value = rubrique_cache.get(ref_key, 0.0)

                if operator == "base":
                    running = value
                elif operator == "add":
                    running += value
                elif operator == "subtract":
                    running -= value

                steps_result.append({
                    "label": step["label"],
                    "ref": ref_key,
                    "value": value,
                    "operator": operator,
                })

            elif operator in ("subtotal", "result"):
                steps_result.append({
                    "label": step["label"],
                    "value": running,
                    "operator": operator,
                    "highlight": step.get("highlight", False),
                })
                subtotal_key = _infer_key_from_label(step["label"])
                if subtotal_key:
                    rubrique_cache[subtotal_key] = running

        sections_result.append({
            "section_label": section["section_label"],
            "steps": steps_result,
        })

    return {
        "waterfall_key": waterfall_key,
        "display_name": wf_def["display_name"],
        "exercice": exercice,
        "include_cca_as_qfp": include_cca_as_qfp,
        "sections": sections_result,
    }


def _infer_key_from_label(label: str) -> str | None:
    """Try to map subtotal labels to rubrique_keys for cross-section references."""
    mapping = {
        "endettement brut": "endettement_brut",
        "endettement net": "endettement_net",
        "trésorerie active": "tresorerie_active",
        "ressources propres": "ressources_propres_elargies",
    }
    label_lower = label.lower()
    for pattern, key in mapping.items():
        if pattern in label_lower:
            return key
    return None
