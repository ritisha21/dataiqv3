import pandas as pd
from sqlalchemy import create_engine, text

engine = create_engine("postgresql+psycopg2://postgres:postgres@localhost:5432/crmdb")
with engine.connect() as conn:
    df = pd.read_sql(text('SELECT * FROM "sales_pipeline" LIMIT 10'), conn)

print("Before anything:")
print(df.dtypes)
print()

# Simulate what ml_tasks does
freq_maps = {}
for col in df.select_dtypes(include=["object"]).columns:
    if col != "deal_stage":
        freq_maps[col] = df[col].value_counts(normalize=True).to_dict()
        print(f"Built freq_map for {col}: {len(freq_maps[col])} values")

print("\nfreq_maps keys:", list(freq_maps.keys()))