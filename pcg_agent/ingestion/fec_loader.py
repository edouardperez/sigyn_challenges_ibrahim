"""L0 — FEC Ingestion: loads raw FEC files into a normalized pandas DataFrame."""

from pathlib import Path

import pandas as pd


class FECIngestion:
    """Loads a raw FEC (xlsx or csv) and returns a clean, normalized DataFrame.

    The FEC (Fichier des Ecritures Comptables) is the legal accounting export
    required by French tax law. Each row is one journal entry line.

    This class:
    - Maps original French column names to snake_case internal names
    - Derives fiscal year (exercice) and month (mois) from the entry date
    - Creates prefix columns (1/2/3-digit) for PCG account matching
    - Validates that total debits == total credits (accounting balance)
    """

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
        "EcritureNum": "ecriture_num",
        "PieceRef": "piece_ref",
        "PieceDate": "piece_date",
        "EcritureLet": "lettre",
        "DateLet": "date_let",
        "ValidDate": "valid_date",
        "Montantdevise": "montant_devise",
    }

    def load(self, filepath: str | Path) -> pd.DataFrame:
        """Load a FEC file and return a normalized DataFrame.

        Args:
            filepath: Path to .xlsx or .csv FEC file.

        Returns:
            Normalized DataFrame with derived columns ready for DuckDB queries.
        """
        filepath = Path(filepath)

        if filepath.suffix.lower() in (".xlsx", ".xls"):
            df = pd.read_excel(
                filepath,
                dtype={"CompteNum": str, "EcritureDate": str},
            )
        elif filepath.suffix.lower() == ".csv":
            df = pd.read_csv(
                filepath,
                dtype={"CompteNum": str, "EcritureDate": str},
                sep="\t",
                encoding="utf-8",
            )
        else:
            raise ValueError(f"Format non supporté: {filepath.suffix}")

        rename_map = {k: v for k, v in self.COLUMN_MAP.items() if k in df.columns}
        df = df.rename(columns=rename_map)

        df["ecriture_date"] = df["ecriture_date"].astype(str)
        df["exercice"] = df["ecriture_date"].str[:4].astype(int)
        df["mois"] = df["ecriture_date"].str[4:6].astype(int)

        df["numero_compte"] = df["numero_compte"].astype(str).str.strip()
        df["compte_prefix_1"] = df["numero_compte"].str[:1]
        df["compte_prefix_2"] = df["numero_compte"].str[:2]
        df["compte_prefix_3"] = df["numero_compte"].str[:3]

        df["debit"] = pd.to_numeric(df["debit"], errors="coerce").fillna(0.0)
        df["credit"] = pd.to_numeric(df["credit"], errors="coerce").fillna(0.0)

        self._validate(df)
        return df

    def _validate(self, df: pd.DataFrame) -> None:
        """Check that total debits equal total credits (basic accounting rule)."""
        total_debit = df["debit"].sum()
        total_credit = df["credit"].sum()
        diff = abs(total_debit - total_credit)
        if diff > 0.01:
            raise ValueError(
                f"Balance check failed: debit={total_debit:.2f}, "
                f"credit={total_credit:.2f}, diff={diff:.2f}"
            )

    def get_exercices(self, df: pd.DataFrame) -> list[int]:
        """Return sorted list of fiscal years present in the FEC."""
        return sorted(df["exercice"].unique().tolist())
