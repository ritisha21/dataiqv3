import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, String, Boolean, DateTime, Text, JSON,
    ForeignKey, Integer, Float, Enum as SAEnum, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base
import enum


class UserRole(str, enum.Enum):
    admin = "admin"
    analyst = "analyst"
    viewer = "viewer"


class DBType(str, enum.Enum):
    postgres = "postgres"
    mysql = "mysql"


class ModelStatus(str, enum.Enum):
    pending = "pending"
    training = "training"
    ready = "ready"
    failed = "failed"


class ModelGoal(str, enum.Enum):
    classification = "classification"
    regression = "regression"
    churn = "churn"
    revenue_forecast = "revenue_forecast"
    anomaly_detection = "anomaly_detection"


# ─── Tenant ──────────────────────────────────────────────────────────────────

class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True)
    slug = Column(String(100), nullable=False, unique=True)
    plan = Column(String(50), default="free")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    users = relationship("User", back_populates="tenant")
    db_connections = relationship("DBConnection", back_populates="tenant")
    ml_models = relationship("MLModel", back_populates="tenant")


# ─── User ─────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    email = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255))
    role = Column(SAEnum(UserRole), default=UserRole.analyst)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True))

    tenant = relationship("Tenant", back_populates="users")
    refresh_tokens = relationship("RefreshToken", back_populates="user")

    __table_args__ = (
        Index("uq_user_email_tenant", "email", "tenant_id", unique=True),
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    token_hash = Column(String(255), nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="refresh_tokens")


# ─── DB Connection ────────────────────────────────────────────────────────────

class DBConnection(Base):
    __tablename__ = "db_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    db_type = Column(SAEnum(DBType), nullable=False)
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False)
    database = Column(String(255), nullable=False)
    username = Column(String(255), nullable=False)
    encrypted_password = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    last_tested_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tenant = relationship("Tenant", back_populates="db_connections")
    schema_snapshots = relationship("SchemaSnapshot", back_populates="connection")
    semantic_mappings = relationship("SemanticMapping", back_populates="connection")


# ─── Schema ───────────────────────────────────────────────────────────────────

class SchemaSnapshot(Base):
    __tablename__ = "schema_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    connection_id = Column(UUID(as_uuid=True), ForeignKey("db_connections.id"), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    schema_graph = Column(JSON, nullable=False)  # nodes + edges
    table_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    connection = relationship("DBConnection", back_populates="schema_snapshots")

    __table_args__ = (
        Index("ix_schema_tenant_conn", "tenant_id", "connection_id"),
    )


class SemanticMapping(Base):
    __tablename__ = "semantic_mappings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    connection_id = Column(UUID(as_uuid=True), ForeignKey("db_connections.id"), nullable=False)
    version = Column(Integer, default=1)
    mappings = Column(JSON, nullable=False)  # table -> {purpose, columns: {name -> tag}}
    is_manual_override = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    connection = relationship("DBConnection", back_populates="semantic_mappings")


# ─── Feature Store ────────────────────────────────────────────────────────────

class FeatureDefinition(Base):
    __tablename__ = "feature_definitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    connection_id = Column(UUID(as_uuid=True), ForeignKey("db_connections.id"), nullable=False)
    name = Column(String(255), nullable=False)
    feature_type = Column(String(50))  # numeric, categorical, temporal, window
    sql_expression = Column(Text)
    source_table = Column(String(255))
    source_columns = Column(JSON)
    lineage = Column(JSON)  # {source_table, transformation, version}
    version = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_feature_tenant_conn", "tenant_id", "connection_id"),
    )


# ─── ML Models ────────────────────────────────────────────────────────────────

class MLModel(Base):
    __tablename__ = "ml_models"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    connection_id = Column(UUID(as_uuid=True), ForeignKey("db_connections.id"), nullable=False)
    name = Column(String(255), nullable=False)
    goal = Column(SAEnum(ModelGoal), nullable=False)
    status = Column(SAEnum(ModelStatus), default=ModelStatus.pending)
    target_column = Column(String(255), nullable=False)
    feature_columns = Column(JSON)
    source_table = Column(String(255), nullable=False)
    dataset_hash = Column(String(64))
    hyperparameters = Column(JSON, default={})
    metrics = Column(JSON, default={})
    artifact_path = Column(String(500))
    version = Column(Integer, default=1)
    random_seed = Column(Integer, default=42)
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    trained_at = Column(DateTime(timezone=True))

    tenant = relationship("Tenant", back_populates="ml_models")
    experiments = relationship("MLExperiment", back_populates="model")


class MLExperiment(Base):
    __tablename__ = "ml_experiments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    model_id = Column(UUID(as_uuid=True), ForeignKey("ml_models.id"), nullable=False)
    run_number = Column(Integer, default=1)
    params = Column(JSON, default={})
    metrics = Column(JSON, default={})
    dataset_hash = Column(String(64))
    artifact_path = Column(String(500))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    model = relationship("MLModel", back_populates="experiments")


# ─── Query History ────────────────────────────────────────────────────────────

class QueryHistory(Base):
    __tablename__ = "query_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    connection_id = Column(UUID(as_uuid=True), ForeignKey("db_connections.id"), nullable=False)
    natural_language = Column(Text, nullable=False)
    generated_sql = Column(Text)
    row_count = Column(Integer)
    execution_time_ms = Column(Float)
    success = Column(Boolean, default=True)
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_query_tenant_user", "tenant_id", "user_id"),
    )
