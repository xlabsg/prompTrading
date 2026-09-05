# ============== Stage 1: Dependencies ==============
FROM public.ecr.aws/docker/library/node:22-alpine AS deps

WORKDIR /app

# Copy only package files for better caching
COPY apps/web/package.json apps/web/package-lock.json* ./

# Install dependencies with cache mount for faster rebuilds
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund --prefer-offline

# ============== Stage 2: Builder ==============
FROM public.ecr.aws/docker/library/node:22-alpine AS builder

WORKDIR /app

# Build argument for API URL
# - Local development: defaults to http://localhost:8000
# - Production CI/CD: auto-set to production domain via GitHub Actions
ARG VITE_API_BASE_URL=
ARG VITE_GA_MEASUREMENT_ID=
ARG VITE_GA_COOKIE_DOMAIN=

# Copy dependencies from deps stage
COPY --from=deps /app/node_modules ./node_modules

# Copy source code
COPY apps/web .

# Build the app with environment variable
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_GA_MEASUREMENT_ID=${VITE_GA_MEASUREMENT_ID}
ENV VITE_GA_COOKIE_DOMAIN=${VITE_GA_COOKIE_DOMAIN}
RUN --mount=type=cache,target=/app/node_modules/.cache \
    --mount=type=cache,target=/app/node_modules/.vite \
    npm run build

# ============== Stage 3: Production ==============
FROM public.ecr.aws/docker/library/nginx:alpine AS runner

# Copy built assets into nginx web root
COPY --from=builder /app/dist /usr/share/nginx/html
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 3000

# Serve the built static files
CMD ["nginx", "-g", "daemon off;"]
