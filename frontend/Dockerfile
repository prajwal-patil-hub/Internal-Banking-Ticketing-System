# --- Dev: vite dev server with hot reload ---------------------------------
FROM node:20-alpine AS dev
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]


# --- Build ----------------------------------------------------------------
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .

# Baked into the bundle at build time, so it is a build argument rather than a
# runtime variable. Left empty on purpose: the client then falls back to a
# same-origin `/api/v1`, which nginx proxies to the backend. Set it only when
# the API lives on a different origin, and expect to configure CORS if you do.
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build


# --- Prod: static files behind nginx --------------------------------------
FROM nginx:1.27-alpine AS prod
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

# Hits the nginx-only endpoint, so this reports on the web tier alone. A check
# that proxied to the backend would mark the frontend unhealthy during a
# backend restart and take the static site down with it.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- http://localhost/healthz >/dev/null 2>&1 || exit 1
