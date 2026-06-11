import sys
sys.path.insert(0, r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend")

from sqlalchemy import create_engine, text
import pandas as pd

engine = create_engine("postgresql+psycopg2://postgres:postgres@localhost:5432/crmdb")
with engine.connect() as conn:
    df = pd.read_sql(text('SELECT * FROM "sales_pipeline" LIMIT 50000'), conn)

print("df dtypes BEFORE copy:")
print(df.dtypes)

raw_df = df.copy()
freq_maps = {}
for col in raw_df.select_dtypes(include=["object"]).columns:
    if col != "deal_stage":
        freq_maps[col] = raw_df[col].value_counts(normalize=True).to_dict()
        print(f"Built {col}: {len(freq_maps[col])} values")

print("\nfinal freq_maps keys:", list(freq_maps.keys()))