# Deployment Guide — Vercel & Cloud Hosting

This guide outlines how to deploy the **SIH26100 Platform** to production using **Vercel** for the Next.js frontend and a cloud provider (e.g., Render, Railway, or Fly.io) for the FastAPI backend and PostgreSQL database.

---

## Architecture Overview

```
Frontend (Vercel)  ──>  Backend API (Render/Railway/Fly.io)  ──>  PostgreSQL (Neon/Supabase/Render)
```

---

## 1. Deploying Frontend to Vercel

### Option A: Via Vercel Dashboard (Recommended)

1. Push your repository to **GitHub / GitLab / Bitbucket**.
2. Go to [vercel.com/new](https://vercel.com/new) and import your repository.
3. In the project settings, set:
   - **Framework Preset**: `Next.js`
   - **Root Directory**: `frontend`
4. Add **Environment Variables**:
   - `NEXT_PUBLIC_API_URL`: `https://<your-backend-domain>` (e.g. `https://sih26100-backend.onrender.com`)
5. Click **Deploy**.

### Option B: Via Vercel CLI

```bash
cd frontend
npm install -g vercel
vercel login
vercel
```

---

## 2. Deploying Backend & Database

The backend is a **FastAPI** application using **SQLAlchemy**, **Alembic**, and **PostgreSQL**.

### Step 1: Managed PostgreSQL Database
Create a free PostgreSQL instance on:
- [Neon.tech](https://neon.tech)
- [Supabase](https://supabase.com)
- [Render PostgreSQL](https://render.com)

Save your `DATABASE_URL` (format: `postgresql://user:password@host/dbname?sslmode=require`).

### Step 2: Deploy Backend to Render / Railway

#### Using Render (`render.yaml` or Web Service):
1. Create a new **Web Service** on [Render.com](https://render.com).
2. Connect your repository.
3. Configure settings:
   - **Root Directory**: `backend`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt && alembic upgrade head`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Set Environment Variables:
   - `DATABASE_URL`: `<your-postgres-connection-string>`
   - `JWT_SECRET`: `<your-production-jwt-secret>`
   - `LLM_BASE_URL`: (Optional) Ollama or OpenAI/Groq compatible URL
5. Deploy and copy your backend URL (e.g. `https://sih26100-api.onrender.com`).

---

## 3. Link Frontend to Backend

Update `NEXT_PUBLIC_API_URL` on your Vercel Project Settings to match your backend URL, then re-deploy the frontend.
