"""Generate a synthetic, deliberately messy e-commerce dataset (4 raw CSVs).

Real data is rarely clean, so defects are injected on purpose: duplicates, nulls,
invalid values, orphaned foreign keys, inconsistent casing and mixed date formats.
The seed is fixed so every run produces the same data.
"""
import os
import numpy as np
import pandas as pd

rng = np.random.default_rng(42)
OUT = os.path.join("data", "raw")
os.makedirs(OUT, exist_ok=True)

N_CUST, N_PROD, N_ORD = 2000, 300, 10000
CITIES = ["Kochi", "Thrissur", "Bengaluru", "Chennai", "Mumbai", "Delhi", "Pune", "Hyderabad"]
CATEGORIES = ["Electronics", "Home", "Books", "Fashion", "Sports", "Beauty", "Toys"]
STATUSES = ["delivered", "shipped", "cancelled", "processing"]


def pick(n, frac):
    """Random row positions to corrupt."""
    return rng.choice(n, size=int(n * frac), replace=False)


# ---------- customers ----------
cust = pd.DataFrame({
    "customer_id": np.arange(1, N_CUST + 1),
    "name": [f"Customer {i}" for i in range(1, N_CUST + 1)],
    "city": rng.choice(CITIES, N_CUST),
    "signup_date": pd.to_datetime("2023-01-01") + pd.to_timedelta(rng.integers(0, 700, N_CUST), unit="D"),
})
cust["signup_date"] = cust["signup_date"].dt.strftime("%Y-%m-%d")
idx = pick(N_CUST, 0.05)
cust.loc[idx, "city"] = [c.upper() + " " for c in cust.loc[idx, "city"]]          # casing / whitespace
cust.loc[pick(N_CUST, 0.03), "city"] = np.nan                                      # missing city
idx = pick(N_CUST, 0.04)
cust.loc[idx, "signup_date"] = pd.to_datetime(cust.loc[idx, "signup_date"]).dt.strftime("%d-%b-%Y")  # mixed format
cust = pd.concat([cust, cust.sample(int(N_CUST * 0.02), random_state=1)])           # duplicate rows

# ---------- products ----------
prod = pd.DataFrame({
    "product_id": np.arange(1, N_PROD + 1),
    "category": rng.choice(CATEGORIES, N_PROD),
    "price": np.round(rng.uniform(150, 5000, N_PROD), 2),
})
prod.loc[pick(N_PROD, 0.03), "category"] = np.nan
bad = pick(N_PROD, 0.04)
prod.loc[bad, "price"] = rng.choice([0, -50, -1], len(bad))                          # invalid prices
prod = pd.concat([prod, prod.sample(int(N_PROD * 0.02), random_state=2)])

# ---------- orders ----------
order_dates = pd.to_datetime("2024-01-01") + pd.to_timedelta(rng.integers(0, 600, N_ORD), unit="D")
orders = pd.DataFrame({
    "order_id": np.arange(1, N_ORD + 1),
    "customer_id": rng.integers(1, N_CUST + 1, N_ORD),
    "order_date": order_dates,
    "delivery_date": order_dates + pd.to_timedelta(rng.integers(2, 12, N_ORD), unit="D"),
    "status": rng.choice(STATUSES, N_ORD, p=[0.7, 0.1, 0.1, 0.1]),
})
orders["order_date"] = orders["order_date"].dt.strftime("%Y-%m-%d")
orders["delivery_date"] = orders["delivery_date"].dt.strftime("%Y-%m-%d")
orders.loc[orders["status"].isin(["cancelled", "processing"]), "delivery_date"] = np.nan
orders.loc[pick(N_ORD, 0.02), "customer_id"] = N_CUST + rng.integers(1, 500)         # orphan customers
swap = pick(N_ORD, 0.02)
orders.loc[swap, "delivery_date"] = (pd.to_datetime(orders.loc[swap, "order_date"]) - pd.Timedelta(days=3)).dt.strftime("%Y-%m-%d")
orders.loc[pick(N_ORD, 0.05), "status"] = "Delivered "                               # inconsistent casing
orders = pd.concat([orders, orders.sample(int(N_ORD * 0.02), random_state=3)])

# ---------- order_items ----------
rows = []
for oid in range(1, N_ORD + 1):
    for pid in rng.choice(np.arange(1, N_PROD + 1), size=rng.integers(1, 5), replace=False):
        rows.append((oid, int(pid), int(rng.integers(1, 5))))
items = pd.DataFrame(rows, columns=["order_id", "product_id", "quantity"])
price_lookup = prod.drop_duplicates("product_id").set_index("product_id")["price"]
items["unit_price"] = items["product_id"].map(price_lookup).abs().replace(0, 499.0)
n = len(items)
items.loc[pick(n, 0.02), "unit_price"] = np.nan
items.loc[pick(n, 0.01), "quantity"] = 0
items.loc[pick(n, 0.01), "product_id"] = N_PROD + rng.integers(1, 100)               # orphan products
items.loc[pick(n, 0.01), "order_id"] = N_ORD + rng.integers(1, 200)                  # orphan orders

for name, df in [("customers", cust), ("products", prod), ("orders", orders), ("order_items", items)]:
    df.to_csv(os.path.join(OUT, f"{name}.csv"), index=False)
    print(f"generated {name}.csv: {len(df)} rows")
