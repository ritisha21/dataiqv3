import pandas as pd
from sqlalchemy import create_engine, text
from app.infrastructure.feature_store.feature_store import feature_store

engine = create_engine("postgresql+psycopg2://postgres:postgres@localhost:5432/crmdb")
with engine.connect() as conn:
    df = pd.read_sql(text('SELECT * FROM "sales_pipeline" LIMIT 50000'), conn)

# Convert datetimes like the pipeline does
for col in df.select_dtypes(include=["datetime64[ns]", "datetimetz"]).columns:
    df[col] = df[col].astype("int64") // 10**9

feature_df, definitions = feature_store.build_features(
    df, {}, "sales_pipeline", target_col="deal_stage"
)

print("Feature columns after build_features:")
print(feature_df.dtypes)
print("\nShape:", feature_df.shape)