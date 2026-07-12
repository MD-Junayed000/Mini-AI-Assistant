# Dockerfile for the React UI.
# Single `dev` target — installs deps, runs the Vite dev server with HMR.
# Production serves `npm run build`'s `dist/` via the host's static-site
# platform (Nginx, S3+CloudFront, Render static site, etc.) — no
# containerised prod target here, since the artefact is a static bundle.
# =============================================================================

FROM node:20-alpine AS dev

WORKDIR /app

# Copy manifests first so `npm install` is cached until they change.
COPY package.json package-lock.json* ./

# `npm ci` is reproducible but requires a committed lockfile; fall back to
# `npm install` so first-time clones without package-lock.json still work.
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# Anonymous volume mounted by docker-compose keeps node_modules out of the
# bind-mounted source tree — the bind-mount is slow on Windows/macOS and
# the kernel-resident copy inside the container is orders of magnitude faster.

COPY . .

EXPOSE 5173

# Bind to 0.0.0.0 so the host browser can reach the dev server, and run
# Vite with polling enabled for file-watcher reliability on bind mounts.
ENV HOST=0.0.0.0
ENV WATCHPACK_POLLING=true
ENV CHOKIDAR_USEPOLLING=true

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]