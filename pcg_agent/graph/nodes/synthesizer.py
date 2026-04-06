"""synthesizer node: formats all tool results into a structured response.

This is the final node before the answer is returned. It receives all
tool_results, alerts, and sector positions, and uses Gemini to compose
a clear, structured answer with response_blocks (metric cards, tables,
charts, alerts, waterfalls, sector gauges, text).
"""

from __future__ import annotations

import json

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage


SYNTHESIZER_SYSTEM_PROMPT = """Tu es un analyste financier expert qui présente des résultats comptables en français.

Tu reçois les résultats d'analyse d'un FEC (Fichier des Écritures Comptables) et tu dois composer
une réponse claire et structurée pour un non-expert.

FORMAT DE SORTIE — JSON avec :
{
  "final_answer": "Texte principal de la réponse (markdown français)",
  "response_blocks": [
    {"type": "metric_card", "label": "...", "value": ..., "unit": "EUR|%|x", "status": "healthy|warning|critical"},
    {"type": "table", "title": "...", "columns": [...], "rows": [...]},
    {"type": "chart", "label": "...", "rubrique_key": "...", "data": [{"period": "Jan 2025", "value": 12345.0}, ...]},
    {"type": "alert", "level": "info|warning|critical", "message": "..."},
    {"type": "waterfall_card", "title": "...", "sections": [...]},
    {"type": "sector_gauge", "label": "...", "value": ..., "q1": ..., "mediane": ..., "q3": ..., "position": "..."},
    {"type": "text", "content": "..."}
  ]
}

RÈGLES POUR LES CHART BLOCKS :
- Utilise le type "chart" dès que get_trend a retourné des données (granularity monthly ou annual).
- Pour granularity=monthly : formate chaque point comme {"period": "Jan 2025", "value": 12345.0}
  en convertissant mois (1-12) en libellé français court (Jan, Fév, Mar, Avr, Mai, Jun, Jul, Aoû, Sep, Oct, Nov, Déc) suivi de l'année.
- Pour granularity=annual : formate chaque point comme {"period": "2024", "value": 12345.0}
- Ne jamais laisser des données de tendance sans chart block correspondant.
- "label" = nom lisible de la rubrique (ex: "Chiffre d'Affaires Mensuel 2025").

RÈGLES POUR LES CHART COMPARATIFS (MULTI-SÉRIES) :
- Quand les résultats contiennent PLUSIEURS get_trend avec le même granularity ET
  des périodes qui se chevauchent, les fusionner en UN SEUL chart block multi-séries.
- Format du chart comparatif :
  {"type": "chart", "chart_type": "line", "label": "CA vs Charges (2024)",
   "xKey": "period",
   "data": [{"period": "Jan 2024", "CA": 15000, "charges_exploitation": 12000}, ...],
   "series": [
     {"key": "CA", "label": "Chiffre d'Affaires"},
     {"key": "charges_exploitation", "label": "Charges d'exploitation"}
   ]}
- chart_type="line" pour les évolutions temporelles, "bar" pour des comparaisons de valeurs isolées.
- Les clés de séries = rubrique_key (identifiants courts sans espaces).
- NE PAS fusionner si les grandeurs ont des unités INCOMPATIBLES (EUR vs %).
  Produire des chart blocks séparés dans ce cas.
- NE PAS fusionner si les granularités diffèrent (monthly vs annual).
- Quand il n'y a qu'un seul get_trend, utiliser le format single-series existant
  ({"period": "...", "value": ...}).

RÈGLES POUR LES COMPARAISONS SECTORIELLES :
- Quand un compare_sector est présent dans les résultats, utiliser UNIQUEMENT un bloc "sector_gauge" pour afficher le positionnement.
- NE PAS créer de metric_card séparé pour la même métrique — le sector_gauge affiche déjà la valeur de l'entreprise.

RÈGLES GÉNÉRALES :
1. Formater les montants en EUR avec séparateur de milliers (espace) et 2 décimales.
2. Les pourcentages avec 1 décimale suivie de %.
3. Les multiples avec 1 décimale suivie de x.
4. Toujours mentionner les alertes et caveats.
5. Si des données sectorielles sont disponibles, les inclure dans des sector_gauge blocks.
6. Être pédagogue — expliquer brièvement ce que signifie chaque indicateur.
7. Répondre en français.
8. JSON valide uniquement.
"""


def synthesizer(state: dict, llm: ChatGoogleGenerativeAI) -> dict:
    """Compose the final structured answer from tool results.

    Args:
        state: Full AgentState as dict (with tool_results, alerts, etc.)
        llm: Configured Gemini LLM.

    Returns:
        Dict with final_answer and response_blocks.
    """
    user_message = state.get("user_message", "")
    tool_results = state.get("tool_results", [])
    alerts = state.get("alerts", [])
    sector_positions = state.get("sector_positions", [])
    plan = state.get("plan")

    results_data = []
    for tr in tool_results:
        if hasattr(tr, "model_dump"):
            results_data.append(tr.model_dump())
        else:
            results_data.append(tr)

    context_text = f"""QUESTION UTILISATEUR : {user_message}

RÉSULTATS DES OUTILS :
{json.dumps(results_data, ensure_ascii=False, indent=2, default=str)}

ALERTES MDL :
{json.dumps(alerts, ensure_ascii=False, indent=2, default=str)}

POSITIONNEMENTS SECTORIELS :
{json.dumps(sector_positions, ensure_ascii=False, indent=2, default=str)}
"""

    messages = [
        SystemMessage(content=SYNTHESIZER_SYSTEM_PROMPT),
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
        output = json.loads(raw)
    except json.JSONDecodeError:
        output = {
            "final_answer": raw,
            "response_blocks": [],
        }

    final_answer = output.get("final_answer", "")
    response_blocks = output.get("response_blocks", [])

    return {
        "final_answer": final_answer,
        "response_blocks": response_blocks,
    }
