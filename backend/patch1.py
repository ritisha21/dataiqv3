path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\feature_store\feature_store.py"

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add leakage_cols param to build_features signature
old_sig = '''    def build_features(
        self,
        df:               pd.DataFrame,
        semantic_mapping: Dict[str, Any],
        target_col:       Optional[str] = None,
        window_cols:      Optional[List[str]] = None,
    ) -> Tuple[pd.DataFrame, List[Dict]]:'''

new_sig = '''    def build_features(
        self,
        df:               pd.DataFrame,
        semantic_mapping: Dict[str, Any],
        target_col:       Optional[str] = None,
        window_cols:      Optional[List[str]] = None,
        leakage_cols:     Optional[List[str]] = None,
    ) -> Tuple[pd.DataFrame, List[Dict]]:'''

if old_sig in content:
    content = content.replace(old_sig, new_sig)
    print("Patched build_features signature")
else:
    print("WARNING: build_features signature not found exactly - manual check needed")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)