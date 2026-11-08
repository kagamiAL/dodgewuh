# Production frontend: Vite build served by Caddy (deploy/Caddyfile is mounted at runtime).
FROM node:22-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM caddy:2.10.2
COPY --from=build /app/dist /srv
