# OPTIONAL container build - NOT verified (Docker/WSL were not operational on the development machine).
# The supported, tested way to run SkillRadar is native Windows: setup.cmd + start.cmd.
# Private data is NOT baked into the image: mount ./data at runtime (see docker-compose.yml).

# --- stage 1: build the React frontend
FROM node:22-alpine AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- stage 2: Python runtime
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY skillradar/ ./skillradar/
COPY --from=web /app/frontend/dist ./frontend/dist
RUN useradd --create-home skillradar && mkdir -p /app/data && chown -R skillradar /app/data
USER skillradar
EXPOSE 8000
# 0.0.0.0 inside the container; docker-compose publishes it on 127.0.0.1 only.
CMD ["python", "-m", "skillradar", "web", "--host", "0.0.0.0", "--port", "8000"]
