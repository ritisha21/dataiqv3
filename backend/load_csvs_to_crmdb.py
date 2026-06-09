"""
load_csvs_to_crmdb.py
---------------------
Loads all CRM CSV files into the crmdb PostgreSQL database.

USAGE (run from the folder where your CSVs are):
    pip install pandas psycopg2-binary sqlalchemy
    python load_csvs_to_crmdb.py

Edit the DB_URL below if your Postgres credentials differ.
"""

import pandas as pd 
from sqlalchemy import create_engine, text

# ── CONFIG ────────────────────────────────────────────────────────────────────
DB_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/crmdb"

import os 
os.chdir(r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\csvfiles")

# Map: table_name → csv filename (put all CSVs in the same folder as this script)
CSV_FILES = {
    "accounts":               "accounts.csv",
    "intl_accounts":          "intl_accounts.csv",
    "products":               "products.csv",
    "employees":              "employees.csv",
    "sales_teams":            "sales_teams.csv",
    "sales_pipeline":         "sales_pipeline.csv",
    "orders_mar_2017":        "mar_2017_orders.csv",
    "orders_apr_2017":        "apr_2017_orders.csv",
    "orders_may_2017":        "may_2017_orders.csv",
    "orders_jun_2017":        "jun_2017_orders.csv",
    "orders_jul_2017":        "jul_2017_orders.csv",
    "orders_aug_2017":        "aug_2017_orders.csv",
    "orders_sep_2017":        "sep_2017_orders.csv",
    "orders_oct_2017":        "oct_2017_orders.csv",
    "orders_nov_2017":        "nov_2017_orders.csv",
    "orders_dec_2017":        "dec_2017_orders.csv",
    "table_join_example":     "table_join_example.csv",
    "pivot_product_region":   "test_of_save_to_dataset_pivot.csv",
    "unpivot_dates":          "test_of_save_to_dataset_unpivot.csv",
}

# ── LOAD ──────────────────────────────────────────────────────────────────────
def main():
    engine = create_engine(DB_URL)

    # Verify connection
    with engine.connect() as conn:
        result = conn.execute(text("SELECT current_database()"))
        print(f"✓ Connected to database: {result.scalar()}\n")

    total_rows = 0
    for table_name, csv_file in CSV_FILES.items():
        try:
            df = pd.read_csv(csv_file)

            # Normalise column names: lowercase, spaces → underscores
            df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

            # Parse date columns
            for col in df.columns:
                if "date" in col:
                    df[col] = pd.to_datetime(df[col], errors="coerce")

            df.to_sql(
                name=table_name,
                con=engine,
                if_exists="replace",   # drop + recreate on re-run
                index=False,
            )
            print(f"  ✓ {table_name:30s}  {len(df):>6,} rows  ← {csv_file}")
            total_rows += len(df)

        except FileNotFoundError:
            print(f"  ✗ {csv_file} not found — skipping {table_name}")
        except Exception as e:
            print(f"  ✗ {table_name}: {e}")

    print(f"\n✓ Done — {total_rows:,} total rows loaded into crmdb")
    print("\nYou can now connect DataIQ to:")
    print("  Host:     localhost")
    print("  Port:     5432")
    print("  Database: crmdb")
    print("  Username: postgres")
    print("  Password: postgres")

if __name__ == "__main__":
    main()
