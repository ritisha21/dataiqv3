from typing import Dict, Any, Optional, List
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage
from app.core.config import settings
import json
import re
import structlog

logger = structlog.get_logger()


def _get_llm(temperature: float = 0.0) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.LLM_MODEL,
        temperature=temperature,
        openai_api_key=settings.OPENAI_API_KEY,
        max_tokens=1000,
    )


SQL_SYSTEM_PROMPT = """You are a SQL expert. Generate a single SELECT SQL query based on the schema and user question.

Rules:
- Only SELECT statements
- Use proper JOIN syntax if needed
- No subqueries more than 2 levels deep
- Always alias ambiguous columns
- Respond ONLY with the SQL query, no explanation, no markdown fences
- Never include DROP, DELETE, INSERT, UPDATE, ALTER or any mutation
"""

INTENT_SYSTEM_PROMPT = """You are a data analytics intent classifier.
Classify the user's message into exactly one of these intents:
- sql_query: user wants to query/filter/aggregate data
- train_model: user wants to build/train a ML model or make predictions
- get_insight: user wants explanations, trends, or business insights
- chart_request: user wants a visualization or chart
- schema_explore: user wants to understand the data structure

Respond ONLY with JSON: {"intent": "<intent>", "confidence": 0.9, "goal": "<if train_model: churn|revenue_forecast|classification|regression>"}
"""

INSIGHT_SYSTEM_PROMPT = """You are a senior business analyst. 
Given query results and statistics, write a concise 2-3 paragraph business insight.
Focus on: key patterns, anomalies, actionable recommendations.
Be direct and specific. Do not use generic phrases.
"""


class LLMService:
    def classify_intent(self, user_message: str, schema_context: str = "") -> Dict[str, Any]:
        llm = _get_llm(temperature=0.0)
        context = f"\nSchema context:\n{schema_context[:500]}" if schema_context else ""
        messages = [
            SystemMessage(content=INTENT_SYSTEM_PROMPT),
            HumanMessage(content=f"User message: {user_message}{context}"),
        ]
        response = llm.invoke(messages)
        try:
            return json.loads(response.content)
        except Exception:
            return {"intent": "sql_query", "confidence": 0.5, "goal": None}

    def generate_sql(self, user_question: str, schema_context: str) -> str:
        llm = _get_llm(temperature=0.0)
        messages = [
            SystemMessage(content=SQL_SYSTEM_PROMPT),
            HumanMessage(content=f"""Schema:
{schema_context}

Question: {user_question}

SQL:"""),
        ]
        response = llm.invoke(messages)
        sql = response.content.strip()
        # Strip markdown if any
        sql = re.sub(r"```sql\s*", "", sql)
        sql = re.sub(r"```\s*", "", sql)
        return sql.strip()

    def generate_insight(
        self,
        query_results: Dict[str, Any],
        statistics: Dict[str, Any],
        user_question: str,
    ) -> str:
        llm = _get_llm(temperature=0.3)
        summary = {
            "question": user_question,
            "row_count": query_results.get("row_count"),
            "columns": query_results.get("columns"),
            "sample_rows": query_results.get("rows", [])[:5],
            "statistics": statistics,
        }
        messages = [
            SystemMessage(content=INSIGHT_SYSTEM_PROMPT),
            HumanMessage(content=f"Data summary:\n{json.dumps(summary, indent=2, default=str)[:3000]}"),
        ]
        response = llm.invoke(messages)
        return response.content

    def generate_chart_spec(
        self,
        columns: List[str],
        rows: List[Dict],
        user_request: str,
    ) -> Dict[str, Any]:
        """Returns a chart spec: {type, x_col, y_col, title}"""
        llm = _get_llm(temperature=0.0)
        messages = [
            SystemMessage(content="""Generate a chart spec from data columns and user request.
Respond ONLY with JSON: {"chart_type": "bar|line|pie|scatter|area", "x_col": "column_name", "y_col": "column_name", "title": "Chart Title"}
Choose the most appropriate chart type for the data."""),
            HumanMessage(content=f"Columns: {columns}\nUser request: {user_request}\nSample: {rows[:3]}"),
        ]
        response = llm.invoke(messages)
        try:
            return json.loads(response.content)
        except Exception:
            return {"chart_type": "bar", "x_col": columns[0] if columns else "x", "y_col": columns[1] if len(columns) > 1 else "y", "title": "Chart"}


llm_service = LLMService()
