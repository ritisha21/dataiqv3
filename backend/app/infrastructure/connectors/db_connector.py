from typing import Optional, Dict, Any, List
from sqlalchemy import create_engine, inspect, text
from app.core.security import decrypt_credential
from app.domain.models.models import DBConnection, DBType
import structlog

logger = structlog.get_logger()


class SchemaGraph:
    def __init__(self):
        self.nodes: List[Dict] = []  # tables
        self.edges: List[Dict] = []  # FK relationships

    def to_dict(self) -> Dict:
        return {"nodes": self.nodes, "edges": self.edges}


class DBConnectorService:
    """Infrastructure service: connects to user DBs, introspects schema."""

    def build_connection_url(self, conn: DBConnection) -> str:
        password = decrypt_credential(conn.encrypted_password)
        if conn.db_type == DBType.postgres:
            return f"postgresql+psycopg2://{conn.username}:{password}@{conn.host}:{conn.port}/{conn.database}"
        elif conn.db_type == DBType.mysql:
            return f"mysql+pymysql://{conn.username}:{password}@{conn.host}:{conn.port}/{conn.database}"
        raise ValueError(f"Unsupported DB type: {conn.db_type}")

    def test_connection(self, conn: DBConnection) -> bool:
        try:
            url = self.build_connection_url(conn)
            engine = create_engine(url, connect_args={"connect_timeout": 5}, pool_pre_ping=True)
            with engine.connect() as c:
                c.execute(text("SELECT 1"))
            engine.dispose()
            return True
        except Exception as e:
            logger.error("connection_test_failed", error=str(e))
            return False

    def introspect_schema(self, conn: DBConnection) -> SchemaGraph:
        url = self.build_connection_url(conn)
        engine = create_engine(
            url,
            connect_args={"connect_timeout": 10},
            pool_size=1,
            max_overflow=0,
        )
        graph = SchemaGraph()

        try:
            inspector = inspect(engine)
            table_names = inspector.get_table_names()

            fk_map: Dict[str, List] = {}

            for table_name in table_names:
                columns = []
                for col in inspector.get_columns(table_name):
                    columns.append({
                        "name": col["name"],
                        "type": str(col["type"]),
                        "nullable": col.get("nullable", True),
                        "primary_key": False,
                    })

                pk_constraint = inspector.get_pk_constraint(table_name)
                pk_cols = set(pk_constraint.get("constrained_columns", []))
                for col in columns:
                    if col["name"] in pk_cols:
                        col["primary_key"] = True

                # Sample data (safe - read only, limited)
                sample_data = self._sample_table(engine, table_name)

                graph.nodes.append({
                    "id": table_name,
                    "label": table_name,
                    "columns": columns,
                    "row_count_estimate": sample_data.get("row_count", 0),
                    "sample_rows": sample_data.get("rows", []),
                })

                # Foreign keys
                fks = inspector.get_foreign_keys(table_name)
                fk_map[table_name] = fks
                for fk in fks:
                    graph.edges.append({
                        "source": table_name,
                        "target": fk["referred_table"],
                        "source_columns": fk["constrained_columns"],
                        "target_columns": fk["referred_columns"],
                        "constraint_name": fk.get("name"),
                    })

        finally:
            engine.dispose()

        return graph

    def _sample_table(self, engine, table_name: str, limit: int = 5) -> Dict:
        try:
            with engine.connect() as conn:
                # Use parameterized-safe quoting approach
                result = conn.execute(text(f'SELECT * FROM "{table_name}" LIMIT :limit'), {"limit": limit})
                rows = [dict(zip(result.keys(), row)) for row in result]

                # Row count estimate
                count_result = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))
                row_count = count_result.scalar()

            # Serialize - convert non-JSON-safe types
            safe_rows = []
            for row in rows:
                safe_row = {}
                for k, v in row.items():
                    try:
                        import json
                        json.dumps(v)
                        safe_row[k] = v
                    except (TypeError, ValueError):
                        safe_row[k] = str(v)
                safe_rows.append(safe_row)

            return {"rows": safe_rows, "row_count": row_count}
        except Exception as e:
            logger.warning("sample_table_failed", table=table_name, error=str(e))
            return {"rows": [], "row_count": 0}

    def get_engine_for_query(self, conn: DBConnection):
        """Returns a read-only capable engine. User must ensure DB user is read-only."""
        url = self.build_connection_url(conn)
        return create_engine(
            url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )


connector_service = DBConnectorService()
