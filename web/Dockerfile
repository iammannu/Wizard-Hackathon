# ---- Build stage: compile the SPA to static assets ----
FROM node:22-alpine AS build
WORKDIR /app

# Copy lockfiles first so `pnpm install` is cached independently of source changes.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN corepack enable && corepack prepare pnpm@9.15.4 --activate \
    && pnpm install --frozen-lockfile

COPY . .

# Baked in at build time — Vite only reads VITE_-prefixed vars present during
# `vite build` (see src/lib/api.js). Leave unset when the frontend is served
# same-origin behind the nginx reverse proxy below (the default for this
# compose stack); set it only if the API is deployed on a separate origin.
ARG VITE_API_URL=
ENV VITE_API_URL=$VITE_API_URL
RUN pnpm build

# ---- Runtime stage: serve the static build with nginx ----
FROM nginx:1.27-alpine AS production
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
