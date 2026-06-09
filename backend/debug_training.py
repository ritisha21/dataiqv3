import pandas as pd
from sqlalchemy import create_engine, text

engine = create_engine("postgresql+psycopg2://postgres:postgres@localhost:5432/crmdb")
with engine.connect() as conn:
    df = pd.read_sql(text('SELECT * FROM "sales_pipeline" LIMIT 50000'), conn)

print("Columns and dtypes:")
print(df.dtypes)
print("\nSample:")
print(df.head(2))