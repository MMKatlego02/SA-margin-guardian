"""Shared settings for SA_Margin_Guardian v2.0. Change assumptions here, nowhere else."""
from datetime import date

AS_OF = date(2026, 11, 8)        # inventory snapshot date (days_on_lot is measured up to this day)
HOLDING_COST_PER_DAY = 350.0     # rand per vehicle per day: from the project brief, NOT from a public source (dealer-internal figure)
FLOORPLAN_SPREAD_PCT = 0.0       # floorplan rate = SARB prime + this spread (set to your dealer group's real spread if known)
THRESHOLD_PCT = 4.0              # flag a vehicle if projected gross margin is below this %
AUCTION_MIN_DAYS = 120           # loss-making AND at least this old -> SEND TO AUCTION

# Yearly depreciation rates. NO consistent public SA source exists for all 8 brands (TransUnion book values are paid).
#   Six brands: values from the original project brief, not from a public source.
#   Kia and Nissan: ASSUMED.
#   Partial public cross-check (Cars.co.za article, 1 Nov 2024, "indicative" brand averages): Toyota 6.8%, Ford 9.1%
#   per year. These are LOWER than the 12% / 16% used below, so the model may overstate depreciation. Not applied.
DEPRECIATION = {
    "BMW": 0.20, "Mercedes": 0.18, "VW": 0.15, "Toyota": 0.12,
    "Ford": 0.16, "Hyundai": 0.14,
    "Kia": 0.15,      # assumed
    "Nissan": 0.16,   # assumed
}

DEALERS = ["Johannesburg", "Pretoria", "Durban", "Cape Town", "Bloemfontein"]
