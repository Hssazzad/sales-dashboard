# PROJECT CONTEXT (read this first, before any task)

## Rules for the AI agent
1. Read this whole file before starting any task.
2. This is a production Streamlit + MySQL app. Never edit, move or delete existing pages, tables or reports unless I explicitly ask. Never create duplicate logic: check reports/engine.py and src/report_helpers.py first and reuse them.
3. Never run write queries or migrations. Use SELECT, SHOW and DESCRIBE only, unless I explicitly approve.
4. Audit or read-only tasks must not change any file.
5. Always finish a task by listing the exact files and lines you changed.
6. After finishing a task, update the "Status" section of this file.

## Project
- Path: project root
- Stack: Streamlit, Python, MySQL, pandas. Run: streamlit run app.py (from the sales_forecast folder, venv activated).
- Business: printer and ink company. Reports must work for BOTH the live MySQL data and uploaded CSV files.

## Architecture
- reports/engine.py: shared report registry plus every report render function. render_reports(df, key_prefix, section) builds a dropdown from the columns present and renders only the selected section.
- reports/mysql_source.py: load_sales_df(start_date, end_date) returns the standard dataframe from MySQL; customer loaders add customer sales and one-row-per-customer due data.
- pages/reports.py: live MySQL reports page (date range plus dropdown).
- pages/csv_analysis.py: thin page. Upload a CSV, auto-detect columns, rename to the standard schema, auto-save as "<file name> - <upload date>", then render_reports(df, "csv", selected_section).
- pages/equivalent_models.py is the Equivalent Models sidebar page (card design).
- src/report_helpers.py: shared helpers (add_profit_columns, get_return_summary). Reuse them.
- Old pages (admin_summary, dashboard, sales, sales_report, stock_buying, return_report, profit_report) stay untouched.
- Standard schema (all optional): product_name, quantity, sales_amount, date, product_group, brand, stock_quantity, cost, profit, returns, customer, invoice, due, paid.

## Design decisions (already agreed)
- No required columns. A report appears in the dropdown only if the columns it needs exist (is_mapped). Missing columns never cause an error and never raise KeyError.
- If no report can be built at all: st.error("No data in CSV file").
- Numeric columns go through to_number() (Bengali digits, commas, currency symbols, text like "pcs").
- Each report render is wrapped in try/except so one bad report never crashes the page.
- Reports must not duplicate the old pages. Admin Summary already exists as a sidebar page, so it must NOT be in the Reports dropdown.
- Forecast uses only COMPLETE months. Default date range on the Reports page should be 12 months.
- Due is stored as a CUSTOMER-LEVEL balance in cs.BALANCE, with collections in collection.AMOUNT. Invoice-level due cannot be calculated. NEVER join cs.BALANCE onto sales rows (it multiplies due by the number of rows). Use a separate one-row-per-customer loader.
- Missing KYC fields (owner, NID, trade licence, TIN, city/area) do not exist in the database.

## The boss's 14 requested reports (WhatsApp list)
1. Peak period of product sell
2. Customer for/against product
3. Printer to ink dependent, and ink to printer dependent
4. New product and printer and ink from website (NOT CLEAR: which website? waiting for the answer)
5. Period customer but not attained last few days (regular customers who stopped buying)
6. Customer KYC about their business
7. SMS integration
8. Warranty-based customer
9. Gift of customer, good customer
9b. (second item numbered 9) Sell decrease due to out of stock, needs analysis
10. Which model is now new in Bangladesh and is demanded
11. Same group of model is equivalent, one can use another as replacement
12. Long time in stock, which customer can buy, notifying them
13. Good customer and bad customer with long due, like long time and due more than 1/2 of the sell
14. Sales wise profit by customer

## Status
- DONE: migrated all 129 local MySQL tables and their data to TiDB Cloud sales_db; verified every table's row count matches.
- DONE: shared database connection supports local XAMPP and TiDB Cloud SSL, with settings from .env or Streamlit Secrets.
- DONE: deployment preparation — minimal requirements.txt, deployment-safe .gitignore, main branch, and GitHub push.
- DONE in engine.py: 1, 2, 3, 5, 9, 9b, 12 (without notify), 14. For CSV they work. For live MySQL, the customer/invoice reports need customer and invoice columns added to mysql_source.py (not done yet).
- DONE: customer sidebar page, customer-section filtering, MySQL customer sales/due loaders, good-vs-bad customer scoring, and warranty customers (item 8).
- DONE: item 11 (equivalent models using shared model codes in product names; no mapping table).
- DONE: item 10 as an internal proxy (new and rising products from own sales); real market data is not available.
- DONE: item 6 as a read-only profile from cs (customer data is maintained in another system; no edit form or new columns).
- MISSING: 4 (website, unclear), 7 (SMS), 12 notify (needs SMS).
- Known issues: Forecast "Buy" table was empty (partial current month, short date range). Duplicate stock_quantity column fixed; stock is taken once per product. Duplicate stock_quantity column fixed on Equivalent Models, stock is taken once per product (MAX, not SUM). Duplicate stock_quantity column fixed in the equivalents table (stock is MAX per product, not SUM).
- Duplicate logic exists (profit calculated in several places, product rankings, stock and dead-stock logic, return aggregation, formatting helpers). Cleanup is planned for LAST. Do not clean up unless asked.

## Next steps (in this order)
1. Fix Forecast (complete months only, 12-month default range).
2. Then phase 2: 8 warranty, 11 equivalent models, 12 notify, 7 SMS, 6 KYC.
3. Last: duplicate cleanup.

After creating the file, reply only with "PROJECT_CONTEXT.md created".
