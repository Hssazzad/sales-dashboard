from collections.abc import Sequence
from datetime import date

from sqlalchemy import bindparam, text
from sqlalchemy.sql import TextClause

SALES_DETAILS_QUERY = """
SELECT
    d.SALES_DATE,
    d.PRODUCT_ID,
    p.PRODUCT_NAME,
    d.PRODUCT_GROUP_ID,
    pg.PRODUCT_GROUP_NAME,
    p.BRAND_ID,
    b.BRAND_NAME,
    d.QTY,
    d.UNIT_PRICE,
    d.QTY * d.UNIT_PRICE AS AMOUNT
FROM sales_details AS d
LEFT JOIN product AS p ON p.PRODUCT_ID = d.PRODUCT_ID
LEFT JOIN product_group AS pg ON pg.PRODUCT_GROUP_ID = d.PRODUCT_GROUP_ID
LEFT JOIN brand AS b ON b.BRAND_ID = p.BRAND_ID
"""

ALL_PRODUCTS_REPORT_QUERY = """
SELECT
    p.PRODUCT_ID,
    p.PRODUCT_NAME,
    pg.PRODUCT_GROUP_NAME,
    b.BRAND_NAME,
    ROUND(SUM(d.QTY), 2) AS TOTAL_QTY,
    ROUND(SUM(d.QTY * d.UNIT_PRICE), 2) AS TOTAL_AMOUNT
FROM sales_details AS d
INNER JOIN product AS p ON p.PRODUCT_ID = d.PRODUCT_ID
LEFT JOIN product_group AS pg ON pg.PRODUCT_GROUP_ID = d.PRODUCT_GROUP_ID
LEFT JOIN brand AS b ON b.BRAND_ID = p.BRAND_ID
WHERE {where_clause}
GROUP BY
    p.PRODUCT_ID,
    p.PRODUCT_NAME,
    d.PRODUCT_GROUP_ID,
    pg.PRODUCT_GROUP_NAME,
    p.BRAND_ID,
    b.BRAND_NAME
ORDER BY TOTAL_QTY DESC, p.PRODUCT_NAME ASC
"""


def build_all_products_report_query(
    start_date: date,
    end_date: date,
    product_group_ids: Sequence[str] = (),
    brand_ids: Sequence[str] = (),
) -> tuple[TextClause, dict[str, object]]:
    conditions = ["d.SALES_DATE BETWEEN :start_date AND :end_date"]
    params: dict[str, object] = {
        "start_date": start_date,
        "end_date": end_date,
    }

    if product_group_ids:
        conditions.append("d.PRODUCT_GROUP_ID IN :product_group_ids")
        params["product_group_ids"] = list(product_group_ids)

    if brand_ids:
        conditions.append("p.BRAND_ID IN :brand_ids")
        params["brand_ids"] = list(brand_ids)

    statement = text(
        ALL_PRODUCTS_REPORT_QUERY.format(where_clause=" AND ".join(conditions))
    )

    if product_group_ids:
        statement = statement.bindparams(
            bindparam("product_group_ids", expanding=True)
        )

    if brand_ids:
        statement = statement.bindparams(bindparam("brand_ids", expanding=True))

    return statement, params
