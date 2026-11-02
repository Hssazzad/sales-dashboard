from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from src.db import get_engine
PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DATA = PROJECT_ROOT / "frontend" / "src" / "data" / "dashboard-data.ts"

SALES_QUERY = """
SELECT
    d.SALES_DATE,
    d.SALES_ID,
    d.STORE_ID,
    d.TIMESTAMP,
    d.QTY,
    d.UNIT_PRICE,
    d.QTY * d.UNIT_PRICE AS AMOUNT,
    d.PRODUCT_GROUP_ID,
    pg.PRODUCT_GROUP_NAME,
    p.BRAND_ID,
    b.BRAND_NAME
FROM sales_details AS d
LEFT JOIN product_group AS pg ON pg.PRODUCT_GROUP_ID = d.PRODUCT_GROUP_ID
LEFT JOIN product AS p ON p.PRODUCT_ID = d.PRODUCT_ID
LEFT JOIN brand AS b ON b.BRAND_ID = p.BRAND_ID
"""

BUCKETS = [
    {"id": "consumables", "name": "Consumables", "color": "#7CFF5B", "ink": "dark"},
    {"id": "hardware", "name": "Hardware", "color": "#8B3DFF", "ink": "light"},
    {"id": "parts", "name": "Parts & service", "color": "#FFB800", "ink": "dark"},
    {"id": "other", "name": "Other", "color": "#FF5A1F", "ink": "dark"},
]


def load_sales() -> pd.DataFrame:
    engine = get_engine()
    with engine.connect() as connection:
        df = pd.read_sql_query(text(SALES_QUERY), connection)
    df["SALES_DATE"] = pd.to_datetime(df["SALES_DATE"]).dt.normalize()
    df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"], errors="coerce")
    df["AMOUNT"] = pd.to_numeric(df["AMOUNT"], errors="coerce").fillna(0.0)
    df["QTY"] = pd.to_numeric(df["QTY"], errors="coerce").fillna(0.0)
    df["SALES_ID"] = df["SALES_ID"].astype("string")
    df["STORE_ID"] = df["STORE_ID"].astype("string")
    return df


def pct(current: float, previous: float) -> str:
    if previous == 0:
        return "0.0%" if current == 0 else "100.0%"
    return f"{(current - previous) / previous * 100:.1f}%"


def money(value: float) -> str:
    return f"৳{value:,.0f}"


def clean_group_name(value: object) -> str:
    name = re.sub(r"\s+", " ", str(value)).strip().title()
    return name.replace("( ", "(").replace(" )", ")")


def bucket_for(group_name: str) -> str:
    name = group_name.upper()
    if any(key in name for key in ("SPARE PARTS", "PRINT HEAD", "MOTOR", "CHIP", "SOFTWEAR")):
        return "parts"
    if any(key in name for key in ("PRINTER", "SCANNER", "PROJECTOR", "LAMINATOR", "HEAT PRESS", "CAMEO", "XEROX")):
        return "hardware"
    if any(key in name for key in ("TONER", "INK", "PAPER", "RIBBON", "POWDER", "SUBLIMATION", "DTF")):
        return "consumables"
    return "other"


def main() -> None:
    df = load_sales()
    if df.empty:
        raise RuntimeError("sales_details is empty; cannot build the dashboard snapshot.")

    max_date = df["SALES_DATE"].max().normalize()
    min_date = df["SALES_DATE"].min().normalize()

    def mask(days_from: int, days_to: int) -> pd.Series:
        start = max_date - pd.Timedelta(days=days_from)
        end = max_date - pd.Timedelta(days=days_to)
        return (df["SALES_DATE"] >= start) & (df["SALES_DATE"] <= end)

    m30 = mask(29, 0)
    p30 = mask(59, 30)
    m7 = mask(6, 0)
    p7 = mask(13, 7)
    m365 = mask(364, 0)
    p365 = mask(729, 365)

    def revenue(selection: pd.Series) -> float:
        return float(df.loc[selection, "AMOUNT"].sum())

    def units(selection: pd.Series) -> float:
        return float(df.loc[selection, "QTY"].sum())

    current_revenue = revenue(m30)
    previous_revenue = revenue(p30)
    current_orders = int(df.loc[m30, "SALES_ID"].nunique())
    avg_order = current_revenue / current_orders if current_orders else 0.0

    series = []
    for day in pd.date_range(max_date - pd.Timedelta(days=29), max_date, freq="D"):
        day_revenue = float(df.loc[df["SALES_DATE"] == day, "AMOUNT"].sum())
        series.append({"label": f"{day:%b} {day.day}", "value": round(day_revenue)})

    revenue_start = max_date - pd.Timedelta(days=29)
    revenue_card = {
        "label": "Revenue",
        "value": round(current_revenue),
        "delta": pct(current_revenue, previous_revenue),
        "note": f"Avg. order {money(avg_order)}",
        "caption": f"Last 30 days · {revenue_start:%b} {revenue_start.day} – {max_date:%b} {max_date.day}",
        "series": series,
    }

    current_units = units(m30)
    previous_units = units(p30)
    store_series: dict[str, list[list[int]]] = {}
    for store_id in ("STO001", "STO002"):
        weeks: list[list[int]] = []
        for week in range(3):
            start = max_date - pd.Timedelta(days=6 + 7 * week)
            end = start + pd.Timedelta(days=6)
            subset = df[
                (df["SALES_DATE"] >= start)
                & (df["SALES_DATE"] <= end)
                & (df["STORE_ID"] == store_id)
            ]
            hours = subset["TIMESTAMP"].dt.hour.dropna().astype(int)
            if hours.empty and not subset.empty:
                hours = pd.Series([12] * len(subset), index=subset.index)
            counts = hours.value_counts().reindex(range(24), fill_value=0).astype(int).tolist()
            weeks.append(counts)
        store_series[store_id] = weeks

    sessions_card = {
        "label": "Units sold",
        "value": round(current_units),
        "delta": pct(current_units, previous_units),
        "note": "By hour, last 3 weeks",
        "desktop": store_series["STO001"],
        "mobile": store_series["STO002"],
        "labels": {
            "desktop": "Main store",
            "mobile": "Showroom",
            "prior": "Prior weeks",
            "current": "this week",
        },
    }

    def group_sums(selection: pd.Series) -> pd.Series:
        return (
            df.loc[selection]
            .groupby(["PRODUCT_GROUP_ID", "PRODUCT_GROUP_NAME"], dropna=False)["AMOUNT"]
            .sum()
        )

    group_table = pd.concat(
        [
            group_sums(m7).rename("w1"),
            group_sums(p7).rename("w0"),
            group_sums(m30).rename("m1"),
            group_sums(p30).rename("m0"),
            group_sums(m365).rename("y1"),
            group_sums(p365).rename("y0"),
        ],
        axis=1,
    ).fillna(0.0)
    group_table = group_table.reset_index()
    group_table = group_table[group_table["PRODUCT_GROUP_NAME"].notna()]
    group_table = group_table[
        (group_table["w1"] > 0) & (group_table["m1"] > 0) & (group_table["y1"] > 0)
    ]
    group_table = group_table.sort_values("m1", ascending=False).head(6)

    used_buckets: list[str] = []
    items = []
    for _, row in group_table.iterrows():
        name = clean_group_name(row["PRODUCT_GROUP_NAME"])
        bucket = bucket_for(name)
        if bucket not in used_buckets:
            used_buckets.append(bucket)
        items.append(
            {
                "name": name,
                "group": bucket,
                "values": [round(row["w1"]), round(row["m1"]), round(row["y1"])],
            }
        )

    groups = [bucket for bucket in BUCKETS if bucket["id"] in used_buckets]

    def brand_sums(selection: pd.Series) -> pd.Series:
        return (
            df.loc[selection]
            .groupby("BRAND_NAME", dropna=False)["AMOUNT"]
            .sum()
        )

    brand_table = pd.concat(
        [
            brand_sums(m7).rename("w1"),
            brand_sums(m30).rename("m1"),
            brand_sums(m365).rename("y1"),
        ],
        axis=1,
    ).fillna(0.0)
    brand_table = brand_table.reset_index()
    brand_table = brand_table[brand_table["BRAND_NAME"].notna()]
    brand_table = brand_table.sort_values("m1", ascending=False).head(3)

    prior_start = max_date - pd.Timedelta(days=729)
    prior_end = max_date - pd.Timedelta(days=365)
    prior_days = max(0, (prior_end - max(prior_start, min_date)).days + 1)
    prior_complete = prior_days >= 365
    yearly_total = group_table["y1"].sum()
    yearly_prior = group_table["y0"].sum()

    categories_card = {
        "title": "Top product groups",
        "groups": groups,
        "periods": [
            {
                "label": "Weekly",
                "total": round(group_table["w1"].sum()),
                "delta": pct(group_table["w1"].sum(), group_table["w0"].sum()),
                "compare": f"vs {money(group_table['w0'].sum())} prior week",
            },
            {
                "label": "Monthly",
                "total": round(group_table["m1"].sum()),
                "delta": pct(group_table["m1"].sum(), group_table["m0"].sum()),
                "compare": f"vs {money(group_table['m0'].sum())} prior month",
            },
            {
                "label": "Yearly",
                "total": round(yearly_total),
                "delta": pct(yearly_total, yearly_prior) if prior_complete else "n/a",
                "compare": (
                    f"vs {money(yearly_prior)} prior 12 mo"
                    if prior_complete
                    else f"vs {money(yearly_prior)} · only {prior_days} days of data"
                ),
            },
        ],
        "items": items,
        "table": {
            "columns": ["Brand", "Weekly", "Monthly", "Yearly"],
            "rows": [
                {
                    "label": str(row["BRAND_NAME"]).strip(),
                    "values": [
                        money(row["w1"]),
                        money(row["m1"]),
                        money(row["y1"]),
                    ],
                }
                for _, row in brand_table.iterrows()
            ],
        },
    }

    monthly = df.groupby(df["SALES_DATE"].dt.to_period("M"))["AMOUNT"].sum()
    month_periods = pd.period_range(end=max_date.to_period("M"), periods=12, freq="M")
    month_values = [float(monthly.get(period, 0.0)) for period in month_periods]
    axis = [period.strftime("%b") for period in month_periods]
    season_start = month_periods[0].start_time.normalize()
    season_mask = (df["SALES_DATE"] >= season_start) & (df["SALES_DATE"] <= max_date)

    season_brands = brand_sums(season_mask).sort_values(ascending=False).head(3)
    season_total = sum(month_values)
    season_avg = season_total / len(month_values)
    best_index = month_values.index(max(month_values))
    best_value = month_values[best_index]
    low_value = min(month_values)
    low_index = month_values.index(low_value)

    seasonality_card = {
        "title": "Seasonality",
        "axis": axis,
        "years": [
            {
                "label": "2025-26",
                "values": [round(value) for value in month_values],
                "stats": [
                    {
                        "label": "Monthly avg",
                        "value": round(season_avg),
                        "delta": pct(season_avg, low_value),
                        "note": f"vs {axis[low_index]} {month_periods[low_index].year} low",
                    },
                    {
                        "label": "Best month",
                        "value": round(best_value),
                        "delta": pct(best_value, season_avg),
                        "note": f"{axis[best_index]} {month_periods[best_index].year} · vs avg",
                    },
                ],
                "rows": [
                    {"label": str(brand).strip(), "value": f"{value:,.0f}"}
                    for brand, value in season_brands.items()
                ],
            }
        ],
    }

    meta = {
        "source": "print_db",
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "dataRange": {
            "from": min_date.strftime("%Y-%m-%d"),
            "to": max_date.strftime("%Y-%m-%d"),
        },
        "totalRevenue": round(float(df["AMOUNT"].sum())),
        "totalRows": int(len(df)),
        "totalOrders": int(df["SALES_ID"].nunique()),
        "currency": "৳",
    }

    payload = {
        "revenue": revenue_card,
        "sessions": sessions_card,
        "categories": categories_card,
        "seasonality": seasonality_card,
    }

    output = (
        'import type { AnalyticsBentoProps } from "@/components/ui/analytics-bento";\n\n'
        "export type DashboardData = Pick<\n"
        '  AnalyticsBentoProps,\n'
        '  "revenue" | "sessions" | "categories" | "seasonality"\n'
        ">;\n\n"
        f"export const dashboardMeta = {json.dumps(meta, ensure_ascii=False, indent=2)} as const;\n\n"
        f"export const dashboardData: DashboardData = {json.dumps(payload, ensure_ascii=False, indent=2)};\n"
    )
    FRONTEND_DATA.parent.mkdir(parents=True, exist_ok=True)
    FRONTEND_DATA.write_text(output, encoding="utf-8")

    print(f"Wrote {FRONTEND_DATA}")
    print(f"Data range: {min_date:%Y-%m-%d} -> {max_date:%Y-%m-%d}")
    print(f"Rows: {len(df):,} | Orders: {df['SALES_ID'].nunique():,} | Revenue: {df['AMOUNT'].sum():,.0f}")
    print(f"Revenue 30d: {current_revenue:,.0f} ({revenue_card['delta']})")
    print(f"Units 30d: {current_units:,.0f} ({sessions_card['delta']})")
    print(f"Groups: {[item['name'] for item in items]}")
    print(f"Buckets: {[group['name'] for group in groups]}")


if __name__ == "__main__":
    main()
