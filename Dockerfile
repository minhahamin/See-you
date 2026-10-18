# 서비스 1개로 배포한다: FastAPI가 API와 빌드된 프론트(React)를 함께 서빙한다.

# --- 1) 프론트 빌드 ---
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# 카카오맵 JavaScript 키는 빌드 때 번들에 들어간다 (브라우저에 노출되는 키이므로 카카오 콘솔에서 도메인을 제한한다).
ARG VITE_KAKAO_MAP_KEY=""
ENV VITE_KAKAO_MAP_KEY=${VITE_KAKAO_MAP_KEY}
RUN npm run build

# --- 2) 백엔드 ---
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt
COPY backend/ backend/
COPY --from=web /web/dist frontend/dist
WORKDIR /app/backend

# 시작할 때 저장된 임베딩 캐시(data/embeddings.npz)로 검색 인덱스를 만든다 (캐시가 맞으면 API 호출이 없다).
CMD ["sh", "-c", "python -m ingest.build_index && uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
