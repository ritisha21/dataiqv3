# DataIQ Platform — Complete Setup & Deployment Guide

## WHY YOU SAW THOSE ERRORS

Every single "Cannot find module" error (both Python Pylance and TypeScript) is because
packages are not installed yet. The errors go away entirely once you run the install
commands below. They are NOT code bugs.

The "files placed in wrong folder" errors (layout.tsx at root, page.tsx at root, etc.)
mean you opened individual files in VS Code without the full folder context. Place every
file exactly as shown in the folder map at the top of this guide.

---

## STEP 0 — Prerequisites (install once on your machine)

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.11+ | python.org |
| Node.js | 20+ | nodejs.org |
| Docker Desktop | latest | docker.com |
| Git | any | git-scm.com |

---

## STEP 1 — Clone / create the project root

```
mkdir crm-ai-core
cd crm-ai-core
# Copy all backend/ and frontend/ folders into here
```

---

## STEP 2 — Backend: create virtualenv + install packages

```bash
cd backend

# Create and activate venv
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate

# Install ALL Python packages (this fixes every Pylance "reportMissingImports" error)
pip install -r requirements.txt
```

After this, open VS Code with the venv selected as the Python interpreter:
  Ctrl+Shift+P → "Python: Select Interpreter" → pick the venv one.
  All red Pylance underlines will disappear.

---

## STEP 3 — Create backend .env file

```bash
cd backend
cp .env.example .env
```

Edit .env and fill in:

```env
# Required — generate a real Fernet key:
# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FERNET_KEY=your-generated-key-here

# Required — your OpenAI key
OPENAI_API_KEY=sk-...

# Keep these as-is for Docker local dev
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/dataiq
SYNC_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/dataiq
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=change-this-to-a-random-32-char-string
```

---

## STEP 4 — Frontend: install packages

```bash
cd frontend

# Install ALL npm packages (fixes every TypeScript "Cannot find module" error)
npm install

# If you see peer dependency warnings, ignore them or run:
npm install --legacy-peer-deps
```

After this, all TypeScript red underlines in VS Code disappear automatically.

---

## STEP 5 — Start databases (Docker)

```bash
# From project root (crm-ai-core/)
docker compose up postgres redis -d

# Verify they started
docker compose ps
```

---

## STEP 6 — Run database migrations

```bash
cd backend

# With venv activated:
alembic upgrade head
```

If alembic complains about DATABASE_URL, make sure your .env is correct and run:
```bash
export SYNC_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/dataiq
alembic upgrade head
```

---

## STEP 7 — Start backend (development)

```bash
cd backend

# With venv activated:
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open: http://localhost:8000/docs  — you should see the Swagger UI

---

## STEP 8 — Start Celery workers (development, separate terminals)

Terminal 2 — ML worker:
```bash
cd backend
source venv/bin/activate   # or venv\Scripts\activate on Windows
celery -A app.infrastructure.cache.celery_app worker -Q ml -c 2 --loglevel=info
```

Terminal 3 — Schema worker:
```bash
cd backend
source venv/bin/activate
celery -A app.infrastructure.cache.celery_app worker -Q schema -c 4 --loglevel=info
```

---

## STEP 9 — Start frontend (development)

```bash
cd frontend
npm run dev
```

Open: http://localhost:3000

---

## STEP 10 — First-time usage flow

1. Open http://localhost:3000
2. Click "Create account"
3. Fill: company name, workspace slug (e.g. "acme"), email, password
4. You land on Dashboard
5. Go to Connections → Connect DB → enter your Postgres/MySQL credentials
6. Wait ~10 seconds for schema introspection (check backend logs)
7. Go to Chat → ask "show me all tables" or "show revenue by month"
8. Go to Models → Train Model → select table, target column, goal

---

## FULL DOCKER DEPLOY (production-like)

```bash
# From project root
docker compose up --build -d

# Check all services running
docker compose ps

# View logs
docker compose logs -f backend
docker compose logs -f celery_ml

# Run migrations inside the container
docker compose exec backend alembic upgrade head
```

Services will be available at:
- http://localhost       → Nginx (frontend + API)
- http://localhost:8000  → Backend API directly
- http://localhost:3000  → Frontend directly
- http://localhost:5555  → Flower (Celery monitoring)

---

## REMAINING CHANGES YOU NEED TO MAKE

### 1. Fix Tailwind CSS version conflict

Your error: '@tailwind base' is no longer available in v4

This means you accidentally installed Tailwind v4. Fix it:

```bash
cd frontend
npm uninstall tailwindcss
npm install tailwindcss@^3.4.3
```

Keep globals.css as-is (with @tailwind base/components/utilities — that's v3 syntax).

### 2. Fix the file location issue

You have files at C:\Users\KIIT\Desktop\crm-ai-core\ root level:
- layout.tsx     → move to frontend/src/app/dashboard/layout.tsx
- page.tsx       → move to frontend/src/app/dashboard/page.tsx (or appropriate subfolder)
- store.ts       → move to frontend/src/lib/store.ts
- globals.css    → move to frontend/src/app/globals.css
- Providers.tsx  → move to frontend/src/components/layout/Providers.tsx
- Sidebar.tsx    → move to frontend/src/components/layout/Sidebar.tsx
- api,.ts        → rename to api.ts, move to frontend/src/lib/api.ts
  (note: your file is named "api,.ts" with a comma — rename it!)
- chat.py        → move to backend/app/api/v1/endpoints/chat.py
- env.py         → move to backend/migrations/env.py
- 001_initial.py → move to backend/migrations/versions/001_initial.py

### 3. Rename api,.ts → api.ts

Your file is literally called "api,.ts" (with a comma). Rename it to api.ts.

### 4. Add missing next.config.js output mode for Docker

Add to frontend/next.config.js:
```js
const nextConfig = {
  output: 'standalone',   // ADD THIS LINE for Docker
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  },
}
```

### 5. Create frontend/.env.local

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 6. VS Code Python interpreter

After installing pip packages, press Ctrl+Shift+P in VS Code,
type "Python: Select Interpreter", and choose the one from your venv folder.
This makes ALL Pylance errors go away — they're purely because VS Code
doesn't know where your packages are installed.

---

## ENVIRONMENT VARIABLES REFERENCE

### Backend (.env)

| Variable | Description | Example |
|----------|-------------|---------|
| DATABASE_URL | Async postgres URL | postgresql+asyncpg://... |
| SYNC_DATABASE_URL | Sync postgres URL (Celery/Alembic) | postgresql+psycopg2://... |
| REDIS_URL | Redis connection | redis://localhost:6379/0 |
| SECRET_KEY | JWT signing key | random 32+ chars |
| FERNET_KEY | DB credential encryption | generate with cryptography |
| OPENAI_API_KEY | LLM API key | sk-... |
| LLM_MODEL | Model to use | gpt-4o-mini |
| ML_MODEL_DIR | Where to save model files | /tmp/dataiq/models |

### Frontend (.env.local)

| Variable | Description |
|----------|-------------|
| NEXT_PUBLIC_API_URL | Backend URL the browser calls |

---

## COMMON ERRORS AND FIXES

| Error | Fix |
|-------|-----|
| "Cannot find module 'axios'" | Run: cd frontend && npm install |
| "Cannot find module 'fastapi'" | Run: cd backend && pip install -r requirements.txt with venv active |
| "reportMissingImports structlog" | Same as above — venv not active or wrong interpreter |
| "@tailwind base not available in v4" | Run: npm install tailwindcss@^3.4.3 |
| "Cannot find react/jsx-runtime" | npm install + check tsconfig.json has "jsx":"preserve" |
| alembic "table already exists" | Run: alembic stamp head (if you created tables manually) |
| Celery "No module named app" | Run celery from inside backend/ folder with venv active |
| CORS error in browser | Make sure backend CORS allows http://localhost:3000 (already set) |
| "Connection refused" on DB | Make sure docker compose up postgres redis -d is running |

---

## QUICK REFERENCE: ALL COMMANDS

```bash
# Terminal 1 — databases
docker compose up postgres redis -d

# Terminal 2 — backend API
cd backend && source venv/bin/activate
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# Terminal 3 — ML Celery worker
cd backend && source venv/bin/activate
celery -A app.infrastructure.cache.celery_app worker -Q ml -c 2 --loglevel=info

# Terminal 4 — Schema Celery worker  
cd backend && source venv/bin/activate
celery -A app.infrastructure.cache.celery_app worker -Q schema -c 4 --loglevel=info

# Terminal 5 — frontend
cd frontend && npm run dev
```
