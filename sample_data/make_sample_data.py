"""Create a realistic fake sales dataset so the app has something to demo."""

import random
from datetime import date, timedelta
from pathlib import Path

import polars as pl

random.seed(42)

PRODUCTS = {
    "Electronics": [("Headphones", 89.0), ("Keyboard", 59.0), ("Monitor", 229.0)],
    "Home": [("Desk Lamp", 35.0), ("Coffee Maker", 79.0), ("Blender", 65.0)],
    "Office": [("Notebook Pack", 12.0), ("Desk Chair", 189.0), ("Pen Set", 9.0)],
}
REGIONS = ["Northeast", "Southeast", "Midwest", "West"]
SEGMENTS = ["Consumer", "Small Business", "Enterprise"]

rows = []
start = date(2024, 1, 1)
for order_id in range(1, 3001):
    order_date = start + timedelta(days=random.randint(0, 729))
    category = random.choice(list(PRODUCTS))
    product, base_price = random.choice(PRODUCTS[category])
    # Seasonality: more units sold in November and December.
    holiday_boost = 2 if order_date.month in (11, 12) else 0
    units = random.randint(1, 5) + holiday_boost
    discount = random.choice([0, 0, 0, 0.1, 0.2])
    unit_price = round(base_price * (1 - discount), 2)
    rows.append(
        {
            "Order ID": order_id,
            "Order Date": order_date,
            "Region": random.choice(REGIONS),
            "Customer Segment": random.choice(SEGMENTS),
            "Product Category": category,
            "Product": product,
            "Units": units,
            "Unit Price ($)": unit_price,
            "Discount": discount,
            "Revenue ($)": round(units * unit_price, 2),
        }
    )

Path("sample_data").mkdir(exist_ok=True)
pl.DataFrame(rows).write_csv("sample_data/sales.csv")
print("Wrote sample_data/sales.csv with", len(rows), "rows")