"""context_builder node: prepares semantic context for the planner.

This is the first node in the graph. It:
1. Resolves concepts mentioned in the user's message via the MDL semantic path
2. Loads the sector profile (active/disabled concepts)
3. Builds a compact domain_context that the planner uses to create a plan

The planner never sees SQL, account prefixes, or execution details —
only labels, keys, synonyms, and relationships from the semantic{} blocks.
"""

from __future__ import annotations

from pcg_agent.graph.state import AgentState
from pcg_agent.semantic_layer.mdl_reader import PCGSemanticLayer


def context_builder(state: dict, semantic: PCGSemanticLayer) -> dict:
    """Build domain context from the user message and sector profile.

    Args:
        state: Current AgentState as a dict.
        semantic: The loaded semantic layer.

    Returns:
        Dict of state updates (domain_context, relevant_concepts, etc.)
    """
    user_message = state.get("user_message", "")
    company_profile = state.get("company_profile", {})
    naf_code = company_profile.get("naf_code", "96.02A")

    relevant_concepts = semantic.resolve_concept(user_message)

    for word in user_message.split():
        if len(word) > 3:
            extra = semantic.resolve_concept(word)
            for match in extra:
                if match["rubrique_key"] not in [
                    r["rubrique_key"] for r in relevant_concepts
                ]:
                    relevant_concepts.append(match)

    relevant_concepts.sort(key=lambda x: x["score"], reverse=True)
    relevant_concepts = relevant_concepts[:5]

    relevant_keys = [r["rubrique_key"] for r in relevant_concepts]
    relevant_semantic = semantic.get_semantic_context(relevant_keys)

    domain_context = semantic.build_domain_context(naf_code)
    sector_profile = semantic.get_sector_profile(naf_code) or {}

    return {
        "domain_context": domain_context,
        "relevant_concepts": relevant_concepts,
        "relevant_semantic": relevant_semantic,
        "sector_profile": sector_profile,
    }
