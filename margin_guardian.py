"""SA_Margin_Guardian v2.0: clean -> log -> margin model -> CSV + SQLite.

Usage:
    python margin_guardian.py                                  # inventory_messy.csv + prime_rates.csv
    python margin_guardian.py --input inventory_clean.csv      # should log zero fixes and zero removals

Outputs (same folder): cleaning_log.csv, rejected_rows.csv, margin_results.csv, margin.db

Margin model (all per vehicle, evaluated on the snapshot date):
    projected_sale_price = list_price * (1 - yearly_depreciation * days_on_lot / 365)
    holding_cost         = HOLDING_COST_PER_DAY * days_on_lot
    floorplan_interest   = acquisition_cost * sum over each day on the lot of (prime in force that day + spread) / 365
    projected_profit     = projected_sale_price - acquisition_cost - holding_cost - floorplan_interest
    margin_pct           = 100 * projected_profit / projected_sale_price
    flagged              = margin_pct < threshold
    at_risk_rand         = if flagged: rand needed to lift profit up to the threshold margin, else 0
"""
import argparse
import re
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

import config

HERE = Path(__file__).parent
DATA_COLS = ["vehicle_id", "brand", "model", "year", "mileage_km", "list_price",
             "acquisition_cost", "days_on_lot", "dealer_location"]
NUM_COLS = ["year", "list_price", "acquisition_cost", "days_on_lot", "mileage_km"]
MISSING_TOKENS = {"", "nan", "n/a", "na", "tbc", "unknown", "none", "null", "-"}
PLAIN_NUMBER = r"-?\d+(\.\d+)?"


# ----------------------------------------------------------------------------- cleaning
def parse_number(value) -> float:
    """'R 411 900' -> 411900, '33,300 km' -> 33300, 'TBC' -> NaN. Assumes comma = thousands separator."""
    t = str(value).strip()
    if t.casefold() in MISSING_TOKENS:
        return np.nan
    t = re.sub(r"(?i)^r\s*", "", t)
    t = re.sub(r"(?i)\s*km$", "", t)
    t = t.replace(",", "").replace(" ", "")
    return float(t) if re.fullmatch(PLAIN_NUMBER, t) else np.nan


def clean(raw: pd.DataFrame, as_of: date):
    """Return (clean_df, cleaning_log_df, rejected_df). Every step logs rows_in / rows_fixed / rows_removed."""
    df = raw[DATA_COLS].copy()
    df.insert(0, "source_line", np.arange(2, len(df) + 2))   # line number in the CSV file (header = line 1)
    log, rejected, touched = [], [], set()

    def step(name, rows_in, fixed, removed, reason):
        log.append({"step": name, "rows_in": rows_in, "rows_fixed": fixed, "rows_removed": removed, "reason": reason})

    def drop(frame, mask, reason):
        for line in frame.loc[mask, "source_line"]:
            rejected.append({"source_line": int(line), "reject_reason": reason})
        return frame.loc[~mask].copy()

    # 1. whitespace
    n = len(df)
    before = df[DATA_COLS].copy()
    for c in DATA_COLS:
        df[c] = df[c].astype(str).str.strip().str.replace(r"\s+", " ", regex=True)
    changed = (df[DATA_COLS] != before).any(axis=1)
    touched |= set(df.loc[changed, "source_line"])
    step("trim_whitespace", n, int(changed.sum()), 0, "leading, trailing or repeated spaces in any column")

    # 2. brand and dealer spelling / case
    n = len(df)
    brand_map = {b.casefold(): b for b in config.DEPRECIATION}
    dealer_map = {d.casefold(): d for d in config.DEALERS}
    new_brand = df["brand"].str.casefold().map(brand_map)
    new_dealer = df["dealer_location"].str.casefold().map(dealer_map)
    unknown = new_brand.isna() | new_dealer.isna()
    changed = ~unknown & ((new_brand != df["brand"]) | (new_dealer != df["dealer_location"]))
    df["brand"], df["dealer_location"] = new_brand.where(~unknown, df["brand"]), new_dealer.where(~unknown, df["dealer_location"])
    touched |= set(df.loc[changed, "source_line"])
    df = drop(df, unknown, "brand or dealer_location not recognised")
    step("standardise_brand_dealer", n, int(changed.sum()), int(unknown.sum()),
         "case variants mapped to canonical names (vw -> VW, DURBAN -> Durban); unrecognised names removed")

    # 3. numbers stored as text
    n = len(df)
    repaired_rows = pd.Series(False, index=df.index)
    for c in NUM_COLS:
        parsed = df[c].map(parse_number)
        repaired_rows |= parsed.notna() & ~df[c].str.fullmatch(PLAIN_NUMBER)
        df[c] = parsed
    touched |= set(df.loc[repaired_rows, "source_line"])
    step("parse_numeric_text", n, int(repaired_rows.sum()), 0,
         "currency symbols, thousands separators or 'km' stripped (R 411 900 -> 411900); unreadable text -> missing")

    # 4. rows we cannot repair (key fields missing / impossible)
    n = len(df)
    missing_key = df[["year", "list_price", "acquisition_cost", "days_on_lot"]].isna().any(axis=1)
    df = drop(df, missing_key, "year, list_price, acquisition_cost or days_on_lot missing or unreadable")
    step("remove_missing_key_fields", n, 0, int(missing_key.sum()),
         "cannot guess a price or age: removed (listed in rejected_rows.csv)")

    n = len(df)
    bad = (df["list_price"] <= 0) | (df["acquisition_cost"] <= 0) | (df["days_on_lot"] < 0) \
        | (df["year"] < 1990) | (df["year"] > as_of.year)
    df = drop(df, bad, "negative/zero price or cost, negative days_on_lot, or impossible year")
    step("remove_impossible_values", n, 0, int(bad.sum()),
         "a negative price or age is a data error we cannot correct safely: removed")

    # 5. duplicates
    n = len(df)
    exact = df.duplicated(subset=DATA_COLS, keep="first")
    df = drop(df, exact, "exact duplicate of an earlier row")
    step("remove_exact_duplicates", n, 0, int(exact.sum()), "identical rows after cleaning: kept first")

    n = len(df)
    keep_idx = df.sort_values(["vehicle_id", "days_on_lot", "source_line"], ascending=[True, False, True]) \
                 .drop_duplicates("vehicle_id", keep="first").index
    conflict = ~df.index.isin(keep_idx)
    df = drop(df, conflict, "same vehicle_id, different values: kept the row with the highest days_on_lot")
    step("resolve_conflicting_ids", n, 0, int(conflict.sum()),
         "same vehicle_id with different values: kept the row with the highest days_on_lot (assumed latest snapshot)")

    # 6. mileage is not used in the margin maths, so impute instead of dropping, and flag it
    n = len(df)
    df.loc[df["mileage_km"] < 0, "mileage_km"] = np.nan
    miss = df["mileage_km"].isna()
    fill = df.groupby("year")["mileage_km"].transform("median").fillna(df["mileage_km"].median())
    df["mileage_imputed"] = miss
    df.loc[miss, "mileage_km"] = fill[miss].round(-2)
    touched |= set(df.loc[miss, "source_line"])
    step("impute_mileage", n, int(miss.sum()), 0,
         "mileage missing, unreadable or negative: median of same model year; mileage_imputed = True")

    df = df.sort_values("source_line").reset_index(drop=True)
    for c in ["year", "days_on_lot", "mileage_km"]:
        df[c] = df[c].round().astype(int)
    for c in ["list_price", "acquisition_cost"]:
        df[c] = df[c].astype(float)

    rows_fixed = len(touched & set(df["source_line"]))
    step("TOTAL", len(raw), rows_fixed, len(raw) - len(df),
         f"rows_out = {len(df)}; rows_fixed counts each kept row once (step rows can overlap)")
    rej = pd.DataFrame(rejected)
    if not rej.empty:
        rej = rej.merge(raw.assign(source_line=np.arange(2, len(raw) + 2)), on="source_line", how="left")
    return df, pd.DataFrame(log), rej


# ----------------------------------------------------------------------------- prime rates
def load_prime(path: Path, first_needed: date, as_of: date) -> pd.Series:
    """SARB prime (percent) as a step table: each row is the date a new rate took effect. Exact, no monthly averaging."""
    if not path.exists():
        sys.exit(f"Missing {path.name} (columns: effective_date, prime_rate_pct, source).")
    p = pd.read_csv(path, dtype=str, keep_default_na=False)
    if not {"effective_date", "prime_rate_pct"} <= set(p.columns):
        sys.exit(f"{path.name} must have columns: effective_date, prime_rate_pct (source is optional)")
    p["rate"] = pd.to_numeric(p["prime_rate_pct"].str.strip().str.replace("%", "", regex=False), errors="coerce")
    p["eff"] = pd.to_datetime(p["effective_date"].str.strip(), errors="coerce")
    bad = p.index[p["rate"].isna() | p["eff"].isna()]
    if len(bad):
        sys.exit(f"{path.name}: unreadable date or rate on file line(s) {[int(i) + 2 for i in bad]} (dates as YYYY-MM-DD, rates like 10.25)")
    if not p["rate"].between(3, 25).all():
        sys.exit(f"{path.name}: prime rates must be percentages like 10.25 (not 0.1025). Check the values.")
    if p["eff"].duplicated().any():
        sys.exit(f"{path.name}: the same effective_date appears twice.")
    s = p.set_index("eff")["rate"].sort_index()
    if s.index.min() > pd.Timestamp(first_needed):
        sys.exit(f"{path.name}: needs a row effective on or before {first_needed} (the oldest stock was acquired then).")
    return s


# ----------------------------------------------------------------------------- margin model
def compute_margins(df: pd.DataFrame, prime: pd.Series, as_of: date, prime_shift: float = 0.0,
                    holding_cost: float = config.HOLDING_COST_PER_DAY,
                    threshold_pct: float = config.THRESHOLD_PCT) -> pd.DataFrame:
    d = df.copy()
    days = d["days_on_lot"].round().astype(int).to_numpy()
    as_of_ts = pd.Timestamp(as_of)
    first_day = as_of_ts - pd.Timedelta(days=int(days.max()))                         # acquisition date of the oldest vehicle
    calendar = pd.date_range(first_day, as_of_ts - pd.Timedelta(days=1), freq="D")
    daily_rate = (prime.reindex(calendar, method="ffill").to_numpy() + prime_shift + config.FLOORPLAN_SPREAD_PCT) / 100 / 365
    if np.isnan(daily_rate).any():
        raise ValueError("prime table has no rate in force for the earliest days on the lot")
    cum = np.concatenate([[0.0], np.cumsum(daily_rate)])          # cum[k] = interest factor for the first k days
    end = len(calendar)
    acq_offset = end - days
    interest_factor = cum[end] - cum[acq_offset]

    d["acquisition_date"] = (as_of_ts - pd.to_timedelta(days, unit="D")).strftime("%Y-%m-%d").to_numpy()
    d["depreciation_rate"] = d["brand"].map(config.DEPRECIATION)
    d["projected_sale_price"] = d["list_price"] * (1 - d["depreciation_rate"] * days / 365)
    d["holding_cost"] = holding_cost * days
    d["floorplan_interest"] = d["acquisition_cost"] * interest_factor
    d["projected_profit"] = d["projected_sale_price"] - d["acquisition_cost"] - d["holding_cost"] - d["floorplan_interest"]
    d["margin_pct"] = 100 * d["projected_profit"] / d["projected_sale_price"]
    d["flagged"] = (d["margin_pct"] < threshold_pct).astype(int)
    shortfall = threshold_pct / 100 * d["projected_sale_price"] - d["projected_profit"]
    d["at_risk_rand"] = np.where(d["flagged"] == 1, shortfall.clip(lower=0), 0.0)
    d["recommendation"] = np.select(
        [d["flagged"] == 0, (d["projected_profit"] < 0) & (days >= config.AUCTION_MIN_DAYS)],
        ["HOLD", "SEND TO AUCTION"], default="PRICE INTERVENTION")
    return d


# ----------------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description="SA_Margin_Guardian v2.0")
    ap.add_argument("--input", default="inventory_messy.csv")
    ap.add_argument("--prime", default="prime_rates.csv")
    ap.add_argument("--as-of", default=config.AS_OF.isoformat())
    ap.add_argument("--threshold", type=float, default=config.THRESHOLD_PCT)
    a = ap.parse_args()
    as_of = datetime.strptime(a.as_of, "%Y-%m-%d").date()

    raw = pd.read_csv(HERE / a.input, dtype=str, keep_default_na=False)
    missing = [c for c in DATA_COLS if c not in raw.columns]
    if missing:
        sys.exit(f"{a.input} is missing columns: {missing}")

    clean_df, log, rejected = clean(raw, as_of)
    print("\nCLEANING LOG")
    print(log.to_string(index=False, max_colwidth=70))
    log.to_csv(HERE / "cleaning_log.csv", index=False)
    rejected.to_csv(HERE / "rejected_rows.csv", index=False)

    first_needed = as_of - timedelta(days=int(clean_df["days_on_lot"].max()))
    prime = load_prime(HERE / a.prime, first_needed, as_of)
    print("\nPRIME TABLE USED (effective date -> % p.a.)")
    print(prime.to_string())
    res = compute_margins(clean_df, prime, as_of, threshold_pct=a.threshold)

    money = ["projected_sale_price", "holding_cost", "floorplan_interest", "projected_profit", "at_risk_rand"]
    res[money] = res[money].round(2)
    res["margin_pct"] = res["margin_pct"].round(2)
    res["mileage_imputed"] = res["mileage_imputed"].astype(int)
    out_cols = DATA_COLS + ["mileage_imputed", "acquisition_date", "depreciation_rate", "projected_sale_price",
                            "holding_cost", "floorplan_interest", "projected_profit", "margin_pct",
                            "flagged", "at_risk_rand", "recommendation"]
    res[out_cols].to_csv(HERE / "margin_results.csv", index=False)

    db = HERE / "margin.db"
    with sqlite3.connect(db) as con:
        res[out_cols].to_sql("vehicle_margins", con, if_exists="replace", index=False)
        log.to_sql("cleaning_log", con, if_exists="replace", index=False)
        pd.DataFrame({"effective_date": prime.index.strftime("%Y-%m-%d"), "prime_rate_pct": prime.to_numpy()}) \
            .to_sql("prime_rates", con, if_exists="replace", index=False)
        pd.DataFrame({"key": ["as_of", "holding_cost_per_day", "floorplan_spread_pct", "threshold_pct", "input_file"],
                      "value": [as_of.isoformat(), config.HOLDING_COST_PER_DAY, config.FLOORPLAN_SPREAD_PCT,
                                a.threshold, a.input]}).astype(str).to_sql("run_params", con, if_exists="replace", index=False)

    flagged = res[res["flagged"] == 1]
    print(f"\n{len(res)} vehicles | {len(flagged)} flagged below {a.threshold}% margin | "
          f"at-risk R{res['at_risk_rand'].sum():,.0f}")
    print(res["recommendation"].value_counts().to_string())
    print(f"\nWrote cleaning_log.csv, rejected_rows.csv, margin_results.csv, {db.name}")


if __name__ == "__main__":
    main()
