"""planner node: uses Gemini to produce a JSON execution plan.

The planner receives:
- The user's question
- Domain context (concept labels, ratios, relationships -- no SQL)
- Tool schemas from agent_spec
- Chat history

It outputs a structured Plan with steps referencing rubrique_keys and tool names.
The LLM never writes SQL -- it only says "use query_rubrique with key X for year Y".
"""

from __future__ import annotations

import json

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from pcg_agent.graph.state import Plan, PlanStep


PLANNER_SYSTEM_PROMPT = """Tu es un planificateur financier expert en comptabilité française (PCG).
Tu reçois une question utilisateur et un contexte de domaine.

Tu dois produire un plan d'exécution en JSON avec les champs :
- "reasoning": explication courte de ta stratégie
- "steps": liste d'étapes, chacune avec "id", "tool", "args", et optionnellement "depends_on"
- "expected_output_type": le type de bloc de réponse principal attendu

OUTILS DISPONIBLES :
- resolve_concept: {"query": "terme ambigu"} → résout en rubrique_key
- query_rubrique: {"rubrique_key": "...", "exercice": N, "mois": N (optionnel)} → valeur brute
- query_metric: {"metric_key": "...", "exercice": N} → métrique (ratio, marge, solde) + seuils + secteur
- get_trend: {"rubrique_key": "...", "from_year": N, "to_year": N, "granularity": "annual|monthly"} → évolution
- get_breakdown: {"rubrique_key": "...", "exercice": N, "top_n": N} → sous-comptes
- get_waterfall: {"waterfall_key": "...", "exercice": N, "include_cca_as_qfp": bool} → cascade
- compare_sector: {"metric_key": "...", "exercice": N} → positionnement BdF
- get_sig: {"exercice": N} → Soldes Intermédiaires de Gestion

RÈGLES :
1. Tu ne manipules QUE des rubrique_key et metric_key — jamais de numéros de comptes PCG, jamais de SQL.
2. Maximum 8 étapes par plan.
3. Si un concept est désactivé pour le secteur, NE PAS le proposer.
4. Réponds UNIQUEMENT en JSON valide — pas de texte avant/après.
5. Quand la question porte sur une évolution, tendance, graphique ou courbe d'une grandeur :
   a. Si la rubrique_key est claire dans relevant_concepts, utilise-la directement dans get_trend.
   b. Si le concept n'est pas résolu, crée d'abord une étape resolve_concept {"query": "..."} avec un id
      (ex: "s1"), puis dans l'étape get_trend mets rubrique_key="$resolve.s1" — le moteur le substituera
      automatiquement par le premier résultat de resolve_concept.
   c. granularity="monthly" par défaut (sauf si l'utilisateur demande explicitement annuel).
   d. expected_output_type="chart".
   e. Cette règle s'applique à TOUTE rubrique (CA, cash, trésorerie, masse salariale, EBE, résultat…).
6. Pour les questions sur les MÉTRIQUES / RATIOS (RÈGLE STRICTE) :
   a. Si l'utilisateur demande DIRECTEMENT un ratio ou une métrique spécifique (ex: "taux d'endettement net",
      "marge EBE", "coût de la dette", "montre-moi X", "quel est X"), utilise query_metric avec le metric_key
      correspondant. NE PAS utiliser get_waterfall.
   b. expected_output_type="metric_card" pour afficher le ratio avec seuils et position sectorielle.
   c. Utilise get_waterfall UNIQUEMENT ET EXCLUSIVEMENT si l'utilisateur demande explicitement :
      - Une décomposition ("décompose", "détaille", "montre la décomposition")
      - Une cascade ("cascade", "waterfall", "montre la cascade")
      - Une explication de calcul ("comment est calculé", "d'où vient", "explique le calcul")
   d. En cas de doute entre query_metric et get_waterfall, TOUJOURS choisir query_metric.
7. Pour les comparaisons sectorielles :
   a. N'utilise compare_sector QUE si l'utilisateur demande explicitement une comparaison sectorielle,
      un benchmark, ou une position par rapport au secteur.
   b. Mots-clés déclencheurs : "par rapport au secteur", "vs secteur", "benchmark", "comparé au secteur",
      "position sectorielle", "médiane du secteur".
   c. expected_output_type="sector_gauge" pour les comparaisons sectorielles.
8. Quand l'utilisateur demande une COMPARAISON ou EVOLUTION de PLUSIEURS grandeurs
   (mots-clés : "vs", "par rapport à", "comparer", "évolution du X et du Y",
    "X contre Y", "X et Y") :
   a. Crée une étape get_trend SÉPARÉE pour CHAQUE rubrique avec les MÊMES from_year,
      to_year et granularity.
   b. expected_output_type="chart".
   c. Le synthesizer fusionnera automatiquement les résultats en un seul graphique comparatif.
   d. Maximum 4 séries par comparaison (limiter à 4 rubriques).
   e. Ne comparer que des rubriques de même unité (EUR avec EUR, % avec %).
"""


def planner(state: dict, llm: ChatGoogleGenerativeAI) -> dict:
    """Use Gemini to generate a structured execution plan.

    Args:
        state: Current AgentState as a dict.
        llm: Configured Gemini LLM instance.

    Returns:
        Dict with 'plan' key containing a Plan object.
    """
    user_message = state.get("user_message", "")
    domain_context = state.get("domain_context", {})
    relevant_concepts = state.get("relevant_concepts", [])
    company_profile = state.get("company_profile", {})
    sector_profile = state.get("sector_profile", {})
    chat_history = state.get("chat_history", [])
    agent_spec = state.get("agent_spec", {})

    tools_desc = json.dumps(
        agent_spec.get("tools", []), ensure_ascii=False, indent=2
    )

    context_text = f"""PROFIL ENTREPRISE :
{json.dumps(company_profile, ensure_ascii=False, indent=2)}

CONCEPTS RÉSOLUS POUR CETTE REQUÊTE :
{json.dumps(relevant_concepts, ensure_ascii=False, indent=2)}

CONTEXTE DOMAINE (concepts actifs, ratios, cascades) :
{json.dumps(domain_context, ensure_ascii=False, indent=2)}

OUTILS (schémas) :
{tools_desc}
"""

    history_messages = []
    for msg in chat_history[-12:]:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            history_messages.append(HumanMessage(content=content))

    messages = [
        SystemMessage(content=PLANNER_SYSTEM_PROMPT),
        *history_messages,
        HumanMessage(content=f"CONTEXTE :\n{context_text}\n\nQUESTION UTILISATEUR :\n{user_message}"),
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
            "reasoning": "Erreur de parsing du plan LLM",
            "steps": [],
            "expected_output_type": "text",
        }

    steps = []
    for s in plan_data.get("steps", []):
        steps.append(PlanStep(
            id=s.get("id", f"s{len(steps)+1}"),
            tool=s["tool"],
            args=s.get("args", {}),
            depends_on=s.get("depends_on", []),
        ))

    plan = Plan(
        reasoning=plan_data.get("reasoning", ""),
        steps=steps,
        expected_output_type=plan_data.get("expected_output_type", "text"),
    )

    return {"plan": plan, "current_step_idx": 0, "tool_results": []}
