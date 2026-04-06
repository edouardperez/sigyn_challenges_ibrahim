"""Tool dispatcher: routes tool calls to the right implementation with security checks.

The executor node calls dispatch() for each step in the plan.
This module validates arguments, checks security rules, and calls
the appropriate function from the semantic layer or specialized tool modules.
"""

from __future__ import annotations

import re
from typing import Any

from pcg_agent.query_engine.duckdb_engine import FECQueryEngine
from pcg_agent.semantic_layer.mdl_reader import PCGSemanticLayer
from pcg_agent.tools.waterfall import compute_waterfall
from pcg_agent.tools.sector_compare import compare_sector


BLOCK_PATTERNS = [
    "DROP", "DELETE", "INSERT", "UPDATE", "TRUNCATE", "UNION SELECT", "--", "/*"
]


def _security_check(sql: str) -> None:
    """Reject SQL containing dangerous patterns."""
    sql_upper = sql.upper()
    for pattern in BLOCK_PATTERNS:
        if pattern.upper() in sql_upper:
            raise SecurityError(f"Blocked SQL pattern detected: {pattern}")


class SecurityError(Exception):
    pass


def dispatch(
    tool_name: str,
    args: dict[str, Any],
    engine: FECQueryEngine,
    semantic: PCGSemanticLayer,
) -> dict[str, Any]:
    """Route a tool call to the correct implementation.

    Args:
        tool_name: Name of the tool to execute (from the plan).
        args: Arguments dict (from the plan step).
        engine: The DuckDB query engine with FEC loaded.
        semantic: The semantic layer for SQL building / concept resolution.

    Returns:
        Dict with the tool's result data.
    """
    if tool_name == "resolve_concept":
        return _resolve_concept(args, semantic)
    elif tool_name == "query_rubrique":
        return _query_rubrique(args, engine, semantic)
    elif tool_name == "query_metric":
        return _query_metric(args, engine, semantic)
    elif tool_name == "get_trend":
        return _get_trend(args, engine, semantic)
    elif tool_name == "get_breakdown":
        return _get_breakdown(args, engine, semantic)
    elif tool_name == "get_waterfall":
        return _get_waterfall(args, engine, semantic)
    elif tool_name == "compare_sector":
        return _compare_sector(args, engine, semantic)
    elif tool_name == "get_sig":
        return _get_sig(args, engine, semantic)
    else:
        raise ValueError(f"Unknown tool: {tool_name}")


def _resolve_concept(args: dict, semantic: PCGSemanticLayer) -> dict:
    query = args["query"]
    matches = semantic.resolve_concept(query)
    return {"matches": matches}


def _query_rubrique(
    args: dict, engine: FECQueryEngine, semantic: PCGSemanticLayer
) -> dict:
    rubrique_key = args["rubrique_key"]
    exercice = args["exercice"]
    mois = args.get("mois")

    sql = semantic.build_rubrique_sql(rubrique_key, exercice, mois)
    _security_check(sql)

    row = engine.fetch_one(sql)
    value = row.get("valeur", 0.0)
    if value is None:
        value = 0.0

    alerts = semantic.evaluate_rubrique_alert(rubrique_key, value)

    concept = semantic.get_concept(rubrique_key)
    label = concept["display_name"] if concept else rubrique_key

    return {
        "rubrique_key": rubrique_key,
        "label": label,
        "exercice": exercice,
        "mois": mois,
        "value": float(value),
        "alerts": alerts,
    }


def _query_metric(
    args: dict, engine: FECQueryEngine, semantic: PCGSemanticLayer
) -> dict:
    metric_key = args["metric_key"]
    exercice = args["exercice"]

    component_keys = semantic.get_metric_components(metric_key)
    rubrique_values: dict[str, float] = {}

    for rk in component_keys:
        sql = semantic.build_rubrique_sql(rk, exercice)
        _security_check(sql)
        row = engine.fetch_one(sql)
        val = row.get("valeur", 0.0)
        rubrique_values[rk] = float(val) if val is not None else 0.0

    metric_value = semantic.compute_metric(metric_key, rubrique_values)
    metric_def = semantic.get_metric_def(metric_key)
    status = (
        semantic.evaluate_metric_alert(metric_key, metric_value)
        if metric_value is not None
        else {"status": "error", "label": "Division par zéro (dénominateur nul)"}
    )
    caveats = semantic.evaluate_metric_caveats(metric_key, rubrique_values)

    return {
        "metric_key": metric_key,
        "metric_type": metric_def.get("metric_type", "ratio") if metric_def else "ratio",
        "display_name": metric_def["display_name"] if metric_def else metric_key,
        "formula": metric_def["formula"] if metric_def else "",
        "exercice": exercice,
        "value": metric_value,
        "output_format": metric_def.get("output_format", "multiple") if metric_def else "multiple",
        "components": rubrique_values,
        "status": status,
        "caveats": caveats,
    }


def _get_trend(
    args: dict, engine: FECQueryEngine, semantic: PCGSemanticLayer
) -> dict:
    rubrique_key = args["rubrique_key"]
    from_year = args["from_year"]
    to_year = args["to_year"]
    granularity = args.get("granularity", "annual")

    sql = semantic.build_trend_sql(rubrique_key, from_year, to_year, granularity)
    _security_check(sql)
    rows = engine.fetch_all(sql)

    concept = semantic.get_concept(rubrique_key)
    label = concept["display_name"] if concept else rubrique_key

    return {
        "rubrique_key": rubrique_key,
        "label": label,
        "from_year": from_year,
        "to_year": to_year,
        "granularity": granularity,
        "data": rows,
        "unit": "EUR",
    }


def _get_breakdown(
    args: dict, engine: FECQueryEngine, semantic: PCGSemanticLayer
) -> dict:
    rubrique_key = args["rubrique_key"]
    exercice = args["exercice"]
    top_n = args.get("top_n", 10)

    sql = semantic.build_breakdown_sql(rubrique_key, exercice, top_n)
    _security_check(sql)
    rows = engine.fetch_all(sql)

    concept = semantic.get_concept(rubrique_key)
    label = concept["display_name"] if concept else rubrique_key

    return {
        "rubrique_key": rubrique_key,
        "label": label,
        "exercice": exercice,
        "accounts": rows,
    }


def _get_waterfall(
    args: dict, engine: FECQueryEngine, semantic: PCGSemanticLayer
) -> dict:
    return compute_waterfall(
        waterfall_key=args["waterfall_key"],
        exercice=args["exercice"],
        include_cca_as_qfp=args.get("include_cca_as_qfp", False),
        engine=engine,
        semantic=semantic,
    )


def _compare_sector(
    args: dict, engine: FECQueryEngine, semantic: PCGSemanticLayer
) -> dict:
    return compare_sector(
        metric_key=args["metric_key"],
        exercice=args["exercice"],
        naf_code=args.get("naf_code", "96.02A"),
        engine=engine,
        semantic=semantic,
    )


def _get_sig(
    args: dict, engine: FECQueryEngine, semantic: PCGSemanticLayer
) -> dict:
    """Compute the SIG (Soldes Intermediaires de Gestion)."""
    exercice = args["exercice"]
    view = semantic.get_view("SIG_simplifie")
    if view is None:
        raise ValueError("SIG view not found in MDL manifest")

    results = []
    for rk in view["rubrique_keys"]:
        sql = semantic.build_rubrique_sql(rk, exercice)
        _security_check(sql)
        row = engine.fetch_one(sql)
        val = row.get("valeur", 0.0)
        if val is None:
            val = 0.0

        concept = semantic.get_concept(rk)
        label = concept["display_name"] if concept else rk

        results.append({
            "rubrique_key": rk,
            "label": label,
            "value": float(val),
        })

    return {
        "view_name": view["displayName"],
        "exercice": exercice,
        "items": results,
    }
