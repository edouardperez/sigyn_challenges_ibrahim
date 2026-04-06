"""Sector comparison tool: positions a metric against BdF benchmarks.

The Banque de France publishes sector-level financial metrics (Q1, median, Q3)
for each NAF code. This tool computes the company's metric value and positions
it against the sector distribution.
"""

from __future__ import annotations

from typing import Any

from pcg_agent.query_engine.duckdb_engine import FECQueryEngine
from pcg_agent.semantic_layer.mdl_reader import PCGSemanticLayer


def compare_sector(
    metric_key: str,
    exercice: int,
    naf_code: str,
    engine: FECQueryEngine,
    semantic: PCGSemanticLayer,
) -> dict[str, Any]:
    """Compute a metric and compare it to BdF sector benchmarks.

    Steps:
    1. Fetch all rubrique components needed for the metric
    2. Compute the metric value via the declarative expression evaluator
    3. Position it against Q1/median/Q3 from benchmarks_bdf.json
    4. Add any caveats (e.g. low equity warning)
    """
    if naf_code == "auto":
        naf_code = "96.02A"

    component_keys = semantic.get_metric_components(metric_key)
    rubrique_values: dict[str, float] = {}

    for rk in component_keys:
        sql = semantic.build_rubrique_sql(rk, exercice)
        row = engine.fetch_one(sql)
        val = row.get("valeur", 0.0)
        rubrique_values[rk] = float(val) if val is not None else 0.0

    metric_value = semantic.compute_metric(metric_key, rubrique_values)
    metric_def = semantic.get_metric_def(metric_key)

    if metric_value is None:
        return {
            "metric_key": metric_key,
            "display_name": metric_def["display_name"] if metric_def else metric_key,
            "exercice": exercice,
            "error": "Division par zéro (dénominateur nul)",
            "components": rubrique_values,
        }

    position = semantic.evaluate_sector_position(metric_key, metric_value, naf_code)
    caveats = semantic.evaluate_metric_caveats(metric_key, rubrique_values)
    status = semantic.evaluate_metric_alert(metric_key, metric_value)

    sector_profile = semantic.get_sector_profile(naf_code)
    maturity_warning = None
    if sector_profile and "maturity_warning" in sector_profile:
        maturity_warning = sector_profile["maturity_warning"]["message"]

    return {
        "metric_key": metric_key,
        "metric_type": metric_def.get("metric_type", "ratio") if metric_def else "ratio",
        "display_name": metric_def["display_name"] if metric_def else metric_key,
        "exercice": exercice,
        "naf_code": naf_code,
        "value": metric_value,
        "output_format": metric_def.get("output_format", "multiple") if metric_def else "multiple",
        "components": rubrique_values,
        "status": status,
        "sector_position": position,
        "caveats": caveats,
        "maturity_warning": maturity_warning,
    }
