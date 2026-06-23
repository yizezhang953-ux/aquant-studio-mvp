FROM node:20-alpine AS build

WORKDIR /app/web_app/frontend

COPY web_app/frontend/package.json web_app/frontend/pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile

COPY web_app/frontend/index.html ./index.html
COPY web_app/frontend/tsconfig.json ./tsconfig.json
COPY web_app/frontend/src ./src

ARG VITE_API_BASE_URL=http://localhost:8000/api/v1
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN pnpm build

FROM nginx:1.27-alpine

COPY web_app/deploy/nginx.frontend.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/web_app/frontend/dist /usr/share/nginx/html

EXPOSE 80
