path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\tasks\ml_tasks.py"

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Drop leakage columns right after raw_df copy, before build_features
old = "raw_df = df.copy()"
new = '''raw_df = df.copy()

        # Drop leakage columns - fields only known AFTER the outcome occurs
        LEAKAGE_COLS = {"close_date"}
        leakage_present = [c for c in LEAKAGE_COLS if c in df.columns and c != training_config["target_col"]]
        if leakage_present:
            df = df.drop(columns=leakage_present)
            logger.info("dropped_leakage_columns", columns=leakage_present)'''

if old in content:
    content = content.replace(old, new, 1)
    print("Patched ml_tasks.py to drop leakage columns")
else:
    print("ERROR: marker not found")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

# Verify
with open(path, "r", encoding="utf-8") as f:
    for i, line in enumerate(f):
        if "leakage" in line.lower() or "raw_df = df.copy" in line:
            print(f"Line {i}: {line.rstrip()}") 