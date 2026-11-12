"""Run every query in queries.sql against margin.db and print the results (no SQLite tool needed)."""
import sqlite3
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
sql = (HERE / "queries.sql").read_text(encoding="utf-8")
with sqlite3.connect(HERE / "margin.db") as con:
    for block in [b.strip() for b in sql.split(";") if b.strip()]:
        title = block.splitlines()[0] if block.startswith("--") else "query"
        print("\n" + title)
        print(pd.read_sql(block, con).to_string(index=False))
