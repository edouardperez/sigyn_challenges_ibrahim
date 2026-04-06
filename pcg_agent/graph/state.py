"""AgentState and supporting models for the LangGraph runtime.

LangGraph requires TypedDict for the graph state (not Pydantic BaseModel).
Supporting data classes (Plan, PlanStep, ToolResult) stay as Pydantic models
since they're serialized/deserialized but not used as the graph's state type.
"""

from __future__ import annotations

from typing import Any, Optional
from typing_extensions import TypedDict

from pydantic import BaseModel


class PlanStep(BaseModel):
    """A single step in the agent's execution plan."""

    id: str
    tool: str
    args: dict[str, Any] = {}
    depends_on: list[str] = []


class Plan(BaseModel):
    """The planner's output: a structured execution plan."""

    reasoning: str = ""
    steps: list[PlanStep] = []
    expected_output_type: str = "text"


class ToolResult(BaseModel):
    """Result from executing one tool/step."""

    step_id: str
    tool: str
    args: dict[str, Any] = {}
    result: Any = None
    error: Optional[str] = None
    alerts: list[dict] = []


class AgentState(TypedDict, total=False):
    """The full state that passes through all LangGraph nodes.

    TypedDict is required by LangGraph's StateGraph. Each node returns
    a partial dict with only the keys it wants to update; LangGraph
    merges them into the shared state automatically.
    """

    # Inputs
    session_id: str
    user_message: str
    chat_history: list[dict]

    # Config
    agent_spec: dict
    company_profile: dict
    sector_profile: dict

    # Semantic context
    domain_context: dict
    relevant_concepts: list[dict]

    # Runtime
    plan: Optional[Plan]
    current_step_idx: int
    tool_results: list[ToolResult]
    replan_count: int
    error_context: Optional[str]

    # Output
    response_blocks: list[dict]
    final_answer: Optional[str]
    alerts: list[dict]
    sector_positions: list[dict]
