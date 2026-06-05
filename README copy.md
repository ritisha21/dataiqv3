# DataIQ — Autonomous Business Intelligence Platform

## What this actually is

You connect your company's Postgres or MySQL database.
The system reads your schema, understands what your tables mean,
and lets you ask questions in plain English — "why did revenue drop last month?"
It generates SQL, runs it, draws charts, trains ML models, and explains everything back to you.

No data science degree needed. No SQL knowledge needed.

---

## The full technology stack and why each piece exists

### Backend — FastAPI (Python)
The API server. Every button click in the UI hits a FastAPI endpoint.
FastAPI is async so it can handle many users simultaneously without blocking.
Lives at: backend/app/main.py

### Database — PostgreSQL (Docker)
Two separate uses:
1. Stores DataIQ's own data — your account, connections, model metadata, query history
2. Your connected CRM/ERP database — the one you're analysing (read-only access)
Never mixed. Completely separate engines.

### Redis (Docker)
Two separate uses:
1. Celery broker — queues background jobs (ML training, schema scanning)
2. Chat memory — stores your last 20 conversation turns so you can ask follow-up questions

### Celery (Python)
Background task runner. When you click "Train model", the API doesn't wait 5 minutes
blocking your browser. It puts the job on a Redis queue. A Celery worker picks it up
and trains in the background. You poll for status.
Two workers: one for ML tasks, one for schema scanning.

### LangGraph (Python)
Orchestration framework for the AI agent. Think of it as a flowchart engine.
When you type a message, LangGraph runs it through a pipeline of nodes:
  intent classifier → schema retriever → SQL generator → executor → insight generator → chart generator
Each node is a pure function. State flows between them. If SQL fails it retries automatically.

### LLM — OpenAI GPT-4o-mini
Used in exactly 3 places and nowhere else:
1. Intent classification — "is this person asking for SQL, an insight, or a model?"
2. SQL generation — "turn this English question into a SELECT query"
3. Insight narration — "explain these query results in business language"
Everything else (ML training, feature engineering, chart building) is deterministic code.

### XGBoost (Python)
The actual machine learning model used for training.
Given a table and a target column (e.g. "churned"), it:
1. Takes all other columns as features
2. Splits 80% train / 20% test
3. Trains a gradient boosting model
4. Returns AUC, F1, accuracy (classification) or RMSE, MAE, R2 (regression)

### Dask (Python)
Pandas handles DataFrames in memory. For a 10 million row table that might be 4GB of RAM.
Dask splits that table into partitions and processes them one at a time.
Used in: feature store, ETL scanner, ETL trainer.
Rule: under 100k rows → pandas. Over 100k rows → Dask.

### Alembic (Python)
Database migration tool. Creates all the tables in Postgres automatically.
"alembic upgrade head" reads migrations/versions/001_initial.py and creates every table.

### SQLAlchemy (Python)
Python's way of talking to databases without writing raw SQL everywhere.
Two modes: async (for FastAPI endpoints) and sync (for Celery workers).

### Next.js 14 (TypeScript/React)
The frontend. Server-side rendered React app.
Four main pages: Dashboard, Connections, Chat, Models.
Two new pages: ETL (scan → suggest → train), Export (query → CSV download).

### Recharts
React charting library. Renders bar charts, line charts, pie charts, scatter plots
from the JSON data the API returns.

### Zustand
Frontend state management. Stores: are you logged in, which connection is selected.
Simpler than Redux.

### TanStack Query
Handles all API calls from the frontend — caching, loading states, refetching.

---

## Complete system architecture — how data flows

```
Browser (Next.js)
      │
      │  HTTP / SSE
      ▼
FastAPI (port 8000)
      │
      ├─── Auth middleware (JWT validation, tenant isolation)
      │
      ├─── Rate limiter (per-tenant, Redis-backed)
      │
      ├─── /chat ──────────────────────────────────────────┐
      │                                                     │
      │         LangGraph Pipeline                          │
      │         ┌─────────────────────────────────────┐    │
      │         │ 1. intent_classifier  (LLM)         │    │
      │         │ 2. schema_retriever   (Redis cache)  │    │
      │         │ 3. context_builder    (Redis memory) │    │
      │         │ 4. sql_generator      (LLM)         │    │
      │         │ 5. sql_validator      (AST check)   │    │
      │         │ 6. sql_executor       (user's DB)   │    │
      │         │ 7. insight_generator  (LLM)         │    │
      │         │ 8. chart_generator    (heuristics)  │    │
      │         │ 9. response_formatter               │    │
      │         └─────────────────────────────────────┘    │
      │                                                     │
      ├─── /etl/scan ──────────────────────────────────────┤
      │         Dask scans every table                      │
      │         Returns suggestions like:                   │
      │         "Predict churn on customers table"          │
      │                                                     │
      ├─── /etl/train ─────────────────────────────────────┤
      │         Celery task queued                          │
      │         Dask: Extract → Transform → Load            │
      │         XGBoost trains, model saved to disk         │
      │                                                     │
      ├─── /export/csv ─────────────────────────────────────┤
      │         NL → SQL → execute → stream CSV file        │
      │                                                     │
      ├─── /connections ───────────────────────────────────┤
      │         Saves encrypted DB credentials              │
      │         Triggers async schema introspection         │
      │                                                     │
      └─── /models/predict ────────────────────────────────┘
                Loads saved XGBoost artifact
                Runs inference on input JSON


User's DB (Postgres/MySQL) ─────── read-only connection ──── sql_executor
System DB (Postgres)       ─────── read/write ────────────── SQLAlchemy ORM
Redis                      ─────── broker + memory ─────────  Celery + Chat
Dask                       ─────── partition processing ───── ETL + Feature store
```

---

## Multi-tenancy — how isolation works

Every single database row has a tenant_id column.
Every API endpoint extracts tenant_id from your JWT token.
Every database query adds WHERE tenant_id = YOUR_ID.

This means:
- Company A can never see Company B's data
- Company A's models are invisible to Company B
- Company A's connections, queries, chat history — all isolated

The JWT token is issued on login and contains:
  { "sub": user_id, "tenant_id": "your-company-uuid", "role": "admin" }

---

## The ETL pipeline in detail

ETL stands for Extract, Transform, Load. Here it means:

EXTRACT: Dask reads your database table in chunks
  → For 500k rows: splits into 5 partitions of 100k each
  → Reads partition by partition, never loads all 500k at once

TRANSFORM: Feature engineering runs on each partition lazily
  → Datetime columns: extracts year, month, day_of_week, hour
  → Categorical text columns: frequency encoding (replace category with its % frequency)
  → High-null columns (>70% missing): dropped
  → Numeric nulls: filled with column median

LOAD: One .compute() call materialises everything to pandas
  → XGBoost trains on the result
  → Model artifact saved to disk as .joblib file
  → Metrics stored in ml_models table

The "scan → suggest → train" flow:
  1. User clicks "Scan Database"
  2. Backend profiles every table (row counts, column types, null rates)
  3. Heuristics detect columns like "churned" (boolean → churn prediction)
     or "revenue" / "amount" (numeric → regression target)
  4. Returns suggestion cards: "Predict churn on customers, 47k rows, 95% confidence"
  5. User selects one or many suggestions (checkboxes)
  6. Clicks Train → Celery background job → Dask ETL → XGBoost → done

---

## Security model

1. Passwords hashed with bcrypt (passlib)
2. DB credentials encrypted with Fernet (symmetric AES-128) before storage
3. JWT access tokens expire in 30 minutes
4. Refresh tokens expire in 7 days, stored as SHA-256 hashes
5. User DB connections use read-only SQL enforcement:
   - AST-level SQL validation (sqlglot parses the query, rejects anything that isn't SELECT)
   - Statement timeout injected (SET LOCAL statement_timeout)
   - Row cap enforced (MAX 10,000 rows per query)
6. Rate limiting per tenant via Redis sliding window
7. Every ORM query scoped to tenant_id

---

## Directory map — every file explained

```
dataiq/
│
├── docker-compose.yml          Start postgres + redis + all services
├── SETUP.md                    This file
│
├── backend/
│   ├── requirements.txt        All Python packages
│   ├── alembic.ini             Alembic config (points to migrations/)
│   ├── .env.example            Copy this to .env and fill in values
│   │
│   ├── migrations/
│   │   ├── env.py              Alembic runtime config
│   │   └── versions/
│   │       └── 001_initial.py  Creates all database tables
│   │
│   └── app/
│       ├── main.py             FastAPI app factory, registers all routers
│       │
│       ├── core/
│       │   ├── config.py       All env vars (DATABASE_URL, OPENAI_API_KEY etc.)
│       │   ├── security.py     JWT, password hashing, Fernet encryption
│       │   ├── logging.py      Structured logging setup (structlog)
│       │   ├── dependencies.py FastAPI auth middleware, tenant resolution
│       │   └── rate_limit.py   Per-tenant rate limiting middleware
│       │
│       ├── db/
│       │   └── database.py     Async SQLAlchemy engine + session factory
│       │
│       ├── domain/
│       │   └── models/
│       │       └── models.py   All ORM models (Tenant, User, DBConnection,
│       │                       MLModel, SchemaSnapshot, QueryHistory etc.)
│       │
│       ├── api/v1/endpoints/
│       │   ├── auth.py         POST /auth/register, /auth/login, /auth/refresh
│       │   ├── connections.py  POST /connections/connect-db, GET /connections/
│       │   ├── query.py        POST /query, POST /chat
│       │   ├── models.py       POST /models/train-model, GET /models/, POST /models/predict
│       │   ├── dashboard.py    GET /dashboard/widgets
│       │   ├── chat.py         POST /chat/, POST /chat/stream (SSE)
│       │   ├── etl.py          POST /etl/scan, POST /etl/train, GET /etl/results
│       │   └── export.py       POST /export/csv, POST /export/query-csv
│       │
│       └── infrastructure/
│           ├── connectors/
│           │   ├── db_connector.py     Connects to user's Postgres/MySQL,
│           │   │                       introspects schema, samples data
│           │   └── semantic_layer.py   Classifies tables (crm/finance/ops)
│           │                           and columns (id/target/datetime/numeric)
│           │
│           ├── feature_store/
│           │   └── feature_store.py    Pandas/Dask feature engineering.
│           │                           Auto-selects engine based on row count.
│           │
│           ├── ml_pipeline/
│           │   └── pipeline.py         XGBoost training + inference.
│           │                           No LLM anywhere in this file.
│           │
│           ├── llm/
│           │   ├── llm_service.py      3 LLM calls: classify_intent,
│           │   │                       generate_sql, generate_insight
│           │   └── query_engine.py     SQL safety layer (AST validation,
│           │                           row limits, timeout injection)
│           │
│           ├── chat/
│           │   ├── state.py            ChatState TypedDict — single source
│           │   │                       of truth flowing through all nodes
│           │   ├── orchestrator.py     LangGraph graph definition + runner
│           │   ├── nodes/
│           │   │   ├── intent_classifier.py   LLM: what does user want?
│           │   │   ├── schema_retriever.py    Fetch schema from DB/cache
│           │   │   ├── context_builder.py     Merge schema + memory + rewrite followups
│           │   │   ├── sql_generator.py       LLM: generate SELECT query
│           │   │   ├── sql_validator.py       AST check: SELECT only
│           │   │   ├── sql_executor.py        Run query, compute column stats
│           │   │   ├── ml_trigger.py          Dispatch Celery training task
│           │   │   ├── insight_generator.py   LLM: explain results in English
│           │   │   ├── chart_generator.py     Heuristic chart type selection
│           │   │   └── response_formatter.py  Assemble final JSON + save to memory
│           │   ├── tools/
│           │   │   ├── sql_tools.py     run_sql(), validate_sql(), compute_column_stats()
│           │   │   ├── schema_tools.py  get_schema() with Redis cache
│           │   │   └── memory_tools.py  fetch/store Redis chat history
│           │   └── memory/
│           │       └── redis_memory.py  Redis List per tenant, capped at 20 turns
│           │
│           ├── etl/
│           │   ├── scanner.py   Dask-powered DB profiler + suggestion generator
│           │   └── trainer.py   Dask ETL pipeline: Extract→Transform→Load→Train
│           │
│           ├── cache/
│           │   └── celery_app.py   Celery app config, queue routing
│           │
│           └── tasks/
│               ├── ml_tasks.py     Celery task: train_model_task
│               ├── schema_tasks.py Celery task: introspect_schema_task
│               └── etl_tasks.py    Celery task: run_etl_task
│
└── frontend/
    ├── package.json            npm dependencies
    ├── next.config.js          Next.js config
    ├── tailwind.config.js      Tailwind CSS config + custom colors
    ├── tsconfig.json           TypeScript config
    ├── .env.local              NEXT_PUBLIC_API_URL=http://localhost:8000
    │
    └── src/
        ├── app/
        │   ├── layout.tsx          Root layout (fonts, providers)
        │   ├── globals.css         Global CSS, Tailwind directives, custom vars
        │   ├── page.tsx            Root redirect (/ → /dashboard or /auth)
        │   ├── auth/page.tsx       Login + Register form
        │   ├── dashboard/
        │   │   ├── layout.tsx      Sidebar wrapper
        │   │   └── page.tsx        KPI cards, charts, model status, query history
        │   ├── connections/
        │   │   ├── layout.tsx
        │   │   └── page.tsx        Connect DB form, schema explorer
        │   ├── chat/
        │   │   ├── layout.tsx
        │   │   └── page.tsx        SSE streaming chat, chart rendering, SQL viewer
        │   ├── models/
        │   │   ├── layout.tsx
        │   │   └── page.tsx        Train model form, metrics, prediction UI
        │   ├── etl/
        │   │   ├── layout.tsx
        │   │   └── page.tsx        Scan → suggestions → multi-select → train
        │   └── export/
        │       ├── layout.tsx
        │       └── page.tsx        NL/SQL query → preview → CSV download
        │
        ├── components/
        │   └── layout/
        │       ├── Sidebar.tsx     Navigation sidebar with all 6 pages
        │       └── Providers.tsx   QueryClient + Toast provider wrapper
        │
        └── lib/
            ├── api.ts              Axios client, auto token refresh, all API calls
            └── store.ts            Zustand: auth state + selected connection
```

---

## Prerequisites — install these before anything else

1. Docker Desktop — https://docker.com/products/docker-desktop
   Open it and wait for "Engine running" in the bottom left

2. Python 3.11 — https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
   During install: CHECK "Add Python 3.11 to PATH"

3. Node.js 20 — https://nodejs.org (LTS version)

4. An OpenAI API key — https://platform.openai.com/api-keys

---

## Setup — run these commands exactly once

### Step 1: Start databases
```
docker compose up postgres redis -d
```
Wait 20 seconds. Both should show "healthy":
```
docker compose ps
```

### Step 2: Backend setup
```
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```
Takes 3-5 minutes. You will see packages downloading one by one.

### Step 3: Generate encryption key
```
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Copy the output. You need it in the next step.

### Step 4: Create .env file
```
copy .env.example .env
```
Open backend\.env and set:
```
FERNET_KEY=paste-your-generated-key-here
OPENAI_API_KEY=sk-your-openai-key-here
```
Everything else stays as-is.

### Step 5: Create database tables
```
alembic upgrade head
```
You should see: Running upgrade -> 001_initial

### Step 6: Frontend setup
```
cd ..\frontend
npm install
```
If Tailwind errors appear:
```
npm uninstall tailwindcss
npm install tailwindcss@3.4.3
```

---

## Running the app — every time

You need 4 terminals. Open them with the + button in VS Code's terminal panel.

TERMINAL 1 — API server:
```
cd backend
venv\Scripts\activate
uvicorn app.main:app --reload --port 8000
```
✓ Working when you see: Uvicorn running on http://127.0.0.1:8000

TERMINAL 2 — ML worker:
```
cd backend
venv\Scripts\activate
celery -A app.infrastructure.cache.celery_app worker -Q ml --pool=solo --loglevel=info
```

TERMINAL 3 — Schema worker:
```
cd backend
venv\Scripts\activate
celery -A app.infrastructure.cache.celery_app worker -Q schema --pool=solo --loglevel=info
```

TERMINAL 4 — Frontend:
```
cd frontend
npm run dev
```
✓ Working when you see: ready - started server on http://localhost:3000

Open http://localhost:3000 in your browser.

---

## First time using the app

1. Go to http://localhost:3000
2. Click "Create account"
3. Fill in:
   - Full name: your name
   - Company name: anything
   - Workspace slug: "mycompany" (lowercase, no spaces)
   - Email: your email
   - Password: anything you want
4. You land on the Dashboard
5. Go to Connections → Connect DB
   Enter the host/port/database/username/password of any Postgres or MySQL database you have
   (Can be a local one, a cloud one, anything)
6. Wait 15-30 seconds — the Schema worker (Terminal 3) introspects your database
7. Go to Chat and type: "show me all tables"
8. Go to ETL → Scan Database → select suggestions → Train
9. Go to Export → ask a question → Download CSV

---

## API reference — all endpoints

POST /api/v1/auth/register       Create account + tenant
POST /api/v1/auth/login          Get access + refresh tokens
POST /api/v1/auth/refresh        Refresh expired access token

POST /api/v1/connections/connect-db    Save DB credentials, start scan
GET  /api/v1/connections/              List your connections
GET  /api/v1/connections/{id}/schema   Get introspected schema
GET  /api/v1/connections/{id}/semantic Get semantic column tags

POST /api/v1/query               NL question → SQL → results + insight + chart
POST /api/v1/chat/               Same as /query, structured response
POST /api/v1/chat/stream         SSE streaming version (for real-time UI)
GET  /api/v1/chat/history        Last N conversation turns
DELETE /api/v1/chat/history      Clear conversation memory

POST /api/v1/etl/scan            Scan DB, return feature suggestions
POST /api/v1/etl/train           Train models for selected suggestions
GET  /api/v1/etl/status/{id}     Poll Celery task status
GET  /api/v1/etl/results         All ETL-trained models

POST /api/v1/models/train-model  Manually trigger training
GET  /api/v1/models/             List all models
GET  /api/v1/models/{id}         Model details + experiment history
POST /api/v1/models/predict      Run inference on a trained model

GET  /api/v1/dashboard/widgets   Auto-generated KPIs + charts for dashboard

POST /api/v1/export/csv          NL question → CSV file download
POST /api/v1/export/query-csv    Raw SQL → CSV file download

Interactive docs: http://localhost:8000/docs (only in development mode)

---

## Common errors and fixes

Password authentication failed for postgres:
  docker compose down -v
  docker compose up postgres redis -d
  (wait 20 seconds)
  alembic upgrade head

Cannot connect to redis:
  Make sure Docker Desktop is running
  docker compose ps (should show healthy)
  docker compose up redis -d

Celery PermissionError WinError 5:
  Use --pool=solo flag (already in the commands above)
  This is a Windows-only issue with multiprocessing

Frontend ERR_MEMORY_ALLOCATION_FAILED:
  Close other applications to free RAM
  Or add to package.json dev script:
  "dev": "node --max-old-space-size=512 node_modules/.bin/next dev"

Cannot find module 'axios' / any npm package:
  cd frontend && npm install

reportMissingImports in VS Code:
  Ctrl+Shift+P → Python: Select Interpreter → pick venv\Scripts\python.exe

@tailwind base not available in v4:
  npm uninstall tailwindcss && npm install tailwindcss@3.4.3

Alembic table already exists:
  alembic stamp head

---

## Environment variables reference

Required in backend/.env:

DATABASE_URL          = postgresql+asyncpg://postgres:postgres@localhost:5432/dataiq
SYNC_DATABASE_URL     = postgresql+psycopg2://postgres:postgres@localhost:5432/dataiq
REDIS_URL             = redis://localhost:6379/0
CELERY_BROKER_URL     = redis://localhost:6379/1
CELERY_RESULT_BACKEND = redis://localhost:6379/2
SECRET_KEY            = any-random-string-32-chars-minimum
ALGORITHM             = HS256
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS   = 7
FERNET_KEY            = (generate with cryptography.fernet.Fernet.generate_key())
OPENAI_API_KEY        = sk-your-key
LLM_MODEL             = gpt-4o-mini
ML_MODEL_DIR          = /tmp/dataiq/models
MAX_QUERY_ROWS        = 10000
QUERY_TIMEOUT_SECONDS = 30
ENVIRONMENT           = development

Required in frontend/.env.local:

NEXT_PUBLIC_API_URL   = http://localhost:8000
