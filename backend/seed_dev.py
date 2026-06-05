"""
Run this once to create the dev tenant + user that the bypass auth uses.
  python seed_dev.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import create_engine, text
from app.core.config import settings
from app.core.security import hash_password

DEV_TENANT_ID = "00000000-0000-0000-0000-000000000001"
DEV_USER_ID   = "00000000-0000-0000-0000-000000000002"

engine = create_engine(settings.SYNC_DATABASE_URL)

with engine.begin() as conn:
    # tenant
    conn.execute(text("""
        INSERT INTO tenants (id, name, slug, plan, is_active)
        VALUES (:id, 'Dev Tenant', 'dev', 'free', true)
        ON CONFLICT (id) DO NOTHING
    """), {"id": DEV_TENANT_ID})

    # user
    conn.execute(text("""
        INSERT INTO users (id, tenant_id, email, hashed_password, full_name, role, is_active)
        VALUES (:id, :tid, 'dev@dataiq.local', :pw, 'Dev User', 'admin', true)
        ON CONFLICT (id) DO NOTHING
    """), {
        "id":  DEV_USER_ID,
        "tid": DEV_TENANT_ID,
        "pw":  hash_password("devpass123"),
    })

engine.dispose()
print("✅ Dev tenant and user seeded.")
print("   Email:    dev@dataiq.local")
print("   Password: devpass123")
print("   Slug:     dev")
