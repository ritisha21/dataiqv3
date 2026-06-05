from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import List, Optional
import uuid

from app.db.database import get_db
from app.domain.models.models import DBConnection, DBType, SchemaSnapshot, SemanticMapping
from app.core.dependencies import get_tenant_context, TenantContext, require_analyst_or_admin
from app.core.security import encrypt_credential
from app.infrastructure.connectors.db_connector import connector_service
from app.infrastructure.tasks.schema_tasks import introspect_schema_task

router = APIRouter(prefix="/connections", tags=["connections"])


class ConnectDBRequest(BaseModel):
    name: str
    db_type: DBType
    host: str
    port: int
    database: str
    username: str
    password: str


class DBConnectionResponse(BaseModel):
    id: str
    name: str
    db_type: str
    host: str
    port: int
    database: str
    username: str
    is_active: bool
    last_tested_at: Optional[str]

    class Config:
        from_attributes = True


@router.post("/connect-db", status_code=201)
async def connect_db(
    req: ConnectDBRequest,
    ctx: TenantContext = Depends(require_analyst_or_admin),
    db: AsyncSession = Depends(get_db),
):
    # Build temp conn object to test
    class TempConn:
        pass
    tmp = TempConn()
    tmp.db_type = req.db_type
    tmp.host = req.host
    tmp.port = req.port
    tmp.database = req.database
    tmp.username = req.username
    tmp.encrypted_password = encrypt_credential(req.password)

    ok = connector_service.test_connection(tmp)
    if not ok:
        raise HTTPException(400, "Could not connect to database. Check credentials and network.")

    encrypted_pw = encrypt_credential(req.password)
    conn = DBConnection(
        tenant_id=ctx.tenant_id,
        name=req.name,
        db_type=req.db_type,
        host=req.host,
        port=req.port,
        database=req.database,
        username=req.username,
        encrypted_password=encrypted_pw,
    )
    db.add(conn)
    await db.flush()
    conn_id = str(conn.id)
    await db.commit()

    # Kick off async schema introspection
    introspect_schema_task.delay(conn_id, ctx.tenant_id)

    return {"id": conn_id, "status": "connected", "message": "Schema introspection started"}


@router.get("/", response_model=List[DBConnectionResponse])
async def list_connections(
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DBConnection).where(
            DBConnection.tenant_id == ctx.tenant_id,
            DBConnection.is_active == True,
        )
    )
    connections = result.scalars().all()
    return [
        DBConnectionResponse(
            id=str(c.id),
            name=c.name,
            db_type=c.db_type.value,
            host=c.host,
            port=c.port,
            database=c.database,
            username=c.username,
            is_active=c.is_active,
            last_tested_at=c.last_tested_at.isoformat() if c.last_tested_at else None,
        )
        for c in connections
    ]


@router.get("/{connection_id}/schema")
async def get_schema(
    connection_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SchemaSnapshot).where(
            SchemaSnapshot.connection_id == connection_id,
            SchemaSnapshot.tenant_id == ctx.tenant_id,
        ).order_by(SchemaSnapshot.version.desc()).limit(1)
    )
    snapshot = result.scalar_one_or_none()
    if not snapshot:
        raise HTTPException(404, "Schema not yet available. Introspection may still be running.")

    return {
        "connection_id": connection_id,
        "version": snapshot.version,
        "schema": snapshot.schema_graph,
        "table_count": snapshot.table_count,
        "created_at": snapshot.created_at.isoformat(),
    }


@router.get("/{connection_id}/semantic")
async def get_semantic_mapping(
    connection_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SemanticMapping).where(
            SemanticMapping.connection_id == connection_id,
            SemanticMapping.tenant_id == ctx.tenant_id,
        ).order_by(SemanticMapping.version.desc()).limit(1)
    )
    mapping = result.scalar_one_or_none()
    if not mapping:
        raise HTTPException(404, "Semantic mappings not available yet.")

    return {
        "connection_id": connection_id,
        "version": mapping.version,
        "mappings": mapping.mappings,
        "is_manual_override": mapping.is_manual_override,
    }


@router.post("/{connection_id}/re-introspect")
async def re_introspect(
    connection_id: str,
    ctx: TenantContext = Depends(require_analyst_or_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DBConnection).where(
            DBConnection.id == connection_id,
            DBConnection.tenant_id == ctx.tenant_id,
        )
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(404, "Connection not found")

    task = introspect_schema_task.delay(connection_id, ctx.tenant_id)
    return {"task_id": task.id, "status": "queued"}
