"""LangGraph StateGraph wiring: connects all nodes with conditional edges.

The graph flow:
  START -> context_builder -> planner -> executor -> router
  router -> executor       (more steps remaining)
  router -> replanner      (error + replans left)
  router -> synthesizer    (all steps done or max replans reached)
  replanner -> executor    (revised plan)
  synthesizer -> END

Each node is a function that reads/writes the shared AgentState dict.
The "router" is a conditional edge function -- it inspects the state
and returns the name of the next node.
"""

from __future__ import annotations

import json
from functools import partial
from pathlib import Path

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END

from pcg_agent.graph.state import AgentState
from pcg_agent.query_engine.duckdb_engine import FECQueryEngine
from pcg_agent.semantic_layer.mdl_reader import PCGSemanticLayer
from pcg_agent.graph.nodes.context_builder import context_builder
from pcg_agent.graph.nodes.planner import planner
from pcg_agent.graph.nodes.executor import executor
from pcg_agent.graph.nodes.replanner import replanner
from pcg_agent.graph.nodes.synthesizer import synthesizer


def _router(state: dict) -> str:
    """Conditional edge: decide where to go after the executor.

    Returns the name of the next node:
    - "executor"    if there are more steps to run
    - "replanner"   if there was an error and we haven't hit max replans
    - "synthesizer" if all steps are done or we've exhausted replans
    """
    plan = state.get("plan")
    idx = state.get("current_step_idx", 0)
    error = state.get("error_context")
    replan_count = state.get("replan_count", 0)
    agent_spec = state.get("agent_spec", {})
    max_replans = agent_spec.get("planner", {}).get("max_replans", 2)

    if plan is None:
        return "synthesizer"

    total_steps = len(plan.steps) if hasattr(plan, "steps") else len(plan.get("steps", []))

    if error and replan_count < max_replans:
        return "replanner"

    if idx < total_steps:
        return "executor"

    return "synthesizer"


def build_graph(
    engine: FECQueryEngine,
    semantic: PCGSemanticLayer,
    llm: ChatGoogleGenerativeAI,
    agent_spec: dict,
) -> StateGraph:
    """Build and compile the LangGraph StateGraph.

    We use functools.partial to inject dependencies (engine, semantic, llm)
    into each node function, so they all have access to shared resources
    without passing them through the state.

    Args:
        engine: DuckDB query engine with FEC loaded.
        semantic: PCG semantic layer.
        llm: Configured Gemini LLM.
        agent_spec: Agent specification dict.

    Returns:
        A compiled LangGraph that can be invoked with an AgentState dict.
    """
    graph = StateGraph(AgentState)

    graph.add_node("context_builder", partial(context_builder, semantic=semantic))
    graph.add_node("planner", partial(planner, llm=llm))
    graph.add_node("executor", partial(executor, engine=engine, semantic=semantic))
    graph.add_node("replanner", partial(replanner, llm=llm))
    graph.add_node("synthesizer", partial(synthesizer, llm=llm))

    graph.set_entry_point("context_builder")
    graph.add_edge("context_builder", "planner")
    graph.add_edge("planner", "executor")
    graph.add_conditional_edges("executor", _router, {
        "executor": "executor",
        "replanner": "replanner",
        "synthesizer": "synthesizer",
    })
    graph.add_edge("replanner", "executor")
    graph.add_edge("synthesizer", END)

    return graph.compile()


def load_agent_spec(config_dir: str | Path) -> dict:
    """Load agent_spec.json from the config directory."""
    path = Path(config_dir) / "agent_spec.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)
