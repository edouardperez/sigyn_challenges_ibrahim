# MDL Manifest Paramétrique — Design & Implémentation

> Refactoring : numéros de compte en args → SQL builder compile → DuckDB exécute

---

## Le problème actuel

Dans le manifest v2, le SQL est écrit à la main pour chaque rubrique :

```json
{
  "name": "capitaux_propres",
  "expression": "SUM(CASE WHEN compte_prefix_2 IN ('10','11','12','13','14') AND compte_prefix_3 != '109' THEN credit - debit ELSE 0 END)"
}
```

Trois problèmes :

1. **Fragile** — les numéros de compte sont noyés dans une chaîne SQL. Changer un préfixe = éditer du SQL à la main.
2. **Non-validable** — on ne peut pas vérifier programmatiquement que les préfixes sont cohérents avec `pcg_taxonomy.json`.
3. **Non-composable** — impossible de générer dynamiquement des variantes (même rubrique, filtre sur un journal, filtre sur une période, etc.) sans dupliquer le SQL.

---

## Le nouveau design : manifest déclaratif + SQL builder

### Principe

Le manifest devient **purement déclaratif** : il décrit *quoi* agréger, pas *comment* l'écrire en SQL.
Le SQL builder (`mdl_reader.py`) prend ces déclarations et compile le SQL.

```
manifest.json (déclaratif)           mdl_reader.py (compilateur)
  rubrique_key                  →      SQL string final
  include_prefixes              →      CASE WHEN compte_prefix IN (...)
  exclude_prefixes              →      AND compte_prefix NOT IN (...)
  polarity                      →      credit - debit  OU  debit - credit
  prefix_length                 →      compte_prefix_2 OU compte_prefix_3
  conditions                    →      clauses WHERE additionnelles
  macro                         →      template expandé
```

---

## Nouveau format `mdl_manifest.json`

```json
{
  "catalog": "pcg_fec_analysis",
  "version": "3.0",

  "macros": {
    "solde_passif": {
      "description": "Solde crédit - débit pour comptes de passif.",
      "polarity": "credit_moins_debit"
    },
    "solde_actif": {
      "description": "Solde débit - crédit pour comptes d'actif.",
      "polarity": "debit_moins_credit"
    }
  },

  "models": [
    {
      "name": "FEC",
      "tableReference": "fec",
      "properties": {
        "forbidden_operations": ["INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE"],
        "exclude_journals_for_flux": ["AN"]
      },
      "columns": [
        { "name": "numero_compte",  "type": "VARCHAR", "supports_prefix_match": true },
        { "name": "exercice",       "type": "INTEGER", "filterable": true },
        { "name": "mois",           "type": "INTEGER", "filterable": true },
        { "name": "journal_code",   "type": "VARCHAR", "filterable": true },
        { "name": "debit",          "type": "DECIMAL", "aggregatable": true },
        { "name": "credit",         "type": "DECIMAL", "aggregatable": true }
      ],

      "calculatedFields": [

        {
          "rubrique_key": "capitaux_propres",
          "macro": "solde_passif",
          "include_prefixes": ["10", "11", "12", "13", "14"],
          "exclude_prefixes": ["109"],
          "prefix_match_length": 2,
          "exclude_prefix_match_length": 3,
          "note": "Capital + réserves + RAN + résultat + subventions + provisions réglementées. Exclut CSNA (109)."
        },

        {
          "rubrique_key": "capitaux_propres_appeles",
          "macro": "solde_passif",
          "include_prefixes": ["10", "11", "12", "13", "14"],
          "exclude_prefixes": ["109"],
          "prefix_match_length": 2,
          "exclude_prefix_match_length": 3,
          "note": "Identique à capitaux_propres pour l'instant — à différencier si besoin du solde 109 brut."
        },

        {
          "rubrique_key": "endettement_brut",
          "macro": "solde_passif",
          "include_prefixes": ["164", "168", "519"],
          "prefix_match_length": 3,
          "note": "Emprunts LT (164, 168) + CBC (519)."
        },

        {
          "rubrique_key": "emprunts_lt",
          "macro": "solde_passif",
          "include_prefixes": ["164", "168"],
          "prefix_match_length": 3
        },

        {
          "rubrique_key": "concours_bancaires_courants",
          "macro": "solde_passif",
          "include_prefixes": ["519"],
          "prefix_match_length": 3
        },

        {
          "rubrique_key": "disponibilites",
          "macro": "solde_actif",
          "include_prefixes": ["512", "530", "531"],
          "prefix_match_length": 3,
          "note": "Banque + Caisse, sans distinction positif/négatif."
        },

        {
          "rubrique_key": "vmp_liquides",
          "macro": "solde_actif",
          "include_prefixes": ["50"],
          "prefix_match_length": 2,
          "note": "VMP liquides — SICAV monétaires."
        },

        {
          "rubrique_key": "chiffre_affaires",
          "macro": "solde_passif",
          "include_prefixes": ["70", "71", "72"],
          "prefix_match_length": 2
        },

        {
          "rubrique_key": "masse_salariale",
          "macro": "solde_actif",
          "include_prefixes": ["64"],
          "prefix_match_length": 2,
          "note": "641 rémunérations + 645 charges sociales."
        },

        {
          "rubrique_key": "charges_interets",
          "macro": "solde_actif",
          "include_prefixes": ["661"],
          "prefix_match_length": 3
        },

        {
          "rubrique_key": "compte_courant_associes",
          "macro": "solde_passif",
          "include_prefixes": ["455"],
          "prefix_match_length": 3,
          "reclassement": "conditional"
        },

        {
          "rubrique_key": "transit_paiement",
          "macro": "solde_actif",
          "include_prefixes": ["467"],
          "prefix_match_length": 3,
          "note": "Planity/Stripe — montants en transit."
        },

        {
          "rubrique_key": "effets_encaissement",
          "macro": "solde_actif",
          "include_prefixes": ["511", "513", "514"],
          "prefix_match_length": 3
        },

        {
          "rubrique_key": "tresorerie_active",
          "macro": "composite",
          "composite_parts": [
            {
              "include_prefixes": ["512", "530", "531"],
              "prefix_match_length": 3,
              "polarity": "debit_moins_credit",
              "condition": "value_positive_only"
            },
            {
              "include_prefixes": ["50"],
              "prefix_match_length": 2,
              "polarity": "debit_moins_credit"
            }
          ],
          "note": "Disponibilités positives + VMP liquides."
        },

        {
          "rubrique_key": "tresorerie_passive",
          "macro": "composite",
          "composite_parts": [
            {
              "include_prefixes": ["519"],
              "prefix_match_length": 3,
              "polarity": "credit_moins_debit"
            },
            {
              "include_prefixes": ["512", "530", "531"],
              "prefix_match_length": 3,
              "polarity": "credit_moins_debit",
              "condition": "value_positive_only"
            }
          ],
          "note": "CBC (519) + soldes bancaires négatifs."
        },

        {
          "rubrique_key": "excedent_brut_exploitation",
          "macro": "composite",
          "composite_parts": [
            {
              "include_prefixes": ["70", "71", "72", "74"],
              "prefix_match_length": 2,
              "polarity": "credit_moins_debit"
            },
            {
              "include_prefixes": ["60", "61", "62", "63", "64"],
              "prefix_match_length": 2,
              "polarity": "debit_moins_credit",
              "sign": "negative"
            }
          ],
          "note": "Produits exploitation (70-74) - Charges exploitation (60-64)."
        },

        {
          "rubrique_key": "resultat_net",
          "macro": "composite",
          "composite_parts": [
            {
              "include_prefixes": ["7"],
              "prefix_match_length": 1,
              "polarity": "credit_moins_debit"
            },
            {
              "include_prefixes": ["6"],
              "prefix_match_length": 1,
              "polarity": "debit_moins_credit",
              "sign": "negative"
            }
          ],
          "note": "Produits (classe 7) - Charges (classe 6)."
        }

      ]
    }
  ]
}
```

---

## Le SQL Builder — `mdl_reader.py` refactorisé

```python
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional


class MDLReader:
    """
    Compile les définitions déclaratives du manifest en SQL DuckDB.
    Aucun SQL n'est jamais écrit à la main dans le manifest.
    """

    POLARITY_EXPR = {
        "credit_moins_debit": "credit - debit",
        "debit_moins_credit": "debit - credit",
    }

    def __init__(self, manifest_path: str | Path):
        with open(manifest_path) as f:
            self.manifest = json.load(f)
        self._fields: dict[str, dict] = {}
        for field in self.manifest["models"][0]["calculatedFields"]:
            self._fields[field["rubrique_key"]] = field

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_sql(
        self,
        rubrique_key: str,
        exercice: int,
        mois: Optional[int] = None,
        exclude_journals: Optional[list[str]] = None,
    ) -> tuple[str, list]:
        """
        Retourne (sql_string, params) prêts pour DuckDB execute().
        Tous les filtres sont des paramètres liés — pas d'interpolation de chaîne.
        """
        field = self._fields.get(rubrique_key)
        if not field:
            raise ValueError(f"rubrique_key inconnue : {rubrique_key!r}")

        macro = field.get("macro", "solde_passif")
        params: list = []

        if macro == "composite":
            agg_expr = self._build_composite(field["composite_parts"])
        else:
            agg_expr = self._build_simple(field, macro)

        where_clauses, params = self._build_where(
            exercice=exercice,
            mois=mois,
            exclude_journals=exclude_journals,
        )

        sql = f"SELECT {agg_expr} AS value FROM fec WHERE {' AND '.join(where_clauses)}"
        return sql, params

    def resolve_concept(self, text: str) -> Optional[str]:
        """
        Résout un label ou synonyme → rubrique_key.
        Utilisé par context_builder.py (pas par le SQL builder).
        """
        text_lower = text.lower()
        for key in self._fields:
            if text_lower in key:
                return key
        return None

    def list_rubriques(self) -> list[str]:
        return list(self._fields.keys())

    # ------------------------------------------------------------------
    # Builders internes
    # ------------------------------------------------------------------

    def _build_simple(self, field: dict, macro: str) -> str:
        """
        Compile une rubrique simple (un seul bloc CASE WHEN).
        Les numéros de compte viennent du JSON — jamais hardcodés ici.
        """
        polarity = self.manifest["macros"][macro]["polarity"]
        value_expr = self.POLARITY_EXPR[polarity]

        include = field["include_prefixes"]          # ex: ["10","11","12","13","14"]
        inc_len = field["prefix_match_length"]       # ex: 2
        exclude = field.get("exclude_prefixes", [])  # ex: ["109"]
        exc_len = field.get("exclude_prefix_match_length", inc_len + 1)

        inc_condition = self._prefix_condition(
            prefixes=include, length=inc_len, column="numero_compte", operator="IN"
        )
        exc_condition = self._prefix_condition(
            prefixes=exclude, length=exc_len, column="numero_compte", operator="NOT IN"
        ) if exclude else ""

        when_clause = inc_condition
        if exc_condition:
            when_clause += f" AND {exc_condition}"

        return f"SUM(CASE WHEN {when_clause} THEN {value_expr} ELSE 0 END)"

    def _build_composite(self, parts: list[dict]) -> str:
        """
        Compile une rubrique composite (plusieurs CASE WHEN additionnés).
        Chaque partie peut avoir sa propre polarité et ses propres conditions.
        """
        cases = []
        for part in parts:
            polarity = part["polarity"]
            value_expr = self.POLARITY_EXPR[polarity]
            sign = part.get("sign", "positive")  # "negative" → soustraction
            condition_type = part.get("condition", "")

            inc_condition = self._prefix_condition(
                prefixes=part["include_prefixes"],
                length=part["prefix_match_length"],
                column="numero_compte",
                operator="IN",
            )

            # Condition spéciale : ne compter que les soldes positifs
            if condition_type == "value_positive_only":
                case_expr = (
                    f"CASE WHEN {inc_condition} AND ({value_expr}) > 0 "
                    f"THEN {value_expr} ELSE 0 END"
                )
            else:
                case_expr = (
                    f"CASE WHEN {inc_condition} THEN {value_expr} ELSE 0 END"
                )

            if sign == "negative":
                case_expr = f"(-1 * {case_expr})"

            cases.append(case_expr)

        return f"SUM({' + '.join(cases)})"

    def _prefix_condition(
        self,
        prefixes: list[str],
        length: int,
        column: str,
        operator: str,  # "IN" ou "NOT IN"
    ) -> str:
        """
        Génère : LEFT(numero_compte, 2) IN ('10','11','12')
        Les valeurs viennent du JSON manifest — jamais d'input utilisateur.
        Pas de risque d'injection : les préfixes sont des constantes config.
        """
        # Les préfixes sont des constantes provenant du JSON config validé —
        # ils peuvent être inclus directement dans le SQL en tant que littéraux.
        # Ils ne proviennent JAMAIS d'une entrée utilisateur.
        quoted = ", ".join(f"'{p}'" for p in prefixes)
        return f"LEFT({column}, {length}) {operator} ({quoted})"

    def _build_where(
        self,
        exercice: int,
        mois: Optional[int],
        exclude_journals: Optional[list[str]],
    ) -> tuple[list[str], list]:
        """
        Construit les clauses WHERE avec paramètres liés pour exercice et mois.
        """
        clauses = ["exercice = ?"]
        params: list = [exercice]

        if mois is not None:
            clauses.append("mois = ?")
            params.append(mois)

        if exclude_journals:
            # Les codes journal sont des constantes config — pas d'input utilisateur
            quoted = ", ".join(f"'{j}'" for j in exclude_journals)
            clauses.append(f"journal_code NOT IN ({quoted})")

        return clauses, params
```

---

## Pourquoi les préfixes dans `_prefix_condition` peuvent être inline

C'est la question clé sur la sécurité SQL. Voici pourquoi c'est safe :

```
Input utilisateur (non fiable)
        │
        ▼
planner.py → produit {"rubrique_key": "capitaux_propres"}
        │
        ▼
dispatcher.py → valide "capitaux_propres" ∈ manifest_keys (whitelist)
        │
        ▼
mdl_reader.py → charge field["include_prefixes"] = ["10","11","12","13","14"]
               Ces valeurs viennent du JSON config — pas de l'utilisateur
        │
        ▼
_prefix_condition() → LEFT(numero_compte, 2) IN ('10','11','12','13','14')
```

**Les seules valeurs dynamiques (exercice, mois) sont des paramètres liés `?`.**
**Les préfixes sont des constantes de config — jamais de l'input utilisateur.**

La seule surface d'injection possible serait si quelqu'un modifiait `mdl_manifest.json` directement — ce qui est un problème de contrôle d'accès filesystem, pas un problème SQL.

---

## Comparaison avant / après

### Avant (v2 — SQL hardcodé)

```json
{
  "name": "capitaux_propres",
  "expression": "SUM(CASE WHEN compte_prefix_2 IN ('10','11','12','13','14') AND compte_prefix_3 != '109' THEN credit - debit ELSE 0 END)"
}
```

**Problèmes :**
- Changer un préfixe = modifier une chaîne SQL à la main
- Impossible de valider programmatiquement les préfixes
- Le format `compte_prefix_2` présuppose que la colonne computed existe
- `!=` vs `NOT IN` — deux syntaxes pour la même chose

### Après (v3 — déclaratif)

```json
{
  "rubrique_key": "capitaux_propres",
  "macro": "solde_passif",
  "include_prefixes": ["10", "11", "12", "13", "14"],
  "exclude_prefixes": ["109"],
  "prefix_match_length": 2,
  "exclude_prefix_match_length": 3
}
```

**Gains :**
- Les préfixes sont des données → validables, comparables, indexables
- Le SQL est généré de manière uniforme par `_prefix_condition()`
- `config_validator.py` peut vérifier que tous les préfixes sont dans les classes PCG attendues
- Ajouter un préfixe = modifier un tableau JSON, pas du SQL
- Extensible : ajouter `"valid_from_exercice": 2020` sans toucher au SQL builder

---

## Ce que `config_validator.py` peut maintenant valider

Avec le format déclaratif, le validateur peut faire des vérifications que l'ancien format SQL ne permettait pas :

```python
class ConfigValidator:

    def validate_manifest_prefixes(self):
        """Vérifie que chaque préfixe est cohérent avec pcg_taxonomy.json."""
        for field in self.manifest_fields:
            for prefix in field.get("include_prefixes", []):
                pcg_class = prefix[0]  # Premier chiffre = classe PCG
                if pcg_class not in self.taxonomy["pcg_classes"]:
                    raise ValueError(
                        f"{field['rubrique_key']}: préfixe {prefix!r} → "
                        f"classe {pcg_class!r} inconnue dans pcg_taxonomy"
                    )

    def validate_polarity_vs_taxonomy(self):
        """Vérifie que la polarité est cohérente avec le côté bilan de la classe."""
        for field in self.manifest_fields:
            macro = field.get("macro")
            if macro in ("solde_passif", "solde_actif"):
                expected_side = "passif" if macro == "solde_passif" else "actif"
                for prefix in field.get("include_prefixes", []):
                    pcg_class = prefix[0]
                    declared_side = self.taxonomy["pcg_classes"].get(pcg_class, {}).get("bilan_side")
                    if declared_side and declared_side != "both" and declared_side != expected_side:
                        raise ValueError(
                            f"{field['rubrique_key']}: préfixe {prefix!r} est classe {pcg_class} "
                            f"({declared_side}) mais macro = {macro} ({expected_side})"
                        )

    def validate_sig_cascade(self):
        """Vérifie que sig_cascade ne référence que des rubriques avec expressions."""
        manifest_keys = {f["rubrique_key"] for f in self.manifest_fields}
        for key in self.taxonomy.get("sig_cascade", []):
            if key not in manifest_keys:
                raise ValueError(f"sig_cascade référence {key!r} → absent du manifest")
```

---

## Extensibilité future — ce que le format déclaratif rend facile

### Ajouter un filtre conditionnel par exercice (ex: compte créé en 2022)

```json
{
  "rubrique_key": "nouveau_compte_2022",
  "macro": "solde_actif",
  "include_prefixes": ["xxx"],
  "prefix_match_length": 3,
  "valid_from_exercice": 2022
}
```

Le SQL builder ajoute `AND exercice >= 2022` automatiquement si le champ est présent.

### Grouper par sous-comptes pour un drill-down

```json
{
  "rubrique_key": "masse_salariale",
  "macro": "solde_actif",
  "include_prefixes": ["64"],
  "prefix_match_length": 2,
  "drill_down_length": 3
}
```

Le builder peut générer un SQL groupé par `LEFT(numero_compte, 3)` pour décomposer 641 / 645 / 648.

### Ajouter une pondération sectorielle

```json
{
  "rubrique_key": "chiffre_affaires_corrige",
  "macro": "solde_passif",
  "include_prefixes": ["70", "71", "72"],
  "prefix_match_length": 2,
  "exclude_prefixes": ["708"],
  "note": "CA hors refacturations internes (708)"
}
```

### Générer le SQL de debug pour inspection

```python
# Dans mdl_reader.py — utile pour les tests
def explain_sql(self, rubrique_key: str, exercice: int = 2024) -> dict:
    sql, params = self.build_sql(rubrique_key, exercice)
    field = self._fields[rubrique_key]
    return {
        "rubrique_key": rubrique_key,
        "macro": field.get("macro"),
        "include_prefixes": field.get("include_prefixes"),
        "exclude_prefixes": field.get("exclude_prefixes"),
        "compiled_sql": sql,
        "params": params,
    }
```

```python
# Output de explain_sql("capitaux_propres", 2024)
{
  "rubrique_key": "capitaux_propres",
  "macro": "solde_passif",
  "include_prefixes": ["10", "11", "12", "13", "14"],
  "exclude_prefixes": ["109"],
  "compiled_sql": "SELECT SUM(CASE WHEN LEFT(numero_compte, 2) IN ('10','11','12','13','14') AND LEFT(numero_compte, 3) NOT IN ('109') THEN credit - debit ELSE 0 END) AS value FROM fec WHERE exercice = ?",
  "params": [2024]
}
```
