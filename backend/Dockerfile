FROM node:24-alpine AS web
WORKDIR /web
COPY --from=frontend package*.json ./
RUN npm ci --no-audit --no-fund
COPY --from=frontend . .
RUN npm run build

FROM python:3.12-slim
WORKDIR /srv/assistant
COPY pyproject.toml .
COPY app ./app
RUN --mount=type=cache,target=/root/.cache/pip pip install --timeout 90 .
COPY alembic.ini .
COPY migrations ./migrations
COPY tests ./tests
COPY --from=web /web/dist ./static
