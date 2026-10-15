# --- Frontend image: build with Node, serve static files with nginx ---

# Stage 1: build the Vite bundle.
FROM node:20-alpine AS build
WORKDIR /app

# VITE_API_BASE_URL is baked into the bundle at BUILD time (import.meta.env).
# The browser (not a container) calls this URL, so it must be host-reachable
# (e.g. http://localhost:8000) — never the in-network service name "backend".
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

# Install deps from the lockfile for reproducible builds (runs lifecycle scripts,
# so esbuild's postinstall binary is set up correctly).
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# Stage 2: serve the static files with nginx (not `vite preview`).
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
