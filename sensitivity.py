"""Step 3c: sensitivity of flagged count and at-risk rand to prime, holding cost and threshold.

Run margin_guardian.py first (it creates margin.db). Then:  python sensitivity.py
Writes sensitivity.csv (36 rows) and prints a compact table: "flagged / at-risk rand".
"""
import sqlite3
from datetime import datetime
from itertools import product
from pathlib import Path

import pandas as pd

import config
from margin_guardian import compute_margins

HERE = Path(__file__).parent
PRIME_SHIFTS = [-1.0, 0.0, 1.0]                                        # percentage points
HOLDING_COSTS = [config.HOLDING_COST_PER_DAY + d for d in (-50, 0, 50)]  # rand per day
THRESHOLDS = [3.0, 4.0, 5.0, 6.0]                                      # percent margin


def main() -> None:
    with sqlite3.connect(HERE / "margin.db") as con:
        vehicles = pd.read_sql("SELECT vehicle_id, brand, list_price, acquisition_cost, days_on_lot FROM vehicle_margins", con)
        pr = pd.read_sql("SELECT effective_date, prime_rate_pct FROM prime_rates", con)
        params = dict(pd.read_sql("SELECT key, value FROM run_params", con).to_numpy())
    prime = pd.Series(pr["prime_rate_pct"].to_numpy(), index=pd.to_datetime(pr["effective_date"]))
    as_of = datetime.strptime(params["as_of"], "%Y-%m-%d").date()

    rows = []
    for shift, hold, thr in product(PRIME_SHIFTS, HOLDING_COSTS, THRESHOLDS):
        r = compute_margins(vehicles, prime, as_of, prime_shift=shift, holding_cost=hold, threshold_pct=thr)
        rows.append({"prime_shift_pt": shift, "holding_cost": hold, "threshold_pct": thr,
                     "flagged": int(r["flagged"].sum()), "at_risk_rand": round(float(r["at_risk_rand"].sum()))})
    grid = pd.DataFrame(rows)
    grid.to_csv(HERE / "sensitivity.csv", index=False)

    grid["cell"] = grid["flagged"].astype(str) + " / R" + (grid["at_risk_rand"] / 1e6).map("{:.2f}m".format)
    wide = grid.pivot_table(index=["prime_shift_pt", "holding_cost"], columns="threshold_pct", values="cell", aggfunc="first")
    wide.columns = [f"threshold {c:g}%" for c in wide.columns]
    print(f"{len(vehicles)} vehicles. Base case: prime +0.0, holding R{config.HOLDING_COST_PER_DAY:.0f}, threshold {config.THRESHOLD_PCT:g}%\n")
    print(wide.to_string())
    print("\nSaved sensitivity.csv")


if __name__ == "__main__":
    main()
