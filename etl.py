"""ETL pipeline: extract raw CSVs -> validate -> clean -> validate again -> load to SQLite.

Every data-quality check runs twice (on the raw data and on the cleaned data) so the
report shows exactly which defects were found and that they were fixed.
"""
import json
import os
import sqlite3
import pandas as pd

RAW, DB, REPORT = os.path.join("data", "raw"), os.path.join("data", "warehouse.db"), os.path.join("data", "quality_report.json")
TABLES = ["customers", "products", "orders", "order_items"]


def extract():
    return {t: pd.read_csv(os.path.join(RAW, f"{t}.csv")) for t in TABLES}


# ---------------------------------------------------------------- checks
def iso_bad(s):
    """Values that are present but not in YYYY-MM-DD format."""
    s = s.dropna().astype(str)
    return int((pd.to_datetime(s, format="%Y-%m-%d", errors="coerce").isna()).sum())


def run_checks(t):
    c, p, o, i = t["customers"], t["products"], t["orders"], t["order_items"]
    od = pd.to_datetime(o["order_date"], errors="coerce")
    dd = pd.to_datetime(o["delivery_date"], errors="coerce")
    checks = [
        ("customers", "duplicate customer_id", int(c["customer_id"].duplicated().sum())),
        ("customers", "missing city", int(c["city"].isna().sum())),
        ("customers", "city not trimmed/title-cased", int((c["city"].dropna() != c["city"].dropna().str.strip().str.title()).sum())),
        ("customers", "signup_date not ISO format", iso_bad(c["signup_date"])),
        ("products", "duplicate product_id", int(p["product_id"].duplicated().sum())),
        ("products", "missing category", int(p["category"].isna().sum())),
        ("products", "price missing or <= 0", int((p["price"].isna() | (p["price"] <= 0)).sum())),
        ("orders", "duplicate order_id", int(o["order_id"].duplicated().sum())),
        ("orders", "orphan customer_id", int((~o["customer_id"].isin(c["customer_id"])).sum())),
        ("orders", "delivery_date before order_date", int((dd < od).sum())),
        ("orders", "status not lowercase/trimmed", int((o["status"] != o["status"].str.strip().str.lower()).sum())),
        ("order_items", "orphan order_id", int((~i["order_id"].isin(o["order_id"])).sum())),
        ("order_items", "orphan product_id", int((~i["product_id"].isin(p["product_id"])).sum())),
        ("order_items", "quantity <= 0", int((i["quantity"] <= 0).sum())),
        ("order_items", "unit_price missing", int(i["unit_price"].isna().sum())),
    ]
    return [{"table": a, "check": b, "failed_rows": n} for a, b, n in checks]


# ------------------------------------------------------------- transform
def transform(t):
    c, p, o, i = (t[k].copy() for k in TABLES)
    log = {}

    # customers
    c = c.drop_duplicates("customer_id")
    c["city"] = c["city"].fillna("Unknown").str.strip().str.title()
    c["signup_date"] = pd.to_datetime(c["signup_date"], format="mixed").dt.strftime("%Y-%m-%d")

    # products: invalid prices -> category median, missing category -> 'Uncategorized'
    p = p.drop_duplicates("product_id")
    p["category"] = p["category"].fillna("Uncategorized")
    p.loc[p["price"] <= 0, "price"] = float("nan")
    p["price"] = p["price"].fillna(p.groupby("category")["price"].transform("median"))
    p["price"] = p["price"].fillna(p["price"].median()).round(2)

    # orders
    o = o.drop_duplicates("order_id")
    o["status"] = o["status"].str.strip().str.lower()
    before = len(o)
    o = o[o["customer_id"].isin(c["customer_id"])]
    log["orders_dropped_orphan_customer"] = before - len(o)
    bad = pd.to_datetime(o["delivery_date"]) < pd.to_datetime(o["order_date"])
    o.loc[bad, "delivery_date"] = None
    log["delivery_dates_nulled"] = int(bad.sum())

    # order items
    before = len(i)
    i = i[i["order_id"].isin(o["order_id"]) & i["product_id"].isin(p["product_id"]) & (i["quantity"] > 0)]
    log["items_dropped_invalid"] = before - len(i)
    i = i.merge(p[["product_id", "price"]], on="product_id", how="left")
    log["unit_prices_filled"] = int(i["unit_price"].isna().sum())
    i["unit_price"] = i["unit_price"].fillna(i["price"])
    i = i.drop(columns="price").reset_index(drop=True)
    i.insert(0, "item_id", range(1, len(i) + 1))

    return {"customers": c, "products": p, "orders": o, "order_items": i}, log


# ------------------------------------------------------------------ load
def load(clean):
    if os.path.exists(DB):
        os.remove(DB)
    con = sqlite3.connect(DB)
    with open("schema.sql") as f:
        con.executescript(f.read())
    for name in TABLES:
        clean[name].to_sql(name, con, if_exists="append", index=False)
    con.execute("PRAGMA foreign_keys = ON")
    violations = con.execute("PRAGMA foreign_key_check").fetchall()
    con.commit()
    con.close()
    return len(violations)


def main():
    raw = extract()
    raw_rows = {k: len(v) for k, v in raw.items()}
    before = run_checks(raw)

    clean, log = transform(raw)
    after = run_checks(clean)
    fk_violations = load(clean)

    found = sum(r["failed_rows"] for r in before)
    left = sum(r["failed_rows"] for r in after)
    report = {
        "raw_rows": raw_rows,
        "clean_rows": {k: len(v) for k, v in clean.items()},
        "checks_run": len(before),
        "checks_failing_before": sum(r["failed_rows"] > 0 for r in before),
        "checks_failing_after": sum(r["failed_rows"] > 0 for r in after),
        "defective_rows_found": found,
        "defective_rows_remaining": left,
        "foreign_key_violations_in_db": fk_violations,
        "cleaning_actions": log,
        "before": before,
        "after": after,
    }
    with open(REPORT, "w") as f:
        json.dump(report, f, indent=2)

    print(f"Rows in : {sum(raw_rows.values())}   Rows out: {sum(report['clean_rows'].values())}")
    print(f"Checks run: {report['checks_run']}  failing before: {report['checks_failing_before']}  after: {report['checks_failing_after']}")
    print(f"Defects found: {found}  remaining after cleaning: {left}  FK violations in DB: {fk_violations}")
    for r in before:
        if r["failed_rows"]:
            print(f"  - {r['table']}: {r['check']}: {r['failed_rows']}")
    if left or fk_violations:
        raise SystemExit("Data-quality checks still failing after cleaning")


if __name__ == "__main__":
    main()
