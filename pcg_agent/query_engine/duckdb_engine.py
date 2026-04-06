"""L1 — DuckDB Query Engine: runs SQL directly on the FEC pandas DataFrame."""

import duckdb
import pandas as pd


class FECQueryEngine:
    """Executes SQL queries on the FEC DataFrame via DuckDB (zero-copy).

    DuckDB can query a pandas DataFrame as if it were a database table,
    without copying the data. We register the DataFrame as table 'fec'
    and run standard SQL against it.
    """

    def __init__(self, df: pd.DataFrame):
        self.conn = duckdb.connect()
        self.conn.register("fec", df)

    def fetch_one(self, sql: str) -> dict:
        """Execute SQL and return the first row as a dict.

        Args:
            sql: SQL query string (SELECT only).

        Returns:
            Dict of column_name -> value for the first row, or empty dict.
        """
        result = self.conn.execute(sql).fetchdf()
        if len(result) > 0:
            return result.iloc[0].to_dict()
        return {}

    def fetch_all(self, sql: str) -> list[dict]:
        """Execute SQL and return all rows as a list of dicts.

        Args:
            sql: SQL query string (SELECT only).

        Returns:
            List of dicts, one per row.
        """
        return self.conn.execute(sql).fetchdf().to_dict("records")

    def fetch_df(self, sql: str) -> pd.DataFrame:
        """Execute SQL and return result as a DataFrame."""
        return self.conn.execute(sql).fetchdf()
