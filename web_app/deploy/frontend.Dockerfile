FROM node:20-alpine AS build

WORKDIR /app/web_app/frontend

COPY web_app/frontend/package.json web_app/frontend/pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile

COPY web_app/frontend/index.html web_app/frontend/tsconfig.json web_app/frontend/vite.config.ts ./
COPY web_app/frontend/src ./src

# Required: the public URL of the API, e.g. https://aquant-studio-api.fly.dev/api/v1
ARG VITE_API_BASE_URL
RUN test -n "$VITE_API_BASE_URL" || (echo "VITE_API_BASE_URL build argument is required" >&2 && exit 1)
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN pnpm build

FROM nginx:1.27-alpine

# The official image renders /etc/nginx/templates/*.template with envsubst at start-up,
# so the server listens on $PORT (Railway/Render) or 8080 by default.
ENV PORT=8080
COPY web_app/deploy/nginx.frontend.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/web_app/frontend/dist /usr/share/nginx/html

EXPOSE 8080
