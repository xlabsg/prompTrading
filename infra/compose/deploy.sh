#!/bin/bash
# Production Deployment Script
# Pulls latest images and restarts services with zero downtime

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env"

# Helper functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root or with sudo
if [ "$EUID" -eq 0 ]; then
    log_warn "Running as root. Consider using a non-root user with Docker permissions."
fi

# Check if .env file exists
if [ ! -f "$ENV_FILE" ]; then
    log_error ".env file not found!"
    log_info "Copy .env.example to .env and configure it:"
    echo "    cp .env.example .env"
    echo "    nano .env"
    exit 1
fi

# Load environment variables
source "$ENV_FILE"

# Check required environment variables
REQUIRED_VARS=("GITHUB_ORG" "TRADING_API_ENCRYPTION_KEY")
for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        log_error "Required environment variable $var is not set in .env"
        exit 1
    fi
done

log_info "Starting deployment process..."
log_info "Organization: $GITHUB_ORG"
log_info "Image Tag: ${IMAGE_TAG:-latest}"

# Check if logged in to GitHub Container Registry
log_info "Checking GitHub Container Registry authentication..."
if ! docker login ghcr.io -u dummy -p dummy 2>&1 | grep -q "unauthorized"; then
    log_warn "Not logged in to GitHub Container Registry"
    log_info "Login with: echo \$PAT | docker login ghcr.io -u USERNAME --password-stdin"
    read -p "Do you want to continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Pull latest images
log_info "Pulling latest images from GitHub Container Registry..."
docker compose -f "$COMPOSE_FILE" pull

# Check if services are already running
if docker compose -f "$COMPOSE_FILE" ps | grep -q "Up"; then
    log_info "Services are running. Performing rolling update..."

    # Rolling update strategy
    docker compose -f "$COMPOSE_FILE" up -d --no-deps --build web
    sleep 5
    docker compose -f "$COMPOSE_FILE" up -d --no-deps --build api
    sleep 5
    docker compose -f "$COMPOSE_FILE" up -d --no-deps --build worker

    log_info "Rolling update completed"
else
    log_info "Starting services for the first time..."
    docker compose -f "$COMPOSE_FILE" up -d
fi

# Wait for services to be healthy
log_info "Waiting for services to be healthy..."
sleep 10

# Check service health
log_info "Checking service health..."
docker compose -f "$COMPOSE_FILE" ps

# Display logs
log_info "Recent logs:"
docker compose -f "$COMPOSE_FILE" logs --tail=20

# Cleanup old images
log_info "Cleaning up old images..."
docker image prune -f

log_info "${GREEN}Deployment completed successfully!${NC}"
log_info "Services are running at:"
log_info "  - Frontend: http://localhost:3000"
log_info "  - API: http://localhost:8000"
log_info "  - API Docs: http://localhost:8000/docs"

# Show resource usage
log_info "Resource usage:"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" $(docker compose -f "$COMPOSE_FILE" ps -q)
