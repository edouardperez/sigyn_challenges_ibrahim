# PCG Data Agent — Architecture Finale (FEC-Native)

> French accounting (Plan Comptable Général) · Config-driven · LangGraph · Wren AI MDL pattern
> FEC-native analysis · Sector-aware (NAF 96.02A) · Benchmark-ready
> Dernière mise à jour : Avril 2026

---

## Table des matières

1. [Executive Summary](#executive-summary)
2. [Le concept de « rubrique »](#le-concept-de-rubrique)
3. [Architecture 6 couches](#architecture-6-couches)
4. [L0 — FEC Ingestion](#l0--fec-ingestion)
5. [L1 — Normalized DataFrame + Query Engine](#l1--normalized-dataframe--query-engine)
6. [L2 — Semantic Layer (MDL Manifest)](#l2--semantic-layer-mdl-manifest)
7. [L3 — Ontology Layer](#l3--ontology-layer)
8. [L4 — Metric Layer](#l4--metric-layer)
9. [L5 — Agent Spec](#l5--agent-spec)
10. [PCGSemanticLayer — Dual-Path Pattern](#pcgsemanticlayer--dual-path-pattern)
11. [LangGraph Runtime — Graph Nodes](#langgraph-runtime--graph-nodes)
12. [AgentState — Typed State Object](#agentstate--typed-state-object)
13. [Wren AI Patterns — Ce qu'on emprunte et comment](#wren-ai-patterns)
14. [Exemple end-to-end](#exemple-end-to-end)
15. [Où vit chaque morceau de logique métier](#où-vit-chaque-morceau-de-logique-métier)
16. [Folder Structure](#folder-structure)
17. [Build Order](#build-order)
18. [Règles fondamentales](#règles-fondamentales)

---

## Executive Summary

Un agent conversationnel config-driven pour l'analyse financière française à partir du FEC (Fichier des Écritures Comptables). L'utilisateur pose des questions en langage naturel. L'agent planifie, requête le FEC chargé en DataFrame via DuckDB, évalue les résultats contre des règles métier, et retourne des blocs de réponse structurés (metric cards, tables, charts, alertes, waterfalls, jauges sectorielles).

**Le principe fondamental :** le LLM ne gère que le langage et la planification. Toute la connaissance comptable vit dans des fichiers JSON de config versionnés. Aucun SQL n'est écrit par le LLM. Aucune règle métier ne vit dans le texte du prompt.

---

## Le concept de « rubrique »

### Le problème

L'utilisateur demande : *« Quels sont mes fonds propres ? »*

Pour répondre, il faut enchaîner quatre choses de natures totalement différentes :

1. **Comprendre** que « fonds propres » = capitaux propres = comptes 10 à 14, sauf 109
2. **Exécuter le bon SQL** avec la bonne polarité (credit - debit pour un passif)
3. **Évaluer** si le résultat est bon ou mauvais (CP négatifs = alerte critique)
4. **Savoir** que ce KPI sert dans le calcul du taux d'endettement, de l'autonomie financière, etc.

Ces quatre choses parlent toutes du **même objet**. La **rubrique_key** (ici `capitaux_propres`) est la clé qui relie les couches entre elles.

### Le flux

```
L'utilisateur dit : "fonds propres"
        │
        ▼
L3 (Ontology) : "fonds propres" → synonyme de rubrique_key = "capitaux_propres"
                 → inclusion : comptes 10-14
                 → exclusion : 109
        │
        ▼
L2 (Semantic/MDL) : rubrique_key = "capitaux_propres"
                     → expression SQL toute faite :
                     SUM(CASE WHEN prefix IN ('10'..'14')
                     AND prefix != '109'
                     THEN credit - debit ELSE 0 END)
        │
        ▼
L4 (Metrics) : rubrique_key = "capitaux_propres"
               → utilisé dans ratio "taux_endettement_brut"
               → alerte si CP < 0 ou < 10 000 €
               → benchmark BdF secteur 96.02
```

### Pourquoi pas juste un numéro de compte PCG ?

Un concept financier ne correspond presque jamais à un seul compte :

| Concept | Comptes PCG | Complexité |
|---|---|---|
| Capitaux propres | 101, 106, 110, 119, 120, 129 sauf 109 | 6 comptes + exclusion + 2 comptes soustractifs |
| Endettement brut | 164, 168, 519 | Mix dettes LT + CT dans des classes différentes |
| Trésorerie active | 512, 530, 531, 50x | Banque + caisse + VMP, mais exclure les soldes bancaires négatifs |
| EBE | 70-74 (produits) moins 60-64 (charges) | Mélange classes 6 et 7 avec polarités inversées |

La rubrique est un **agrégat logique** avec des règles d'inclusion, d'exclusion et de polarité. C'est l'équivalent d'une **ligne du bilan** — un label lisible qui pointe vers une mécanique cachée.

### Ce que le planner manipule

Le LLM ne voit **que** des rubrique_keys — jamais des numéros de comptes, jamais du SQL :

```json
{
  "steps": [
    { "tool": "query_rubrique", "args": { "rubrique_key": "capitaux_propres", "exercice": 2025 } },
    { "tool": "query_ratio",    "args": { "ratio_key": "taux_endettement_brut", "exercice": 2025 } }
  ]
}
```

**Le contrat : le LLM parle en rubriques, le SQL builder exécute en comptes PCG. Ils ne se rencontrent jamais.**

---

## Architecture 6 couches

```
┌─────────────────────────────────────────────────────────────────┐
│  L0 — FEC Ingestion                                            │
│  Raw FEC (.xlsx/.csv) → pandas DataFrame                       │
│  Column mapping, exercice/mois extraction, validation          │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│  L1 — Normalized DataFrame + DuckDB Query Engine               │
│  df_fec (numero_compte, debit, credit, exercice, mois, ...)   │
│  In-memory — queried via DuckDB (zero-copy on pandas)          │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│  L2 — Semantic Layer  (Wren MDL pattern)                       │
│  config/semantic/mdl_manifest.json                             │
│  SQL expressions, macros, polarity, auto_filters               │
│  One expression per rubrique — single source of truth          │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│  L3 — Ontology Layer                                           │
│  config/ontology/                                              │
│  Concepts, synonymes, taxonomie PCG, profils sectoriels        │
│  Reclassements conditionnels (455, EENE)                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│  L4 — Metric Layer                                             │
│  config/metrics/                                               │
│  Ratios avec seuils + caveats sectoriels                       │
│  Benchmarks BdF par NAF (médiane, Q1, Q3)                      │
│  Waterfalls (cascades ordonnées de rubriques)                  │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│  L5 — Agent Spec                                               │
│  config/agent_spec.json                                        │
│  Planner policy, tool schemas, security guardrails             │
│  Response blocks : metric_card, waterfall_card, sector_gauge   │
└─────────────────────────────────────────────────────────────────┘
```

---

## L0 — FEC Ingestion

Le FEC est le fichier légal d'export comptable défini par l'Article A.47 A-1 du Livre des Procédures Fiscales. Toute entreprise française doit en produire un.

### Schéma FEC réel (RD Cannes — 9 375 écritures)

| Colonne FEC | Type | Mappé vers | Notes |
|---|---|---|---|
| `JournalCode` | str | `journal_code` | AN, HA, VE, BQ, OD, CA... |
| `JournalLib` | str | `journal_lib` | Libellé du journal |
| `EcritureNum` | str | `ecriture_num` | Numéro séquentiel |
| `EcritureDate` | str (YYYYMMDD) | `ecriture_date` | **On en dérive `exercice` et `mois`** |
| `CompteNum` | str | `numero_compte` | **Colonne clé — numéro de compte PCG** |
| `CompteLib` | str | `libelle_compte` | Libellé du compte |
| `CompAuxNum` | str | `compte_aux_num` | Sous-compte auxiliaire (client/fournisseur) |
| `CompAuxLib` | str | `compte_aux_lib` | Libellé du tiers |
| `PieceRef` | str | `piece_ref` | Référence de la pièce |
| `PieceDate` | str (YYYYMMDD) | `piece_date` | Date de la pièce |
| `EcritureLib` | str | `ecriture_lib` | Libellé de l'écriture |
| `Debit` | float | `debit` | Montant au débit |
| `Credit` | float | `credit` | Montant au crédit |
| `EcritureLet` | str | `lettre` | Code de lettrage |
| `DateLet` | str | `date_let` | Date de lettrage |
| `ValidDate` | str | `valid_date` | Date de validation |
| `Montantdevise` | float | `montant_devise` | Montant en devise étrangère |
| `Idevise` | str | `devise` | Code devise (EUR) |

### Logique d'ingestion

```python
class FECIngestion:
    """L0 — Charge un FEC brut en DataFrame normalisé."""

    COLUMN_MAP = {
        "CompteNum": "numero_compte",
        "CompteLib": "libelle_compte",
        "EcritureDate": "ecriture_date",
        "JournalCode": "journal_code",
        "JournalLib": "journal_lib",
        "EcritureLib": "ecriture_lib",
        "Debit": "debit",
        "Credit": "credit",
        "CompAuxNum": "compte_aux_num",
        "CompAuxLib": "compte_aux_lib",
        "Idevise": "devise",
    }

    def load(self, filepath: str) -> pd.DataFrame:
        df = pd.read_excel(filepath, dtype={"CompteNum": str, "EcritureDate": str})
        df = df.rename(columns=self.COLUMN_MAP)

        # Dériver exercice et mois depuis EcritureDate (YYYYMMDD)
        df["exercice"] = df["ecriture_date"].str[:4].astype(int)
        df["mois"] = df["ecriture_date"].str[4:6].astype(int)

        # Dériver les préfixes de compte pour le matching PCG
        df["compte_prefix_1"] = df["numero_compte"].str[:1]
        df["compte_prefix_2"] = df["numero_compte"].str[:2]
        df["compte_prefix_3"] = df["numero_compte"].str[:3]

        # NaN → 0 pour debit/credit
        df["debit"] = df["debit"].fillna(0.0)
        df["credit"] = df["credit"].fillna(0.0)

        self._validate(df)
        return df

    def _validate(self, df: pd.DataFrame):
        total_debit = df["debit"].sum()
        total_credit = df["credit"].sum()
        assert abs(total_debit - total_credit) < 0.01, \
            f"Contrôle balance échoué : D={total_debit:.2f} C={total_credit:.2f}"
```

---

## L1 — Normalized DataFrame + Query Engine

Le FEC normalisé vit en mémoire dans un DataFrame pandas. On utilise **DuckDB** pour l'exécution SQL directement sur le df (zero-copy) :

```python
import duckdb

class FECQueryEngine:
    """L1 — Exécute du SQL sur le DataFrame FEC via DuckDB."""

    def __init__(self, df: pd.DataFrame):
        self.conn = duckdb.connect()
        self.conn.register("fec", df)

    def fetch_one(self, sql: str) -> dict:
        result = self.conn.execute(sql).fetchdf()
        return result.iloc[0].to_dict() if len(result) > 0 else {}

    def fetch_all(self, sql: str) -> list[dict]:
        return self.conn.execute(sql).fetchdf().to_dict("records")
```

Les expressions MDL écrivent du SQL standard qui s'exécute sur la table `fec` (le DataFrame enregistré dans DuckDB).

---

## L2 — Semantic Layer (MDL Manifest)

La seule source de vérité pour le SQL. Le LLM ne voit jamais ce fichier — seul le `PCGSemanticLayer` (SQL builder) le lit.

### `config/semantic/mdl_manifest.json`

```json
{
  "catalog": "pcg_fec_analysis",
  "version": "2.0",
  "source": "FEC (Fichier des Écritures Comptables)",

  "macros": [
    {
      "name": "solde_passif",
      "description": "Solde crédit - débit pour comptes de passif.",
      "definition": "SUM(CASE WHEN ({include_cond}) {exclude_cond} THEN credit - debit ELSE 0 END)"
    },
    {
      "name": "solde_actif",
      "description": "Solde débit - crédit pour comptes d'actif.",
      "definition": "SUM(CASE WHEN ({include_cond}) {exclude_cond} THEN debit - credit ELSE 0 END)"
    }
  ],

  "models": [
    {
      "name": "FEC",
      "tableReference": "fec",
      "properties": {
        "auto_filters": [],
        "forbidden_operations": ["INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE"],
        "exclude_journals": {
          "for_flux_analysis": ["AN"],
          "note": "Journal à-nouveaux (AN) = soldes d'ouverture. Exclure pour l'analyse de flux, inclure pour les soldes."
        }
      },
      "columns": [
        { "name": "numero_compte",  "type": "VARCHAR",  "properties": { "supports_prefix_match": true } },
        { "name": "libelle_compte", "type": "VARCHAR",  "properties": { "searchable": true } },
        { "name": "exercice",       "type": "INTEGER",  "properties": { "filterable": true, "is_fiscal_year": true } },
        { "name": "mois",           "type": "INTEGER",  "properties": { "filterable": true } },
        { "name": "journal_code",   "type": "VARCHAR",  "properties": { "filterable": true } },
        { "name": "debit",          "type": "DECIMAL",  "properties": { "aggregatable": true } },
        { "name": "credit",         "type": "DECIMAL",  "properties": { "aggregatable": true } },

        {
          "name": "capitaux_propres",
          "isCalculated": true,
          "expression": "SUM(CASE WHEN compte_prefix_2 IN ('10','11','12','13','14') AND compte_prefix_3 != '109' THEN credit - debit ELSE 0 END)",
          "rubrique_key": "capitaux_propres",
          "prefixes": ["10","11","12","13","14"],
          "exclude_prefixes": ["109"],
          "polarity": "credit_moins_debit"
        },
        {
          "name": "capitaux_propres_appeles",
          "isCalculated": true,
          "expression": "SUM(CASE WHEN compte_prefix_2 IN ('10','11','12','13','14') AND compte_prefix_3 NOT IN ('109') THEN credit - debit ELSE 0 END)",
          "rubrique_key": "capitaux_propres_appeles",
          "prefixes": ["10","11","12","13","14"],
          "exclude_prefixes": ["109"],
          "polarity": "credit_moins_debit",
          "note": "CP appelés = CP - CSNA (109)"
        },
        {
          "name": "endettement_brut",
          "isCalculated": true,
          "expression": "SUM(CASE WHEN compte_prefix_3 IN ('164','168') THEN credit - debit WHEN compte_prefix_3 = '519' THEN credit - debit ELSE 0 END)",
          "rubrique_key": "endettement_brut",
          "prefixes": ["164","168","519"],
          "polarity": "credit_moins_debit",
          "note": "Emprunts LT (164,168) + CBC (519)"
        },
        {
          "name": "emprunts_lt",
          "isCalculated": true,
          "expression": "SUM(CASE WHEN compte_prefix_3 IN ('164','168') THEN credit - debit ELSE 0 END)",
          "rubrique_key": "emprunts_lt",
          "prefixes": ["164","168"],
          "polarity": "credit_moins_debit"
        },
        {
          "name": "concours_bancaires_courants",
          "isCalculated": true,
          "expression": "SUM(CASE WHEN compte_prefix_3 = '519' THEN credit - debit ELSE 0 END)",
          "rubrique_key": "concours_bancaires_courants",
          "prefixes": ["519"],
          "polarity": "credit_moins_debit"
        },
        {
          "name": "disponibilites",
          "isCalculated": true,
          "expression": "SUM(CASE WHEN compte_prefix_3 IN ('512','530','531') THEN debit - credit ELSE 0 END)",
          "rubrique_key": "disponibilites",
          "prefixes": ["512","530","531"],
          "polarity": "debit_moins_credit",
          "note": "Banque + Caisse"
        },
        {
          "name": "vmp_liquides",
          "isCalculated": true,
          "expression": "SUM(CASE WHEN compte_prefix_2 = '50' THEN debit - credit ELSE 0 END)",
          "rubrique_key": "vmp_liquides",
          "prefixes": ["50"],
          "polarity": "debit_moins_credit",
          "note": "VMP liquides et sans risque (SICAV monétaires)"
        },
        {
          "name": "tresorerie_active",
          "isCalculated": true,
          "expression": "SUM(CASE WHEN compte_prefix_3 IN ('512','530','531') AND (debit - credit) > 0 THEN debit - credit WHEN compte_prefix_2 = '50' THEN debit - credit ELSE 0 END)",
          "rubrique_key": "tresorerie_active",
          "polarity": "composite",
          "note": "Disponibilités positives + VMP liquides"
        },
        {
          "name": "tresorerie_passive",
          "isCalculated": true,
          "expression": "SUM(CASE WHEN compte_prefix_3 = '519' THEN credit - debit WHEN compte_prefix_3 IN ('512','530','531') AND (credit - debit) > 0 THEN credit - debit ELSE 0 END)",
          "rubrique_key": "tresorerie_passive",
          "polarity": "composite",
          "note": "CBC (519) + soldes bancaires négatifs"
        },
        {
          "name": "compte_courant_associes",
          "isCalculated": true,
          "expression": "SUM(CASE WHEN compte_prefix_3 = '455' THEN credit - debit ELSE 0 END)",
          "rubrique_key": "compte_courant_associes",
          "prefixes": ["455"],
          "polarity": "credit_moins_debit",
          "reclassement": "conditional"
        },
        {
          "name": "charges_interets",
          "isCalculated": true,
          "expression": "SUM(CASE WHEN compte_prefix_3 = '661' THEN debit - credit ELSE 0 END)",
          "rubrique_key": "charges_interets",
          "prefixes": ["661"],
          "polarity": "debit_moins_credit"
        },
        {
          "name": "chiffre_affaires",
          "isCalculated": true,
          "expression": "SUM(CASE WHEN compte_prefix_2 IN ('70','71','72') THEN credit - debit ELSE 0 END)",
          "rubrique_key": "chiffre_affaires",
          "prefixes": ["70","71","72"],
          "polarity": "credit_moins_debit"
        },
        {
          "name": "masse_salariale",
          "isCalculated": true,
          "expression": "SUM(CASE WHEN compte_prefix_2 IN ('64') THEN debit - credit ELSE 0 END)",
          "rubrique_key": "masse_salariale",
          "prefixes": ["64"],
          "polarity": "debit_moins_credit",
          "note": "Charges de personnel (641 rémunérations + 645 charges sociales)"
        },
        {
          "name": "excedent_brut_exploitation",
          "isCalculated": true,
          "expression": "SUM(CASE WHEN compte_prefix_2 IN ('70','71','72','74') THEN credit - debit WHEN compte_prefix_2 IN ('60','61','62','63','64') THEN -(debit - credit) ELSE 0 END)",
          "rubrique_key": "excedent_brut_exploitation",
          "polarity": "composite",
          "note": "Produits exploitation (70-74) - Charges exploitation (60-64). Exclut amortissements (68) et provisions."
        },
        {
          "name": "resultat_net",
          "isCalculated": true,
          "expression": "SUM(CASE WHEN compte_prefix_1 = '7' THEN credit - debit WHEN compte_prefix_1 = '6' THEN -(debit - credit) ELSE 0 END)",
          "rubrique_key": "resultat_net",
          "polarity": "composite",
          "note": "Produits (classe 7) - Charges (classe 6)"
        },
        {
          "name": "transit_paiement",
          "isCalculated": true,
          "expression": "SUM(CASE WHEN compte_prefix_3 = '467' THEN debit - credit ELSE 0 END)",
          "rubrique_key": "transit_paiement",
          "prefixes": ["467"],
          "polarity": "debit_moins_credit",
          "note": "Solde Planity/Stripe — montants en transit. Un solde élevé = retard de reversement."
        },
        {
          "name": "effets_encaissement",
          "isCalculated": true,
          "expression": "SUM(CASE WHEN compte_prefix_3 IN ('511','513','514') THEN debit - credit ELSE 0 END)",
          "rubrique_key": "effets_encaissement",
          "prefixes": ["511","513","514"],
          "polarity": "debit_moins_credit",
          "note": "Valeurs à l'encaissement (511x) : 5113 = effets encaissement, 5114 = effets escompte"
        }
      ]
    }
  ],

  "views": [
    {
      "name": "SIG_simplifie",
      "displayName": "Soldes Intermédiaires de Gestion (simplifié coiffure)",
      "rubrique_keys": ["chiffre_affaires", "masse_salariale", "excedent_brut_exploitation", "resultat_net"]
    },
    {
      "name": "structure_endettement",
      "displayName": "Structure d'endettement complète",
      "rubrique_keys": ["capitaux_propres", "endettement_brut", "tresorerie_active", "tresorerie_passive"]
    }
  ]
}
```

---

## L3 — Ontology Layer

La connaissance comptable lisible par le LLM. C'est ce que le planner voit comme contexte — labels, synonymes, relations, justifications. Jamais de SQL.

### `config/ontology/concepts.json`

```json
{
  "concepts": [
    {
      "rubrique_key": "capitaux_propres",
      "rubrique_label": "Capitaux Propres",
      "synonyms": ["fonds propres", "equity", "CP", "situation nette"],
      "domain_category": "bilan_passif",
      "bilan_section": "Passif — Capitaux propres",
      "description": "Ressources propres : capital + réserves + report à nouveau + résultat. Exclut le CSNA (109).",
      "logic": {
        "inclusion": "Comptes 10 à 14 du PCG : capital (101), réserves (106), RAN (110/119), résultat (120/129), subventions (13), provisions réglementées (14).",
        "exclusion": "Compte 109 (capital souscrit non appelé) — non disponible en trésorerie."
      },
      "relationships": {
        "part_of": "total_passif",
        "used_in_ratio": ["taux_endettement_brut", "taux_endettement_net", "autonomie_financiere"],
        "related_to": ["compte_courant_associes"]
      },
      "higher_is_better": true,
      "importance_level": 9,
      "tags": ["bilan", "passif", "solvabilite", "pcg_classe1"]
    },
    {
      "rubrique_key": "endettement_brut",
      "rubrique_label": "Endettement Financier Brut",
      "synonyms": ["dettes financières", "dette brute", "emprunts"],
      "domain_category": "bilan_passif",
      "description": "Total des dettes financières : emprunts LT (164, 168) + concours bancaires courants (519). Exclut les dettes fournisseurs (401).",
      "logic": {
        "inclusion": "Comptes 164 (emprunts bancaires), 168 (autres emprunts), 519 (CBC/découverts).",
        "exclusion": "Dettes fournisseurs (401), dettes sociales/fiscales (43, 44) — ce ne sont pas des dettes financières."
      },
      "relationships": {
        "used_in_ratio": ["taux_endettement_brut", "taux_endettement_net", "cout_dette"],
        "related_to": ["charges_interets", "tresorerie_active"]
      },
      "higher_is_better": false,
      "importance_level": 9,
      "tags": ["bilan", "passif", "endettement", "pcg_classe1"]
    },
    {
      "rubrique_key": "tresorerie_active",
      "rubrique_label": "Trésorerie Active",
      "synonyms": ["cash", "liquidités", "disponibilités"],
      "domain_category": "bilan_actif",
      "description": "Cash réellement disponible : disponibilités bancaires positives (512) + caisse (530/531) + VMP liquides (50x).",
      "logic": {
        "inclusion": "Comptes 512 (banque, si positif), 530/531 (caisse), 50x (VMP si liquides et sans risque).",
        "exclusion": "Soldes bancaires négatifs (reclassés en trésorerie passive)."
      },
      "higher_is_better": true,
      "importance_level": 8,
      "tags": ["bilan", "actif", "tresorerie", "pcg_classe5"]
    },
    {
      "rubrique_key": "tresorerie_passive",
      "rubrique_label": "Trésorerie Passive",
      "synonyms": ["découvert", "CBC", "concours bancaires"],
      "domain_category": "bilan_passif",
      "description": "Financement CT subi : concours bancaires courants (519) + soldes bancaires négatifs.",
      "logic": {
        "inclusion": "Compte 519 + comptes 512 si solde créditeur (découvert).",
        "exclusion": "Aucune."
      },
      "higher_is_better": false,
      "importance_level": 8,
      "tags": ["bilan", "passif", "tresorerie", "pcg_classe5"]
    },
    {
      "rubrique_key": "compte_courant_associes",
      "rubrique_label": "Comptes Courants d'Associés",
      "synonyms": ["CCA", "avance associé", "current account", "455"],
      "domain_category": "zone_grise",
      "description": "Avances des associés à la société. Comptablement = dette (classe 4, compte 455). Économiquement = quasi-fonds propres si l'associé s'engage à ne pas retirer.",
      "logic": {
        "inclusion": "Compte 455.",
        "exclusion": "Aucune."
      },
      "reclassement": {
        "default_classification": "dettes_hors_exploitation",
        "alternative_classification": "quasi_fonds_propres",
        "switch_condition": "convention_blocage_or_user_choice",
        "impact_on_ratios": ["taux_endettement_brut", "taux_endettement_net"],
        "dual_scenario": true,
        "note": "Si reclassé en quasi-FP : le numérateur baisse (moins de dettes) ET le dénominateur monte (plus de FP) → double effet positif sur les ratios."
      },
      "higher_is_better": null,
      "importance_level": 7,
      "tags": ["bilan", "zone_grise", "pcg_classe4"]
    },
    {
      "rubrique_key": "charges_interets",
      "rubrique_label": "Charges d'Intérêts",
      "synonyms": ["intérêts", "frais financiers", "coût de la dette", "661"],
      "domain_category": "compte_de_resultat",
      "description": "Coût des emprunts et dettes financières. Compte 661.",
      "logic": {
        "inclusion": "Compte 661 et sous-comptes.",
        "exclusion": "Aucune.",
        "intuition": "Les comptes 66x (charges financières) mirroitent les 16x (dettes financières). Le 661 = coût du 164."
      },
      "relationships": {
        "used_in_ratio": ["cout_dette"],
        "related_to": ["endettement_brut"]
      },
      "higher_is_better": false,
      "importance_level": 6,
      "tags": ["resultat", "financier", "pcg_classe6"]
    },
    {
      "rubrique_key": "chiffre_affaires",
      "rubrique_label": "Chiffre d'Affaires",
      "synonyms": ["CA", "ventes", "revenus", "turnover"],
      "domain_category": "compte_de_resultat",
      "description": "Total des ventes et prestations de services. Comptes 70 à 72.",
      "logic": {
        "inclusion": "Comptes 70 (ventes), 71 (production stockée), 72 (production immobilisée).",
        "exclusion": "Aucune."
      },
      "higher_is_better": true,
      "importance_level": 10,
      "tags": ["resultat", "exploitation", "pcg_classe7"]
    },
    {
      "rubrique_key": "masse_salariale",
      "rubrique_label": "Masse Salariale",
      "synonyms": ["charges de personnel", "salaires", "payroll"],
      "domain_category": "compte_de_resultat",
      "description": "Rémunérations (641) + charges sociales (645). Premier poste de charges en coiffure.",
      "logic": {
        "inclusion": "Comptes 641 (rémunérations) et 645 (charges sociales).",
        "exclusion": "Aucune."
      },
      "relationships": {
        "used_in_ratio": ["poids_masse_salariale"]
      },
      "higher_is_better": false,
      "importance_level": 8,
      "tags": ["resultat", "exploitation", "pcg_classe6", "secteur_coiffure"]
    },
    {
      "rubrique_key": "transit_paiement",
      "rubrique_label": "Transit de Paiement (Planity/Stripe)",
      "synonyms": ["Planity", "Stripe", "SumUp", "TPE en transit"],
      "domain_category": "tresorerie",
      "description": "Montants encaissés par un prestataire (Planity/Stripe) pas encore reversés au salon. Compte 467 ou 511x.",
      "logic": {
        "inclusion": "Comptes 467 (tiers intermédiaires) et 511 (valeurs à l'encaissement).",
        "exclusion": "Aucune."
      },
      "alert_if_high": {
        "threshold_days": 7,
        "message": "Solde transit > 7 jours de CA quotidien — vérifier les reversements Stripe/Planity."
      },
      "higher_is_better": false,
      "importance_level": 5,
      "tags": ["tresorerie", "digital", "b2c"]
    }
  ]
}
```

### `config/ontology/pcg_taxonomy.json`

```json
{
  "pcg_classes": {
    "1": { "label": "Comptes de capitaux",         "bilan_side": "passif", "statement": "bilan" },
    "2": { "label": "Comptes d'immobilisations",   "bilan_side": "actif",  "statement": "bilan" },
    "3": { "label": "Comptes de stocks",            "bilan_side": "actif",  "statement": "bilan" },
    "4": { "label": "Comptes de tiers",             "bilan_side": "both",   "statement": "bilan" },
    "5": { "label": "Comptes financiers",           "bilan_side": "actif",  "statement": "bilan" },
    "6": { "label": "Comptes de charges",           "statement": "compte_de_resultat" },
    "7": { "label": "Comptes de produits",          "statement": "compte_de_resultat" }
  },
  "sig_cascade": ["chiffre_affaires", "valeur_ajoutee", "excedent_brut_exploitation", "resultat_exploitation", "resultat_net"]
}
```

### `config/ontology/business_rules.json`

```json
{
  "polarity_rules": {
    "credit_moins_debit": {
      "applies_to_classes": ["1", "4_passif", "5_passif"],
      "sql_pattern": "SUM(credit - debit)",
      "rationale": "Comptes de passif : solde créditeur = ressource positive."
    },
    "debit_moins_credit": {
      "applies_to_classes": ["2", "3", "4_actif", "5_actif"],
      "sql_pattern": "SUM(debit - credit)",
      "rationale": "Comptes d'actif : solde débiteur = avoir positif."
    },
    "composite": {
      "applies_to": ["excedent_brut_exploitation", "resultat_net", "tresorerie_active", "tresorerie_passive"],
      "rationale": "Agrège plusieurs classes avec polarités opposées — expression custom dans mdl_manifest."
    }
  },
  "global_exclusions": {
    "109": "Capital souscrit non appelé — non disponible, exclure des fonds propres.",
    "419": "Avances reçues clients — exclure des créances nettes.",
    "409": "Avances versées fournisseurs — exclure des dettes nettes."
  }
}
```

### `config/ontology/sector_profiles.json`

```json
{
  "profiles": {
    "96.02A": {
      "label": "Coiffure",
      "business_model": "B2C_cash",
      "characteristics": {
        "encaissement": "Comptant ou J+1 via TPE/Planity (pas de créances clients significatives).",
        "stocks": "Faibles — produits capillaires uniquement.",
        "saisonnalite": "Légère — creux estival, pic pré-fêtes.",
        "main_doeuvre": "Coût principal — masse salariale > 40% du CA.",
        "immobilisations": "Agencements salon, matériel coiffure, mobilier."
      },
      "active_concepts": [
        "capitaux_propres", "capitaux_propres_appeles", "endettement_brut",
        "emprunts_lt", "concours_bancaires_courants", "disponibilites",
        "vmp_liquides", "tresorerie_active", "tresorerie_passive",
        "compte_courant_associes", "charges_interets",
        "chiffre_affaires", "masse_salariale",
        "excedent_brut_exploitation", "resultat_net",
        "transit_paiement", "effets_encaissement"
      ],
      "disabled_concepts": {
        "besoin_fonds_roulement": "BFR quasi nul en B2C cash — pas pertinent.",
        "delai_recouvrement_clients": "Pas de créances clients en coiffure.",
        "production_stockee": "Pas de production stockée — activité de service.",
        "production_immobilisee": "Aucune production immobilisée."
      },
      "key_ratios": [
        "taux_endettement_brut", "taux_endettement_net",
        "marge_ebe", "cout_dette", "poids_masse_salariale"
      ],
      "bdf_fascicule_code": "96.02",
      "maturity_warning": {
        "creation_recente_years": 3,
        "message": "Entreprise créée il y a moins de 3 ans — les benchmarks BdF sont biaisés (comparaison avec des entreprises établies)."
      }
    }
  }
}
```

---

## L4 — Metric Layer

### `config/metrics/ratios.json`

```json
{
  "ratios": [
    {
      "ratio_key": "taux_endettement_brut",
      "display_name": "Taux d'Endettement Brut",
      "formula": "endettement_brut / capitaux_propres",
      "numerator_rubrique": "endettement_brut",
      "denominator_rubrique": "capitaux_propres",
      "output_format": "multiple",
      "higher_is_better": false,
      "thresholds": {
        "healthy":  { "max": 1.0, "label": "Endettement maîtrisé (< 1x)" },
        "warning":  { "min": 1.0, "max": 3.0, "label": "Endettement élevé (1-3x)" },
        "critical": { "min": 3.0, "label": "Endettement excessif (> 3x)" }
      },
      "sector_comparison": true,
      "caveat_if_low_equity": {
        "threshold_cp": 10000,
        "message": "CP très faibles — le ratio est mécaniquement élevé sans que l'endettement soit anormalement fort."
      }
    },
    {
      "ratio_key": "taux_endettement_net",
      "display_name": "Taux d'Endettement Net",
      "formula": "(endettement_brut - tresorerie_active) / capitaux_propres",
      "components": ["endettement_brut", "tresorerie_active", "capitaux_propres"],
      "output_format": "multiple",
      "higher_is_better": false,
      "thresholds": {
        "healthy":  { "max": 1.0, "label": "Endettement net maîtrisé" },
        "warning":  { "min": 1.0, "max": 3.0, "label": "Endettement net élevé" },
        "critical": { "min": 3.0, "label": "Endettement net critique" }
      },
      "sector_comparison": true
    },
    {
      "ratio_key": "cout_dette",
      "display_name": "Coût Moyen de la Dette",
      "formula": "charges_interets / endettement_brut",
      "numerator_rubrique": "charges_interets",
      "denominator_rubrique": "endettement_brut",
      "output_format": "percentage",
      "higher_is_better": false,
      "thresholds": {
        "healthy":  { "max": 0.05, "label": "Coût raisonnable (< 5%)" },
        "warning":  { "min": 0.05, "max": 0.08, "label": "Coût modéré (5-8%)" },
        "critical": { "min": 0.08, "label": "Coût élevé (> 8%)" }
      }
    },
    {
      "ratio_key": "marge_ebe",
      "display_name": "Marge EBE",
      "formula": "excedent_brut_exploitation / chiffre_affaires",
      "numerator_rubrique": "excedent_brut_exploitation",
      "denominator_rubrique": "chiffre_affaires",
      "output_format": "percentage",
      "higher_is_better": true,
      "thresholds": {
        "healthy":  { "min": 0.10, "label": "Marge saine (> 10%)" },
        "warning":  { "min": 0.05, "max": 0.10, "label": "Marge faible (5-10%)" },
        "critical": { "max": 0.05, "label": "Marge très faible (< 5%)" }
      }
    },
    {
      "ratio_key": "poids_masse_salariale",
      "display_name": "Poids de la Masse Salariale",
      "formula": "masse_salariale / chiffre_affaires",
      "numerator_rubrique": "masse_salariale",
      "denominator_rubrique": "chiffre_affaires",
      "output_format": "percentage",
      "higher_is_better": false,
      "thresholds": {
        "healthy":  { "max": 0.45, "label": "Maîtrisée (< 45%)" },
        "warning":  { "min": 0.45, "max": 0.55, "label": "Élevée (45-55%)" },
        "critical": { "min": 0.55, "label": "Critique (> 55%)" }
      },
      "sector_specific": "96.02A",
      "note": "En coiffure, la masse salariale est le premier poste. Médiane secteur ~42%."
    }
  ],

  "rubrique_alerts": {
    "tresorerie_active": {
      "critical": { "max": 0, "label": "Trésorerie négative — risque de cessation de paiements." }
    },
    "capitaux_propres": {
      "critical": { "max": 0, "label": "Capitaux propres négatifs — situation nette déficitaire." },
      "warning":  { "max": 10000, "label": "Capitaux propres très faibles — capacité d'emprunt limitée." }
    },
    "excedent_brut_exploitation": {
      "critical": { "max": 0, "label": "EBE négatif — activité structurellement non rentable." }
    },
    "resultat_net": {
      "critical": { "max": 0, "label": "Résultat déficitaire." }
    }
  }
}
```

### `config/metrics/benchmarks_bdf.json`

```json
{
  "source": "Banque de France — Fascicules d'indicateurs sectoriels",
  "last_update": "2024",
  "sectors": {
    "96.02": {
      "label": "Coiffure et soins de beauté",
      "naf_codes": ["96.02A", "96.02B"],
      "sample_size": "~85 000 entreprises",
      "ratios": {
        "taux_endettement_brut": { "q1": 0.3, "mediane": 1.2, "q3": 4.5, "unit": "multiple" },
        "taux_endettement_net": { "q1": -0.2, "mediane": 0.5, "q3": 3.0, "unit": "multiple", "note": "Q1 négatif = trésorerie excédant les dettes (entreprises établies)" },
        "autonomie_financiere": { "q1": 0.15, "mediane": 0.35, "q3": 0.60, "unit": "percentage" },
        "marge_ebe": { "q1": 0.05, "mediane": 0.12, "q3": 0.20, "unit": "percentage" },
        "poids_masse_salariale": { "q1": 0.35, "mediane": 0.42, "q3": 0.52, "unit": "percentage" }
      }
    }
  }
}
```

### `config/metrics/waterfalls.json`

```json
{
  "waterfalls": [
    {
      "waterfall_key": "endettement_complet",
      "display_name": "Cascade d'endettement",
      "sections": [
        {
          "section_label": "Ressources propres",
          "steps": [
            { "rubrique_key": "capitaux_propres", "label": "Capitaux propres", "operator": "base" },
            { "rubrique_key": "compte_courant_associes", "label": "+ CCA (si quasi-FP)", "operator": "add", "conditional": true },
            { "label": "= Ressources propres élargies", "operator": "subtotal" }
          ]
        },
        {
          "section_label": "Endettement",
          "steps": [
            { "rubrique_key": "emprunts_lt", "label": "Emprunts LT (164, 168)", "operator": "base" },
            { "rubrique_key": "concours_bancaires_courants", "label": "+ CBC / Découverts (519)", "operator": "add" },
            { "label": "= Endettement brut", "operator": "subtotal" }
          ]
        },
        {
          "section_label": "Trésorerie",
          "steps": [
            { "rubrique_key": "disponibilites", "label": "Disponibilités (512 + 531)", "operator": "base" },
            { "rubrique_key": "vmp_liquides", "label": "+ VMP liquides", "operator": "add" },
            { "label": "= Trésorerie active", "operator": "subtotal" }
          ]
        },
        {
          "section_label": "Synthèse",
          "steps": [
            { "ref": "endettement_brut", "label": "Endettement brut", "operator": "base" },
            { "ref": "tresorerie_active", "label": "- Trésorerie active", "operator": "subtract" },
            { "label": "= Endettement net", "operator": "result", "highlight": true }
          ]
        }
      ]
    }
  ]
}
```

---

## L5 — Agent Spec

### `config/agent_spec.json`

```json
{
  "agent_id": "pcg-fec-analyst-v2",
  "language": "fr",
  "mdl_manifest": "config/semantic/mdl_manifest.json",
  "ontology_path": "config/ontology/",
  "metrics_path": "config/metrics/",

  "planner": {
    "mode": "plan_execute_replan",
    "max_steps": 8,
    "max_replans": 2,
    "replan_on_tool_error": true,
    "replan_on_empty_result": true
  },

  "context_policy": {
    "inject_domain_ontology": true,
    "inject_sector_profile": true,
    "relevant_concepts_top_k": 5,
    "chat_history_window": 12,
    "include_company_profile": true
  },

  "tools": [
    {
      "name": "resolve_concept",
      "description": "Résout un terme comptable en rubrique_key PCG. Appeler quand le terme est ambigu.",
      "input_schema": {
        "type": "object",
        "required": ["query"],
        "properties": { "query": { "type": "string" } }
      }
    },
    {
      "name": "query_rubrique",
      "description": "Calcule la valeur d'une rubrique pour un exercice donné à partir du FEC.",
      "input_schema": {
        "type": "object",
        "required": ["rubrique_key", "exercice"],
        "properties": {
          "rubrique_key": { "type": "string" },
          "exercice":     { "type": "integer" },
          "mois":         { "type": "integer", "minimum": 1, "maximum": 12 }
        }
      },
      "guardrails": { "readonly": true, "timeout_seconds": 30 }
    },
    {
      "name": "query_ratio",
      "description": "Calcule un ratio financier et l'évalue (seuils absolus + position sectorielle BdF).",
      "input_schema": {
        "type": "object",
        "required": ["ratio_key", "exercice"],
        "properties": {
          "ratio_key": { "type": "string" },
          "exercice":  { "type": "integer" }
        }
      }
    },
    {
      "name": "get_trend",
      "description": "Évolution d'une rubrique sur plusieurs périodes (mensuel ou annuel).",
      "input_schema": {
        "type": "object",
        "required": ["rubrique_key", "from_year", "to_year"],
        "properties": {
          "rubrique_key": { "type": "string" },
          "from_year":    { "type": "integer" },
          "to_year":      { "type": "integer" },
          "granularity":  { "type": "string", "enum": ["monthly", "annual"], "default": "annual" }
        }
      }
    },
    {
      "name": "get_breakdown",
      "description": "Décompose une rubrique en ses sous-comptes PCG (top N).",
      "input_schema": {
        "type": "object",
        "required": ["rubrique_key", "exercice"],
        "properties": {
          "rubrique_key": { "type": "string" },
          "exercice":     { "type": "integer" },
          "top_n":        { "type": "integer", "default": 10 }
        }
      }
    },
    {
      "name": "get_waterfall",
      "description": "Retourne une cascade ordonnée (ex: CP → endettement brut → trésorerie → endettement net).",
      "input_schema": {
        "type": "object",
        "required": ["waterfall_key", "exercice"],
        "properties": {
          "waterfall_key":      { "type": "string" },
          "exercice":           { "type": "integer" },
          "include_cca_as_qfp": { "type": "boolean", "default": false }
        }
      }
    },
    {
      "name": "compare_sector",
      "description": "Compare un ratio de l'entreprise aux benchmarks BdF du secteur (médiane, Q1, Q3).",
      "input_schema": {
        "type": "object",
        "required": ["ratio_key", "exercice"],
        "properties": {
          "ratio_key": { "type": "string" },
          "exercice":  { "type": "integer" },
          "naf_code":  { "type": "string", "default": "auto" }
        }
      }
    },
    {
      "name": "get_sig",
      "description": "Retourne les Soldes Intermédiaires de Gestion.",
      "input_schema": {
        "type": "object",
        "required": ["exercice"],
        "properties": { "exercice": { "type": "integer" } }
      }
    }
  ],

  "response": {
    "allowed_blocks": ["text", "table", "chart", "metric_card", "alert", "waterfall_card", "sector_gauge"],
    "number_format": { "locale": "fr-FR", "currency": "EUR" }
  },

  "security": {
    "allowed_tables": ["fec"],
    "block_patterns": ["DROP", "DELETE", "INSERT", "UPDATE", "TRUNCATE", "UNION SELECT", "--", "/*"],
    "max_query_timeout_ms": 5000
  }
}
```

---

## PCGSemanticLayer — Dual-Path Pattern

Pattern emprunté à Wren AI : le modèle sémantique a deux chemins distincts.

```
mdl_manifest.json + ontology/ + ratios.json
         │
         ▼
PCGSemanticLayer.__init__()
   ├─ _index_concepts()     ← from ontology/concepts.json
   ├─ _index_expressions()  ← from semantic/mdl_manifest.json
   └─ _index_metrics()      ← from metrics/ratios.json
         │
         ├─── DEPLOY PATH (exécution de requêtes)
         │    build_rubrique_sql()   → SQL paramétré depuis l'expression MDL
         │    build_trend_sql()      → GROUP BY exercice/mois
         │    build_breakdown_sql()  → top-N sous-comptes
         │    build_waterfall_sql()  → multi-rubrique ordonné
         │    evaluate_alerts()      → check seuils depuis ratios.json
         │    evaluate_sector()      → positionnement vs benchmarks BdF
         │
         └─── INDEX PATH (résolution sémantique — Phase 2)
              index_for_vector_store() → Qdrant upsert payloads
              resolve_concept()        → Phase 1: keyword  |  Phase 2: vector search
```

**Deploy path** — Le SQL builder. Prend une `rubrique_key`, lit le champ `expression` du `mdl_manifest.json`, filtre par `exercice`, exécute via DuckDB. Le LLM ne touche jamais à ce chemin.

**Index path** — Pour `resolve_concept()`. En Phase 1, matching par mots-clés sur les labels et tags des concepts. En Phase 2, remplacé par une recherche vectorielle Qdrant sur des documents construits par `index_for_vector_store()`.

---

## LangGraph Runtime — Graph Nodes

```
START
  │
  ▼
[context_builder]
  Reads: user_message, chat_history
  Does:  loads company profile (NAF, exercice, forme juridique)
         loads sector_profile → active/disabled concepts
         calls PCGSemanticLayer.resolve_concept() pour les termes du message
         builds compact domain_context (ontology snapshot for planner)
  Output: domain_context, relevant_concepts, company_profile, sector_profile → AgentState
  │
  ▼
[planner]
  Receives: domain_context (labels + rubrique_keys actifs pour le secteur)
            tool schemas from agent_spec
            company profile (NAF 96.02A, exercice 2025)
            chat history (last N turns)
  LLM outputs: JSON Plan only (response_format: json_object)
               never SQL, never column names
  Output: Plan { reasoning, steps[], expected_output_type } → AgentState
  │
  ▼
[executor]  ← boucle un step à la fois
  Pour chaque step :
    1. Valider args contre tool input_schema (jsonschema)
    2. Dispatcher vers le tool :
         resolve_concept  → PCGSemanticLayer.resolve_concept()
         query_rubrique   → build_rubrique_sql() → engine.fetch_one()
         query_ratio      → compute num/denom → evaluate_ratio_alert() → evaluate_sector()
         get_trend        → build_trend_sql() → engine.fetch_all()
         get_breakdown    → build_breakdown_sql() → engine.fetch_all()
         get_waterfall    → build_waterfall_sql() → multi-rubrique → cascade
         compare_sector   → load benchmarks_bdf → positionnement Q1/médiane/Q3
         get_sig          → multi-rubrique → SIG cascade
    3. Évaluer les alertes MDL sur la valeur résultat
    4. Append ToolResult to state
  │
  ▼
[router]  (conditional edge)
  ├── encore des steps dans le plan ?      → loop back to executor
  ├── erreur tool + replans restants ?     → replanner
  ├── résultat vide + on_empty=stop ?      → synthesizer (avec état vide)
  └── tous les steps terminés ?            → synthesizer
  │
  ▼
[replanner]  (uniquement sur erreur/vide)
  Receives: question originale + tool_results so far + error_context
  LLM outputs: JSON Plan révisé
  Incrémente replan_count → si > max_replans → force synthesizer
  │
  ▼
[synthesizer]
  Receives: tous les tool_results, alertes MDL, positionnement sectoriel
  LLM formats: response_blocks[] selon allowed_blocks de agent_spec
  Block types: metric_card | table | chart | alert | text | waterfall_card | sector_gauge
  Output: final_answer + response_blocks → AgentState
  │
  ▼
END → API response
```

---

## AgentState — Typed State Object

```python
class AgentState(BaseModel):
    # ── Inputs ─────────────────────────────────────────
    session_id:       str
    user_message:     str
    chat_history:     list[dict] = []

    # ── Config (chargé une fois au démarrage) ──────────
    agent_spec:       dict = {}
    company_profile:  dict = {}   # naf_code, exercice_courant, forme_juridique, date_creation
    sector_profile:   dict = {}   # active_concepts, disabled_concepts, key_ratios

    # ── Contexte sémantique (construit par context_builder) ──
    domain_context:      dict = {}   # snapshot ontologie compact pour le planner
    relevant_concepts:   list = []   # définitions de concepts résolus pour cette requête

    # ── Runtime ────────────────────────────────────────
    plan:              Optional[Plan] = None
    current_step_idx:  int = 0
    tool_results:      list[ToolResult] = []
    replan_count:      int = 0
    error_context:     Optional[str] = None

    # ── Output ─────────────────────────────────────────
    response_blocks:   list[dict] = []
    final_answer:      Optional[str] = None
    alerts:            list[dict] = []   # alertes MDL (seuils franchis)
    sector_positions:  list[dict] = []   # positionnements vs benchmarks BdF
```

---

## Wren AI Patterns

| Concept Wren AI | Comment on l'applique |
|---|---|
| **MDL `models[]`** avec champs calculés | `mdl_manifest.json` — colonnes avec `isCalculated + expression` — chaque rubrique a son SQL ici |
| **MDL `metrics[]`** avec références formule | `metrics/ratios.json` — les ratios référencent des `rubrique_key`, pas du SQL brut |
| **Deploy path** (exécution) | `build_rubrique_sql()` compile l'expression MDL → SQL paramétré exécuté via DuckDB |
| **Index path** (résolution sémantique) | `index_for_vector_store()` → payloads Qdrant depuis les descriptions ontologie |
| **Semantic SQL rewriting** | `resolve_concept()` → Phase 1: keyword · Phase 2: Qdrant vector search |
| **`auto_filters` sur model** | Simplifié pour FEC mono-entreprise — pas de `societe_id` ni `is_valide` |
| **Relationship modeling** | `ontology/concepts.json` → `relationships.used_in_ratio`, `part_of`, `related_to` |

**Différence clé avec Wren** : Wren laisse le LLM générer du semantic SQL. Ici, le LLM ne produit qu'un **JSON plan référençant des `rubrique_key`**. Le SQL builder compile ces clés via le MDL. C'est plus strict et plus auditable — adapté aux données financières où la correction SQL est non négociable.

---

## Exemple end-to-end

**Utilisateur :** *« Montre-moi la cascade d'endettement de RD Cannes en 2025. »*

**context_builder** → `resolve_concept("cascade endettement")` → matche `waterfall_key: endettement_complet`. Charge le sector_profile 96.02A. Injecte le domain_context.

**planner** produit :
```json
{
  "reasoning": "L'utilisateur veut la cascade d'endettement complète. J'utilise get_waterfall pour l'exercice 2025, puis compare_sector pour le taux d'endettement net.",
  "steps": [
    { "id": "s1", "tool": "get_waterfall",
      "args": { "waterfall_key": "endettement_complet", "exercice": 2025, "include_cca_as_qfp": false } },
    { "id": "s2", "tool": "compare_sector",
      "args": { "ratio_key": "taux_endettement_net", "exercice": 2025 },
      "depends_on": ["s1"] }
  ],
  "expected_output_type": "waterfall_card"
}
```

**executor s1** → `build_waterfall_sql("endettement_complet", 2025)` exécute chaque rubrique de la cascade via DuckDB :
```sql
-- Pour chaque rubrique_key de la cascade :
SELECT SUM(CASE WHEN compte_prefix_2 IN ('10','11','12','13','14')
     AND compte_prefix_3 != '109' THEN credit - debit ELSE 0 END) AS valeur
FROM fec WHERE exercice = 2025
```
→ Résultat : CP = 1 100 €, Endettement brut = 92 829 €, Trésorerie active = 29 141 €, Endettement net = 63 688 €.

**executor s2** → taux_endettement_net = 57.9x → benchmarks BdF médiane = 0.5x → position = **très au-dessus du Q3 (3.0x)**. Mais `caveat_if_low_equity` se déclenche : CP = 1 100 € < seuil 10 000 € → caveat ajouté.

**synthesizer** retourne :
```json
[
  { "type": "waterfall_card", "waterfall_key": "endettement_complet",
    "sections": [ ... cascade complète avec valeurs ... ] },
  { "type": "sector_gauge", "ratio_key": "taux_endettement_net",
    "value": 57.9, "sector_median": 0.5, "q1": -0.2, "q3": 3.0,
    "position": "above_q3" },
  { "type": "alert", "level": "warning",
    "message": "CP très faibles (1 100 €) — le ratio est mécaniquement élevé sans que l'endettement soit anormalement fort." },
  { "type": "alert", "level": "info",
    "message": "Entreprise créée il y a moins de 3 ans — les benchmarks BdF sont biaisés." }
]
```

---

## Où vit chaque morceau de logique métier

| Connaissance | Fichier de config | Visible par le LLM ? |
|---|---|---|
| "Exclure 109 — CSNA non disponible" | `ontology/business_rules.json` | Comme **contexte** (compréhension) |
| `LEFT(compte,3) != '109'` condition SQL | `semantic/mdl_manifest.json` | **Jamais** — SQL builder uniquement |
| Polarité: `credit_moins_debit` pour passif | `semantic/mdl_manifest.json` | **Jamais** |
| `autonomie = fonds_propres / total_passif` | `metrics/ratios.json` | **Jamais** — l'executor calcule |
| Seuil: healthy si autonomie > 30% | `metrics/ratios.json` | Comme **bloc alert** dans la réponse |
| Label "Capitaux Propres" | `ontology/concepts.json` | Comme **vocabulaire du planner** |
| BdF médiane secteur 96.02 = 1.2x | `metrics/benchmarks_bdf.json` | Comme **bloc sector_gauge** dans la réponse |
| Concept désactivé "BFR" pour coiffure | `ontology/sector_profiles.json` | **Jamais proposé** par le planner |
| CCA reclassable en quasi-FP | `ontology/concepts.json` (reclassement) | Comme **option** présentée à l'utilisateur |
| SQL query string | Généré par `build_rubrique_sql()` | **Jamais** |

---

## Folder Structure

```
pcg_agent/
├── config/
│   ├── ontology/
│   │   ├── concepts.json              ← définitions de rubriques, synonymes, reclassements
│   │   ├── pcg_taxonomy.json          ← structure PCG classes 1→7, cascade SIG
│   │   ├── business_rules.json        ← règles de polarité, exclusions globales (109, 419, 409)
│   │   └── sector_profiles.json       ← NAF → concepts actifs/désactivés, ratios clés
│   ├── semantic/
│   │   └── mdl_manifest.json          ← expressions SQL sur colonnes FEC, macros, vues
│   ├── metrics/
│   │   ├── ratios.json                ← formules de ratios, seuils, caveats sectoriels
│   │   ├── benchmarks_bdf.json        ← données BdF par NAF (médiane, Q1, Q3)
│   │   └── waterfalls.json            ← définitions de cascades ordonnées
│   └── agent_spec.json                ← policy planner, schemas tools, guardrails, blocs réponse
│
├── ingestion/
│   └── fec_loader.py                  ← FECIngestion: xlsx/csv → DataFrame normalisé
│
├── semantic_layer/
│   └── mdl_reader.py                  ← PCGSemanticLayer: deploy path + index path
│
├── query_engine/
│   └── duckdb_engine.py               ← FECQueryEngine: DuckDB sur pandas df
│
├── graph/
│   ├── state.py                       ← AgentState, Plan, ToolResult (Pydantic)
│   ├── graph.py                       ← LangGraph StateGraph wiring + conditional edges
│   └── nodes/
│       ├── context_builder.py         ← résolution concepts + profil sectoriel
│       ├── planner.py                 ← LLM → JSON Plan
│       ├── executor.py                ← dispatch tools + alertes + comparaison sectorielle
│       ├── replanner.py               ← plan révisé sur erreur
│       └── synthesizer.py             ← LLM → response_blocks[]
│
├── tools/
│   ├── dispatcher.py                  ← _dispatch() avec checks de sécurité
│   ├── waterfall.py                   ← implémentation get_waterfall
│   └── sector_compare.py             ← implémentation compare_sector
│
└── api/
    └── routes.py                      ← POST /conversations, POST /conversations/{id}/messages
```

---

## Build Order

| Semaine | Focus | Livrable |
|---|---|---|
| 1 | Écrire tous les fichiers config JSON pour les comptes réels RD Cannes | `config/` complet et validé |
| 2 | `FECIngestion` + `DuckDB engine` + `PCGSemanticLayer` | FEC chargé, toutes les requêtes rubrique retournent les bonnes valeurs |
| 3 | `context_builder` + `planner` node | Le LLM génère des JSON plans valides pour 15 questions test |
| 4 | `executor` + `router` + `replanner` + `waterfall` + `sector_compare` | Graphe complet end-to-end |
| 5 | `synthesizer` + routes FastAPI | API de chat fonctionnelle end-to-end |
| 6 | Phase 2 : Qdrant `resolve_concept()` + hardening sécurité | Production-ready |

---

## Règles fondamentales

1. **Le LLM n'écrit jamais de SQL** — le SQL vient de `build_*_sql()` lisant `mdl_manifest.json`.
2. **La logique métier vit dans les configs, jamais dans les prompts** — les prompts référencent des rubrique_keys, pas des règles.
3. **Le FEC est la source de vérité unique** — pas de base de données intermédiaire pour le MVP.
4. **Le profil sectoriel filtre les concepts** — les concepts désactivés ne sont jamais proposés par le planner.
5. **Le CCA (455) produit toujours un double scénario** — sauf si l'utilisateur choisit explicitement un traitement.
6. **La comparaison sectorielle signale le biais de maturité** — une entreprise jeune vs des benchmarks établis.
7. **Les fichiers config sont versionnés comme du code** — source de vérité, pas de la donnée.
