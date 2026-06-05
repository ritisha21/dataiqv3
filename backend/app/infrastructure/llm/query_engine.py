from typing import Dict, Any, List, Optional, Tuple
import sqlglot
import sqlglot.expressions as exp
from sqlalchemy import text, create_engine
from app.core.config import settings
import structlog
import time

logger = structlog.get_logger()

# Banned SQL keywords that indicate mutation
BANNED_STATEMENTS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER",
    "TRUNCATE", "REPLACE", "MERGE", "GRANT", "REVOKE", "EXEC",
    "EXECUTE", "CALL", "COPY", "LOAD",
}


class QuerySafetyError(Exception):
    pass


class QueryEngine:
    """
    Executes validated SQL on read-only connections.
    Enforces row limits, timeouts, and injection prevention.
    """

    def validate_sql(self, sql: str) -> str:
        """
        AST-level validation via sqlglot.
        Returns cleaned SQL or raises QuerySafetyError.
        """
        sql = sql.strip().rstrip(";")

        try:
            statements = sqlglot.parse(sql)
        except Exception as e:
            raise QuerySafetyError(f"SQL parse error: {e}")

        if not statements:
            raise QuerySafetyError("Empty SQL statement")

        if len(statements) > 1:
            raise QuerySafetyError("Multiple statements not allowed")

        stmt = statements[0]

        # Must be a SELECT
        if not isinstance(stmt, exp.Select):
            raise QuerySafetyError("Only SELECT statements are allowed")

        # Check for any mutation expressions in the AST
        for node in stmt.walk():
            node_type = type(node).__name__.upper()
            if node_type in BANNED_STATEMENTS:
                raise QuerySafetyError(f"Forbidden operation detected: {node_type}")

        # Add LIMIT if not present
        if stmt.args.get("limit") is None:
            sql = f"{sql} LIMIT {settings.MAX_QUERY_ROWS}"
        else:
            # Enforce max limit
            limit_val = stmt.args["limit"]
            try:
                limit_num = int(str(limit_val.this))
                if limit_num > settings.MAX_QUERY_ROWS:
                    sql = sql  # Will be handled by row enforcement
            except Exception:
                pass

        return sql

    def execute(
        self,
        engine,
        sql: str,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Execute validated SQL and return structured results."""
        safe_sql = self.validate_sql(sql)
        start = time.time()

        try:
            with engine.connect() as conn:
                # Set statement timeout (Postgres)
                try:
                    timeout_ms = settings.QUERY_TIMEOUT_SECONDS * 1000
                    conn.execute(text(f"SET LOCAL statement_timeout = {timeout_ms}"))
                except Exception:
                    pass  # MySQL doesn't support this the same way

                result = conn.execute(text(safe_sql), params or {})
                columns = list(result.keys())
                rows = result.fetchmany(settings.MAX_QUERY_ROWS)

            elapsed = round((time.time() - start) * 1000, 2)

            # Serialize rows
            serialized = []
            for row in rows:
                safe_row = {}
                for k, v in zip(columns, row):
                    if hasattr(v, "isoformat"):
                        safe_row[k] = v.isoformat()
                    elif v is None:
                        safe_row[k] = None
                    else:
                        try:
                            import json; json.dumps(v)
                            safe_row[k] = v
                        except (TypeError, ValueError):
                            safe_row[k] = str(v)
                serialized.append(safe_row)

            return {
                "columns": columns,
                "rows": serialized,
                "row_count": len(serialized),
                "execution_time_ms": elapsed,
                "sql": safe_sql,
            }

        except QuerySafetyError:
            raise
        except Exception as e:
            elapsed = round((time.time() - start) * 1000, 2)
            logger.error("query_execution_failed", sql=safe_sql[:200], error=str(e))
            raise RuntimeError(f"Query execution failed: {e}")


query_engine = QueryEngine()
