"""End-to-end smoke test for the PCG FEC Agent data pipeline.

Tests:
1. FEC ingestion (load xlsx)
2. DuckDB query engine (register + query)
3. Semantic layer (SQL builder + concept resolution)
4. Tool dispatcher (query_rubrique, query_metric, get_waterfall, compare_sector)

This test does NOT require a Gemini API key -- it tests the config-driven
data pipeline only, which is the heart of the architecture.
"""

import sys
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

from pcg_agent.ingestion.fec_loader import FECIngestion
from pcg_agent.query_engine.duckdb_engine import FECQueryEngine
from pcg_agent.semantic_layer.mdl_reader import PCGSemanticLayer
from pcg_agent.tools.dispatcher import dispatch


def main():
    fec_path = BASE / "FEC_blckbx_cannes_2025.xlsx"
    config_dir = BASE / "pcg_agent" / "config"

    print("=" * 60)
    print("SMOKE TEST — PCG FEC Agent Data Pipeline")
    print("=" * 60)

    # ── 1. Ingestion ────────────────────────────────────────────
    print("\n[1] Loading FEC...")
    ingestion = FECIngestion()
    df = ingestion.load(fec_path)
    exercices = ingestion.get_exercices(df)
    print(f"    Rows: {len(df)}")
    print(f"    Exercices: {exercices}")
    print(f"    Columns: {list(df.columns)}")
    print(f"    Total debit:  {df['debit'].sum():,.2f}")
    print(f"    Total credit: {df['credit'].sum():,.2f}")

    # ── 2. Query engine ────────────────────────────────────────
    print("\n[2] Initializing DuckDB engine...")
    engine = FECQueryEngine(df)
    row = engine.fetch_one("SELECT COUNT(*) AS cnt FROM fec")
    print(f"    Row count from DuckDB: {row['cnt']}")

    # ── 3. Semantic layer ──────────────────────────────────────
    print("\n[3] Loading semantic layer...")
    semantic = PCGSemanticLayer(config_dir)
    keys = semantic.get_all_rubrique_keys()
    print(f"    Rubrique keys: {keys}")
    print(f"    Active concepts (96.02A): {semantic.get_active_concepts()}")

    # ── 4. Concept resolution ──────────────────────────────────
    print("\n[4] Concept resolution tests...")
    for query in ["fonds propres", "dette", "CA", "cash", "salaires"]:
        matches = semantic.resolve_concept(query)
        top = matches[0] if matches else {"rubrique_key": "NONE", "score": 0}
        print(f"    '{query}' -> {top['rubrique_key']} (score={top['score']})")

    # ── 5. SQL builder + execution ─────────────────────────────
    exercice = max(exercices)
    print(f"\n[5] Querying rubriques for exercice={exercice}...")

    rubrique_results = {}
    for rk in ["capitaux_propres", "endettement_brut", "tresorerie_active",
                "chiffre_affaires", "masse_salariale", "resultat_net",
                "compte_courant_associes", "charges_interets"]:
        result = dispatch("query_rubrique", {"rubrique_key": rk, "exercice": exercice}, engine, semantic)
        val = result["value"]
        rubrique_results[rk] = val
        alerts = result.get("alerts", [])
        alert_str = f" [ALERT: {alerts[0]['level']}]" if alerts else ""
        print(f"    {result['label']:40s} = {val:>12,.2f} EUR{alert_str}")

    # ── 6. Ratios ──────────────────────────────────────────────
    print(f"\n[6] Computing ratios for exercice={exercice}...")
    for rk in ["capitaux_propres_nets", "taux_endettement_brut", "taux_endettement_net", "marge_ebe",
                "poids_masse_salariale", "cout_dette"]:
        result = dispatch("query_metric", {"metric_key": rk, "exercice": exercice}, engine, semantic)
        val = result["value"]
        if val is not None:
            fmt = result.get("output_format", "multiple")
            if fmt == "percentage":
                val_str = f"{val*100:.1f}%"
            elif fmt == "euros":
                val_str = f"{val:>,.2f} EUR"
            else:
                val_str = f"{val:.2f}x"
        else:
            val_str = "N/A (div/0)"
        status = result["status"]["label"]
        caveats_str = f" | Caveat: {result['caveats'][0]}" if result.get("caveats") else ""
        print(f"    {result['display_name']:40s} = {val_str:>12s}  [{status}]{caveats_str}")

    # ── 7. Waterfall ───────────────────────────────────────────
    print(f"\n[7] Waterfall: endettement_complet for {exercice}...")
    wf_result = dispatch(
        "get_waterfall",
        {"waterfall_key": "endettement_complet", "exercice": exercice, "include_cca_as_qfp": False},
        engine, semantic,
    )
    for section in wf_result["sections"]:
        print(f"    --- {section['section_label']} ---")
        for step in section["steps"]:
            val = step["value"]
            print(f"      {step['label']:40s} = {val:>12,.2f} EUR")

    # ── 8. Sector comparison ───────────────────────────────────
    print(f"\n[8] Sector comparison: taux_endettement_net vs BdF 96.02...")
    sector = dispatch(
        "compare_sector",
        {"metric_key": "taux_endettement_net", "exercice": exercice},
        engine, semantic,
    )
    pos = sector.get("sector_position", {})
    val = sector.get("value")
    if val is not None:
        print(f"    Value:   {val:.2f}x")
        print(f"    Q1:      {pos.get('q1', 'N/A')}")
        print(f"    Median:  {pos.get('mediane', 'N/A')}")
        print(f"    Q3:      {pos.get('q3', 'N/A')}")
        print(f"    Position: {pos.get('position', 'N/A')}")
    if sector.get("caveats"):
        for c in sector["caveats"]:
            print(f"    Caveat: {c}")
    if sector.get("maturity_warning"):
        print(f"    Maturity: {sector['maturity_warning']}")

    # ── 9. SIG ─────────────────────────────────────────────────
    print(f"\n[9] SIG simplifié for {exercice}...")
    sig = dispatch("get_sig", {"exercice": exercice}, engine, semantic)
    for item in sig["items"]:
        print(f"    {item['label']:40s} = {item['value']:>12,.2f} EUR")

    print("\n" + "=" * 60)
    print("SMOKE TEST PASSED — All data pipeline components working!")
    print("=" * 60)


if __name__ == "__main__":
    main()
