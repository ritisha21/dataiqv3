"""Initial schema

Revision ID: 001_initial
Revises: 
Create Date: 2024-01-01 00:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'tenants',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False, unique=True),
        sa.Column('slug', sa.String(100), nullable=False, unique=True),
        sa.Column('plan', sa.String(50), default='free'),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('full_name', sa.String(255)),
        sa.Column('role', sa.String(50), default='analyst'),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('last_login', sa.DateTime(timezone=True)),
    )
    op.create_index('uq_user_email_tenant', 'users', ['email', 'tenant_id'], unique=True)
    op.create_index('ix_users_tenant_id', 'users', ['tenant_id'])

    op.create_table(
        'refresh_tokens',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('token_hash', sa.String(255), nullable=False, unique=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'db_connections',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('db_type', sa.String(50), nullable=False),
        sa.Column('host', sa.String(255), nullable=False),
        sa.Column('port', sa.Integer(), nullable=False),
        sa.Column('database', sa.String(255), nullable=False),
        sa.Column('username', sa.String(255), nullable=False),
        sa.Column('encrypted_password', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('last_tested_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_db_connections_tenant_id', 'db_connections', ['tenant_id'])

    op.create_table(
        'schema_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('connection_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('db_connections.id'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, default=1),
        sa.Column('schema_graph', postgresql.JSON(), nullable=False),
        sa.Column('table_count', sa.Integer(), default=0),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_schema_tenant_conn', 'schema_snapshots', ['tenant_id', 'connection_id'])

    op.create_table(
        'semantic_mappings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('connection_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('db_connections.id'), nullable=False),
        sa.Column('version', sa.Integer(), default=1),
        sa.Column('mappings', postgresql.JSON(), nullable=False),
        sa.Column('is_manual_override', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'feature_definitions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('connection_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('db_connections.id'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('feature_type', sa.String(50)),
        sa.Column('sql_expression', sa.Text()),
        sa.Column('source_table', sa.String(255)),
        sa.Column('source_columns', postgresql.JSON()),
        sa.Column('lineage', postgresql.JSON()),
        sa.Column('version', sa.Integer(), default=1),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'ml_models',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('connection_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('db_connections.id'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('goal', sa.String(50), nullable=False),
        sa.Column('status', sa.String(50), default='pending'),
        sa.Column('target_column', sa.String(255), nullable=False),
        sa.Column('feature_columns', postgresql.JSON()),
        sa.Column('source_table', sa.String(255), nullable=False),
        sa.Column('dataset_hash', sa.String(64)),
        sa.Column('hyperparameters', postgresql.JSON(), default={}),
        sa.Column('metrics', postgresql.JSON(), default={}),
        sa.Column('artifact_path', sa.String(500)),
        sa.Column('version', sa.Integer(), default=1),
        sa.Column('random_seed', sa.Integer(), default=42),
        sa.Column('error_message', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('trained_at', sa.DateTime(timezone=True)),
    )
    op.create_index('ix_ml_models_tenant_id', 'ml_models', ['tenant_id'])

    op.create_table(
        'ml_experiments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('model_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('ml_models.id'), nullable=False),
        sa.Column('run_number', sa.Integer(), default=1),
        sa.Column('params', postgresql.JSON(), default={}),
        sa.Column('metrics', postgresql.JSON(), default={}),
        sa.Column('dataset_hash', sa.String(64)),
        sa.Column('artifact_path', sa.String(500)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'query_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('connection_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('db_connections.id'), nullable=False),
        sa.Column('natural_language', sa.Text(), nullable=False),
        sa.Column('generated_sql', sa.Text()),
        sa.Column('row_count', sa.Integer()),
        sa.Column('execution_time_ms', sa.Float()),
        sa.Column('success', sa.Boolean(), default=True),
        sa.Column('error_message', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_query_history_tenant_user', 'query_history', ['tenant_id', 'user_id'])


def downgrade() -> None:
    op.drop_table('query_history')
    op.drop_table('ml_experiments')
    op.drop_table('ml_models')
    op.drop_table('feature_definitions')
    op.drop_table('semantic_mappings')
    op.drop_table('schema_snapshots')
    op.drop_table('db_connections')
    op.drop_table('refresh_tokens')
    op.drop_table('users')
    op.drop_table('tenants')
