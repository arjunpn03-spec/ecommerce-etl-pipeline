"""Run every query in queries.sql against the warehouse and print the results."""
import re
import sqlite3
import pandas as pd

con = sqlite3.connect("data/warehouse.db")
sql = open("queries.sql").read()
for block in re.split(r"-- name: ", sql)[1:]:
    title, query = block.split("\n", 1)
    print(f"\n=== {title} ===")
    print(pd.read_sql_query(query, con).to_string(index=False))
con.close()
