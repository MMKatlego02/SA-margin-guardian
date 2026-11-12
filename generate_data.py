"""Step 1: generate SYNTHETIC South African used-vehicle inventory (seeded, reproducible).

Writes:
  inventory_clean.csv        300 clean rows
  inventory_sample.csv       first 15 clean rows
  inventory_messy.csv        same data with ~8% deliberate problems (plus a few extra duplicate rows)
  inventory_messy_key.csv    answer key: which row got which problem (use it to test your cleaner)

Everything here is invented. Planted effects (stated so you can disclose them):
  * Durban and Bloemfontein stock sits longer (x1.15 and x1.25 days on lot).
  * Older cars have lower list prices; acquisition cost is 78-88% of list price.
"""
from pathlib import Path

import numpy as np
import pandas as pd

import config

HERE = Path(__file__).parent
SEED = 42
N_ROWS = 300
MESSY_SHARE = 0.08

MODELS = {  # brand -> (model, low, high) list-price range in rand for a nearly-new car
    "BMW":      [("118i", 300_000, 450_000), ("320i", 380_000, 620_000),
                 ("X1 sDrive18i", 400_000, 650_000), ("X3 xDrive20d", 520_000, 850_000)],
    "Mercedes": [("A200", 330_000, 520_000), ("C200", 400_000, 650_000), ("GLC 220d", 600_000, 950_000)],
    "VW":       [("Polo Vivo", 170_000, 250_000), ("Polo", 250_000, 380_000),
                 ("T-Cross", 300_000, 450_000), ("Golf 8 TSI", 380_000, 560_000)],
    "Toyota":   [("Starlet", 200_000, 280_000), ("Corolla Cross", 330_000, 450_000),
                 ("Hilux 2.4 GD-6", 400_000, 650_000), ("Fortuner 2.8", 520_000, 750_000)],
    "Ford":     [("Figo", 150_000, 230_000), ("EcoSport", 220_000, 330_000), ("Ranger 2.0 BiTurbo", 600_000, 900_000)],
    "Hyundai":  [("i20", 230_000, 330_000), ("Creta", 330_000, 480_000), ("Tucson", 400_000, 600_000)],
    "Kia":      [("Picanto", 170_000, 240_000), ("Seltos", 330_000, 470_000), ("Sportage", 450_000, 650_000)],
    "Nissan":   [("Magnite", 200_000, 260_000), ("Qashqai", 350_000, 480_000), ("Navara", 450_000, 650_000)],
}
BRAND_P = {"Toyota": 0.20, "VW": 0.18, "Ford": 0.12, "Hyundai": 0.12,
           "BMW": 0.10, "Mercedes": 0.10, "Kia": 0.09, "Nissan": 0.09}
YEARS = np.arange(2018, 2027)
YEAR_P = np.array([0.04, 0.06, 0.08, 0.10, 0.13, 0.16, 0.19, 0.18, 0.06])
DEALER_P = [0.28, 0.20, 0.20, 0.20, 0.12]  # same order as config.DEALERS
DEALER_DAYS_FACTOR = {"Johannesburg": 1.0, "Pretoria": 1.0, "Durban": 1.15,
                      "Cape Town": 1.0, "Bloemfontein": 1.25}

COLUMNS = ["vehicle_id", "brand", "model", "year", "mileage_km", "list_price",
           "acquisition_cost", "days_on_lot", "dealer_location"]


def make_clean(rng: np.random.Generator) -> pd.DataFrame:
    brands = rng.choice(list(BRAND_P), size=N_ROWS, p=list(BRAND_P.values()))
    rows = []
    for i, brand in enumerate(brands, start=1):
        model, lo, hi = MODELS[brand][rng.integers(len(MODELS[brand]))]
        year = int(rng.choice(YEARS, p=YEAR_P))
        age = max(config.AS_OF.year - year, 0.5)
        list_price = int(round(rng.uniform(lo, hi) * (1 - 0.06 * age) / 1000) * 1000 - 100)  # e.g. 289 900
        mileage = int(max(800, rng.normal(15_000, 4_500) * age) // 100 * 100)
        acquisition = int(round(list_price * rng.uniform(0.78, 0.88), -2))
        dealer = str(rng.choice(config.DEALERS, p=DEALER_P))
        days = int(np.clip(rng.gamma(2.0, 26.0) * DEALER_DAYS_FACTOR[dealer], 3, 240))
        rows.append([f"VID-{i:04d}", brand, model, year, mileage, list_price, acquisition, days, dealer])
    return pd.DataFrame(rows, columns=COLUMNS)


def make_messy(clean: pd.DataFrame, rng: np.random.Generator):
    """Return (messy_df, key_df). All values are strings, like a real CSV export."""
    df = clean.astype(str).copy()
    plan = {"extra_spaces": 6, "case_mismatch": 5, "duplicate_id": 4,
            "missing_mileage": 3, "negative_value": 3, "text_in_numeric": 3}
    n_bad = sum(plan.values())  # 24 = 8% of 300
    pool = list(rng.permutation(len(df))[:n_bad])
    take = lambda k: [pool.pop() for _ in range(k)]
    key = []

    def log(i, problem, col, new):
        key.append({"vehicle_id": clean.at[i, "vehicle_id"], "problem": problem, "column": col,
                    "original": str(clean.at[i, col]) if col else "", "messy": new})

    for i in take(plan["extra_spaces"]):          # leading / trailing / double inner spaces
        col = str(rng.choice(["brand", "model", "dealer_location"]))
        v = df.at[i, col]
        style = int(rng.integers(3))
        new = f"  {v}" if style == 0 else f"{v}  " if style == 1 else (v.replace(" ", "  ") if " " in v else f"{v} ")
        df.at[i, col] = new
        log(i, "extra_spaces", col, repr(new))

    for i in take(plan["case_mismatch"]):         # vw vs VW, DURBAN vs Durban
        col = str(rng.choice(["brand", "dealer_location"]))
        v = df.at[i, col]
        new = v.lower() if rng.integers(2) == 0 else v.upper()
        if new == v:
            new = v.lower()
        df.at[i, col] = new
        log(i, "case_mismatch", col, new)

    for i in take(plan["missing_mileage"]):       # blank or N/A
        new = "" if rng.integers(2) == 0 else "N/A"
        df.at[i, "mileage_km"] = new
        log(i, "missing_mileage", "mileage_km", repr(new))

    for col, i in zip(["days_on_lot", "list_price", "mileage_km"], take(plan["negative_value"])):
        new = "-" + df.at[i, col]
        df.at[i, col] = new
        log(i, "negative_value", col, new)

    text_fix = {                                   # one repairable list_price, one repairable mileage, one hopeless days
        "list_price": lambda v: "R " + f"{int(v):,}".replace(",", " "),
        "mileage_km": lambda v: f"{int(v):,} km",
        "days_on_lot": lambda v: "TBC",
    }
    for col, i in zip(text_fix, take(plan["text_in_numeric"])):
        new = text_fix[col](df.at[i, col])
        df.at[i, col] = new
        log(i, "text_in_numeric", col, new)

    dup_src = take(plan["duplicate_id"])           # first 2: exact copies; last 2: stale snapshot (fewer days_on_lot)
    dups = []
    for n, i in enumerate(dup_src):
        row = df.loc[i].copy()
        if n >= 2:
            row["days_on_lot"] = str(max(int(row["days_on_lot"]) - 14, 0))
        dups.append(row)
        log(i, "duplicate_id_exact" if n < 2 else "duplicate_id_conflicting", "", "")

    out = df.reset_index(drop=True)
    for row in dups:                               # drop each copy into a random later position
        pos = int(rng.integers(1, len(out)))
        out = pd.concat([out.iloc[:pos], row.to_frame().T, out.iloc[pos:]], ignore_index=True)
    return out, pd.DataFrame(key)


def main() -> None:
    rng = np.random.default_rng(SEED)
    clean = make_clean(rng)
    messy, key = make_messy(clean, rng)
    clean.to_csv(HERE / "inventory_clean.csv", index=False)
    clean.head(15).to_csv(HERE / "inventory_sample.csv", index=False)
    messy.to_csv(HERE / "inventory_messy.csv", index=False)
    key.to_csv(HERE / "inventory_messy_key.csv", index=False)
    print(f"clean: {len(clean)} rows | messy: {len(messy)} rows | problems planted: {len(key)}")


if __name__ == "__main__":
    main()
