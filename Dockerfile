# ---- web app (React + Vite) -------------------------------------------------------------------
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- API (FastAPI) serving the built app at /app -------------------------------------------------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 tesseract-ocr poppler-utils && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=web /web/dist ./frontend/dist
# Build data + models at image build time if they are not shipped (deterministic, seed 42)
RUN test -f data/generated/homes.parquet || python scripts/generate_data.py --n 50000 --seed 42
RUN test -f models/energy_hybrid.txt || python -m greenghar.ml.train
EXPOSE 8000
HEALTHCHECK CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"
CMD ["uvicorn", "greenghar.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
