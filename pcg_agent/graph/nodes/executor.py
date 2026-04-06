"""executor node: runs one step of the plan at a time.

The executor takes the current plan step, dispatches it to the appropriate
tool via the dispatcher, captures the result (or error), and advances
the step index. The router node then decides what to do next.
"""

from __future__ import annotations

import traceback

from pcg_agent.graph.state import ToolResult
from pcg_agent.query_engine.duckdb_engine import FECQueryEngine
from pcg_agent.semantic_layer.mdl_reader import PCGSemanticLayer
from pcg_agent.tools.dispatcher import dispatch


def executor(
    state: dict,
    engine: FECQueryEngine,
    semantic: PCGSemanticLayer,
) -> dict:
    """Execute the current plan step and record the result.

    If the step succeeds, its result is appended to tool_results.
    If it fails, the error is captured so the router can decide
    whether to replan or proceed.
    """
    plan = state.get("plan")
    if plan is None:
        return {"error_context": "No plan available"}

    idx = state.get("current_step_idx", 0)
    steps = plan.steps if hasattr(plan, "steps") else plan.get("steps", [])

    if idx >= len(steps):
        return {}

    step = steps[idx]
    step_id = step.id if hasattr(step, "id") else step.get("id", f"s{idx}")
    tool_name = step.tool if hasattr(step, "tool") else step.get("tool", "")
    args = dict(step.args if hasattr(step, "args") else step.get("args", {}))

    tool_results = list(state.get("tool_results", []))

    # Resolve "$resolve.<step_id>" placeholders — lets get_trend use a prior
    # resolve_concept result without the planner needing to hardcode the key.
    prior_results = {tr.step_id: tr for tr in tool_results if hasattr(tr, "step_id")}
    for k, v in list(args.items()):
        if isinstance(v, str) and v.startswith("$resolve."):
            ref_step_id = v[len("$resolve."):]
            ref = prior_results.get(ref_step_id)
            if ref and ref.result and ref.result.get("matches"):
                args[k] = ref.result["matches"][0]["rubrique_key"]
    alerts = list(state.get("alerts", []))
    sector_positions = list(state.get("sector_positions", []))

    try:
        result_data = dispatch(tool_name, args, engine, semantic)

        if isinstance(result_data, dict):
            if "alerts" in result_data:
                alerts.extend(result_data["alerts"])
            if "sector_position" in result_data:
                sector_positions.append(result_data["sector_position"])

        tool_result = ToolResult(
            step_id=step_id,
            tool=tool_name,
            args=args,
            result=result_data,
        )
    except Exception as e:
        tool_result = ToolResult(
            step_id=step_id,
            tool=tool_name,
            args=args,
            error=f"{type(e).__name__}: {e}",
        )

    tool_results.append(tool_result)

    return {
        "tool_results": tool_results,
        "current_step_idx": idx + 1,
        "alerts": alerts,
        "sector_positions": sector_positions,
        "error_context": tool_result.error,
    }
