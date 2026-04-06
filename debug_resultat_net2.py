"""Debug: find source of 276.12 difference (2983.93 vs 2707.81)."""

import sys
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

from pcg_agent.ingestion.fec_loader import FECIngestion
from pcg_agent.query_engine.duckdb_engine import FECQueryEngine

fec_path = BASE / "FEC_blckbx_cannes_2025.xlsx"
loader = FECIngestion()
df = loader.load(fec_path)
engine = FECQueryEngine(df)

exercice = 2025
diff_target = 2983.93 - 2707.81  # = 276.12

print(f"Target difference to explain: {diff_target:.2f}")
print()

# Check if any individual accounts sum to ~276.12
sql_accounts = (
    "SELECT numero_compte, libelle_compte, "
    "SUM(credit - debit) AS net_credit, "
    "SUM(debit) AS total_debit, SUM(credit) AS total_credit, "
    "COUNT(*) AS n_rows "
    f"FROM fec WHERE exercice = {exercice} "
    "AND LEFT(numero_compte, 1) IN ('6', '7') "
    "GROUP BY numero_compte, libelle_compte "
    "ORDER BY numero_compte"
)
print("=== All class 6/7 accounts ===")
all_rows = engine.fetch_all(sql_accounts)
for row in all_rows:
    flag = " <-- ~276?" if abs(abs(row['net_credit']) - 276.12) < 1 else ""
    print(f"  {row['numero_compte']:10s} {row.get('libelle_compte',''):40s} "
          f"debit={row['total_debit']:>12.2f}  credit={row['total_credit']:>12.2f}  "
          f"net(cr-db)={row['net_credit']:>12.2f}  rows={int(row['n_rows'])}{flag}")

# Also check: what if user mistakenly sums debit col for class 6 and credit col for class 7?
# Instead of (credit-debit) for 7 and (debit-credit) for 6
sql_naive7 = (
    f"SELECT SUM(credit) AS credit_7, SUM(debit) AS debit_7 "
    f"FROM fec WHERE exercice = {exercice} AND LEFT(numero_compte, 1) = '7'"
)
sql_naive6 = (
    f"SELECT SUM(credit) AS credit_6, SUM(debit) AS debit_6 "
    f"FROM fec WHERE exercice = {exercice} AND LEFT(numero_compte, 1) = '6'"
)
r7 = engine.fetch_one(sql_naive7)
r6 = engine.fetch_one(sql_naive6)

print(f"\n=== Raw totals ===")
print(f"Class 7: credit={r7['credit_7']:.2f}, debit={r7['debit_7']:.2f}")
print(f"Class 6: credit={r6['credit_6']:.2f}, debit={r6['debit_6']:.2f}")
print()

# Different ways to compute:
way1 = (r7['credit_7'] - r7['debit_7']) - (r6['debit_6'] - r6['credit_6'])
way2 = r7['credit_7'] - r6['debit_6']  # Naive: just credit of 7 minus debit of 6
way3 = (r7['credit_7'] + r6['credit_6']) - (r7['debit_7'] + r6['debit_6'])  # Sum all credits - sum all debits

print(f"Way 1: (cr7-db7) - (db6-cr6) = {way1:.2f}")
print(f"Way 2: credit_7 - debit_6     = {way2:.2f}")
print(f"Way 3: all_credits - all_debits = {way3:.2f}")
print()

# Check if the user's 2707.81 could come from ignoring certain sub-classes
# e.g., only counting 70-76 and 60-68 (excluding 69)
for excl in ['65', '66', '67', '68', '69', '74', '75', '76']:
    sql_without = (
        f"SELECT "
        f"SUM(CASE WHEN LEFT(numero_compte,1)='7' THEN credit-debit ELSE 0 END) - "
        f"SUM(CASE WHEN LEFT(numero_compte,1)='6' THEN debit-credit ELSE 0 END) AS net "
        f"FROM fec WHERE exercice = {exercice} "
        f"AND LEFT(numero_compte,1) IN ('6','7') "
        f"AND LEFT(numero_compte,2) != '{excl}'"
    )
    r = engine.fetch_one(sql_without)
    val = r.get('net', 0)
    flag = " <-- MATCH!" if abs(val - 2707.81) < 1 else ""
    print(f"  Excluding prefix {excl}: net = {val:>12.2f}{flag}")
