# ---------- Frontend build (Next.js static export) ----------
FROM node:22-bookworm-slim AS frontend_builder
WORKDIR /app/frontend

COPY frontend/package.json ./
RUN npm install

COPY frontend ./
# With output:'export', `next build` produces the `out/` folder.
RUN npm run build


# ---------- Backend runtime (FastAPI + serve static files) ----------
FROM python:3.12-slim AS runtime
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps (kept minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# Python deps
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# App code
COPY backend /app/backend

# Copy the built static site
COPY --from=frontend_builder /app/frontend/out /app/static

# App Runner will route to whatever port you configure.
# We'll default to 8000, but respect $PORT if App Runner sets it.
ENV PORT=8000

EXPOSE 8000

CMD ["sh", "-c", "uvicorn backend.server:app --host 0.0.0.0 --port ${PORT}"]
