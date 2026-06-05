from typing import Dict, List, Any, Optional
import re
import structlog

logger = structlog.get_logger()

# Heuristic classification patterns
TABLE_PURPOSE_PATTERNS = {
    "crm": r"(customer|client|contact|account|lead|opportunity|deal|prospect)",
    "finance": r"(invoice|payment|revenue|expense|transaction|order|billing|account)",
    "ops": r"(product|inventory|warehouse|shipment|delivery|ticket|support|issue)",
    "hr": r"(employee|staff|department|salary|payroll|leave|attendance)",
    "analytics": r"(event|log|metric|stat|report|summary|aggregate)",
}

COLUMN_TAG_PATTERNS = {
    "id": r"^(id|uuid|guid|pk|_id)$|_id$|_uuid$",
    "target_churn": r"(churn|churned|cancelled|canceled|inactive|lost)",
    "target_revenue": r"(revenue|amount|value|sales|price|total|sum)",
    "datetime": r"(created_at|updated_at|date|time|timestamp|at$|_date$|_time$)",
    "categorical": r"(status|type|category|label|class|tier|segment|group|gender|country|region)",
    "numeric": r"(count|quantity|qty|score|rate|ratio|percent|age|weight|height|amount)",
    "email": r"(email|mail)",
    "name": r"(name|title|first_name|last_name|full_name)",
    "foreign_key": r"_id$|_uuid$|_fk$",
}


class SemanticLayerEngine:
    """
    Classifies tables and columns using heuristics + optional embeddings.
    Deterministic layer - no LLM calls here.
    """

    def classify_schema(
        self, schema_graph: Dict, connection_id: str
    ) -> Dict[str, Any]:
        """
        Returns versioned semantic mappings:
        {
            "tables": {
                "customers": {
                    "purpose": "crm",
                    "confidence": 0.9,
                    "columns": {
                        "id": {"tag": "id", "confidence": 1.0},
                        "email": {"tag": "email", "confidence": 0.95},
                        ...
                    }
                }
            },
            "graph": {nodes, edges},
            "connection_id": ...,
        }
        """
        mappings = {"tables": {}, "connection_id": connection_id}

        for node in schema_graph.get("nodes", []):
            table_name = node["id"]
            table_purpose, table_conf = self._classify_table_purpose(table_name, node.get("columns", []))

            col_mappings = {}
            for col in node.get("columns", []):
                tag, conf = self._classify_column(col["name"], col.get("type", ""))
                col_mappings[col["name"]] = {
                    "tag": tag,
                    "confidence": conf,
                    "dtype": col.get("type", "unknown"),
                    "nullable": col.get("nullable", True),
                    "primary_key": col.get("primary_key", False),
                }

            mappings["tables"][table_name] = {
                "purpose": table_purpose,
                "confidence": table_conf,
                "columns": col_mappings,
                "sample_rows": node.get("sample_rows", []),
            }

        return mappings

    def _classify_table_purpose(self, table_name: str, columns: List[Dict]) -> tuple:
        name_lower = table_name.lower()
        for purpose, pattern in TABLE_PURPOSE_PATTERNS.items():
            if re.search(pattern, name_lower):
                return purpose, 0.9

        # Check column names for clues
        col_names = " ".join([c["name"].lower() for c in columns])
        for purpose, pattern in TABLE_PURPOSE_PATTERNS.items():
            if re.search(pattern, col_names):
                return purpose, 0.7

        return "general", 0.5

    def _classify_column(self, col_name: str, col_type: str) -> tuple:
        name_lower = col_name.lower()
        type_lower = col_type.lower()

        for tag, pattern in COLUMN_TAG_PATTERNS.items():
            if re.search(pattern, name_lower, re.IGNORECASE):
                return tag, 0.9

        # Type-based fallback
        if any(t in type_lower for t in ["int", "float", "numeric", "decimal", "double"]):
            return "numeric", 0.7
        if any(t in type_lower for t in ["char", "text", "varchar", "string"]):
            return "categorical", 0.6
        if any(t in type_lower for t in ["date", "time", "timestamp"]):
            return "datetime", 0.9
        if "bool" in type_lower:
            return "boolean", 0.9

        return "feature", 0.5

    def get_feature_candidates(
        self, mappings: Dict, target_tag: str = "target_churn"
    ) -> Dict[str, List[str]]:
        """Return tables and columns most suitable as features for a given target."""
        result = {}
        for table_name, table_info in mappings.get("tables", {}).items():
            feature_cols = []
            has_target = False
            for col_name, col_info in table_info.get("columns", {}).items():
                if col_info["tag"] == target_tag:
                    has_target = True
                elif col_info["tag"] not in ("id", "foreign_key"):
                    feature_cols.append(col_name)
            if has_target or feature_cols:
                result[table_name] = feature_cols
        return result

    def build_prompt_context(
        self, mappings: Dict, max_tables: int = 10
    ) -> str:
        """Build schema context for LLM SQL generation - no full dump."""
        lines = []
        tables = list(mappings.get("tables", {}).items())[:max_tables]
        for table_name, table_info in tables:
            purpose = table_info.get("purpose", "general")
            lines.append(f"Table: {table_name} (purpose: {purpose})")
            for col_name, col_info in list(table_info.get("columns", {}).items())[:20]:
                lines.append(f"  - {col_name}: {col_info['dtype']} [{col_info['tag']}]")
        return "\n".join(lines)


semantic_engine = SemanticLayerEngine()
