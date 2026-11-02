from pathlib import Path
import sys

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.db import get_engine

SALES_QUERY = """
SELECT
    d.SALES_DATE,
    d.PRODUCT_ID,
    p.PRODUCT_NAME, 
    d.PRODUCT_GROUP_ID,
    p.BRAND_ID,
    d.QTY,
    d.UNIT_PRICE,
    d.QTY * d.UNIT_PRICE AS AMOUNT
FROM sales_details AS d
LEFT JOIN product AS p ON p.PRODUCT_ID = d.PRODUCT_ID
"""

APPROVAL_COUNTS_QUERY = """
SELECT APPROVAL, COUNT(*) AS ROW_COUNT
FROM sales_details
GROUP BY APPROVAL
ORDER BY ROW_COUNT DESC
"""

STATUS_COUNTS_QUERY = """
SELECT STATUS, COUNT(*) AS ROW_COUNT
FROM sales_details
GROUP BY STATUS
ORDER BY ROW_COUNT DESC
"""


def load_sales_data(engine: Engine | None = None) -> pd.DataFrame:
    engine = engine or get_engine()
    df = pd.read_sql_query(text(SALES_QUERY), engine)
    df["SALES_DATE"] = pd.to_datetime(df["SALES_DATE"])
    return df


def load_approval_counts(engine: Engine | None = None) -> pd.DataFrame:
    engine = engine or get_engine()
    return pd.read_sql_query(text(APPROVAL_COUNTS_QUERY), engine)


def load_status_counts(engine: Engine | None = None) -> pd.DataFrame:
    engine = engine or get_engine()
    return pd.read_sql_query(text(STATUS_COUNTS_QUERY), engine)


if __name__ == "__main__":
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 200)

    engine = get_engine()
    df = load_sales_data(engine)

    print("df.shape:")
    print(df.shape)

    print("\ndf.head():")
    print(df.head())

    print("\ndf.dtypes:")
    print(df.dtypes)

    print("\nSALES_DATE min/max:")
    print(df["SALES_DATE"].min())
    print(df["SALES_DATE"].max())

    print("\nNULL counts per column:")
    print(df.isna().sum())

    print("\nAPPROVAL distinct values and counts:")
    print(load_approval_counts(engine))

    print("\nSTATUS distinct values and counts:")
    print(load_status_counts(engine))
