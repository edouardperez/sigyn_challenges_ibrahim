"""replanner node: revises the plan when a tool errors or returns empty.

Called by the router when:
- A tool returned an error AND replan_count < max_replans
- A tool returned empty results AND replan_on_empty is configured

The replanner sends the original question + error context to Gemini
and asks for a revised plan.
"""

from __future__ import annotations

import json

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from pcg_agent.graph.state import Plan, PlanStep


REPLANNER_SYSTEM_PROMPT = """Tu es un planificateur financier expert. Le plan précédent a rencontré une erreur.
Tu reçois la question originale, les résultats obtenus jusqu'ici, et le contexte d'erreur.

Produis un plan RÉVISÉ en JSON avec les mêmes champs : "reasoning", "steps", "expected_output_type".

RÈGLES :
1. Ne répète pas les étapes qui ont déjà réussi (leurs résultats sont fournis).
2. Corrige l'erreur en essayant une approche alternative.
3. Maximum 4 étapes supplémentaires.
4. JSON valide uniquement — pas de texte avant/après.
"""


def replanner(state: dict, llm: ChatGoogleGenerativeAI) -> dict:
    """Generate a revised plan after an error.

    Args:
        state: Current AgentState as dict.
        llm: Configured Gemini LLM.

    Returns:
        Updated state with new plan and incremented replan_count.
    """
    user_message = state.get("user_message", "")
    error_context = state.get("error_context", "")
    tool_results = state.get("tool_results", [])
    domain_context = state.get("domain_context", {})
    replan_count = state.get("replan_count", 0)

    results_summary = []
    for tr in tool_results:
        if hasattr(tr, "model_dump"):
            results_summary.append(tr.model_dump())
        else:
            results_summary.append(tr)

    context_text = f"""QUESTION ORIGINALE : {user_message}

RÉSULTATS OBTENUS :
{json.dumps(results_summary, ensure_ascii=False, indent=2, default=str)}

ERREUR RENCONTRÉE : {error_context}

CONTEXTE DOMAINE :
{json.dumps(domain_context, ensure_ascii=False, indent=2)}
"""

    messages = [
        SystemMessage(content=REPLANNER_SYSTEM_PROMPT),
        HumanMessage(content=context_text),
    ]

    response = llm.invoke(messages)
    raw = response.content.strip()

    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = lines[1:] if lines[0].startswith("```") else lines
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines)

    try:
        plan_data = json.loads(raw)
    except json.JSONDecodeError:
        plan_data = {
            "reasoning": "Replanning failed — proceeding to synthesis with available data",
            "steps": [],
            "expected_output_type": "text",
        }

    steps = []
    for s in plan_data.get("steps", []):
        steps.append(PlanStep(
            id=s.get("id", f"r{len(steps)+1}"),
            tool=s["tool"],
            args=s.get("args", {}),
            depends_on=s.get("depends_on", []),
        ))

    plan = Plan(
        reasoning=plan_data.get("reasoning", ""),
        steps=steps,
        expected_output_type=plan_data.get("expected_output_type", "text"),
    )

    return {
        "plan": plan,
        "current_step_idx": 0,
        "replan_count": replan_count + 1,
        "error_context": None,
    }
