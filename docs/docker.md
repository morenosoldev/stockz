# Docker Deployment Guide

This document describes how to run Recover-Bot using Docker and Docker Compose for local development and production deployment.

## Quick Start

### Prerequisites
- Docker 20.10+
- Docker Compose v2+

### Local Development

1. **Start PostgreSQL only** (recommended for development):
   ```bash
   make db-up
   # or
   docker compose up -d postgres
   ```

2. **Run migrations**:
   ```bash
   make db-migrate
   # or
   alembic upgrade head
   ```

3. **Start FastAPI locally** (with hot-reload):
   ```bash
   make dev
   # or
   uvicorn src.api.main:app --reload
   ```

### Full Stack (Docker)

Run both PostgreSQL and FastAPI in containers:

```bash
docker compose up -d
```

Access:
- **API**: http://localhost:8000
- **Swagger UI**: http://localhost:8000/docs
- **PostgreSQL**: localhost:5432

## Architecture

### Services

#### PostgreSQL
- **Image**: `postgres:15-alpine`
- **Port**: 5432
- **Credentials**: recoverbot/recoverbot
- **Database**: recoverbot
- **Volume**: `postgres_data` (persistent storage)
- **Health Check**: `pg_isready` every 10s

#### FastAPI API
- **Build**: Custom Dockerfile (Python 3.13-slim)
- **Port**: 8000
- **Auto-reload**: Enabled in development
- **Health Check**: `GET /health` every 30s
- **Volumes**:
  - `./src:/app/src` - Hot-reload source code
  - `./config:/app/config` - Configuration files

### Network
- **Bridge network**: `recoverbot-network`
- Services communicate via service names (e.g., `postgres:5432`)

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and customize:

```bash
cp .env.example .env
```

**Key variables**:
```bash
# Database
DATABASE_URL=postgresql://recoverbot:recoverbot@postgres:5432/recoverbot

# Application
APP_DEBUG=false
LOG_LEVEL=INFO

# Scheduler
CRON_SCHEDULE=30 16 * * *
SCHEDULER_ENABLED=true

# Scanner
UNIVERSE_SIZE=2000
CONCURRENCY=50
```

See `.env.example` for full configuration options.

### Docker Compose Profiles

Run specific services:

```bash
# PostgreSQL only
docker compose up -d postgres

# Full stack
docker compose up -d

# With custom env file
docker compose --env-file .env.production up -d
```

## Common Commands

### Build & Start
```bash
# Build images
docker compose build

# Start services
docker compose up -d

# View logs
docker compose logs -f

# Follow specific service logs
docker compose logs -f api
docker compose logs -f postgres
```

### Stop & Clean
```bash
# Stop services
docker compose down

# Stop and remove volumes (⚠️ deletes data)
docker compose down -v

# Remove all containers and images
docker compose down --rmi all
```

### Database Operations
```bash
# Run migrations
docker compose exec api alembic upgrade head

# Connect to PostgreSQL
docker compose exec postgres psql -U recoverbot -d recoverbot

# Backup database
docker compose exec postgres pg_dump -U recoverbot recoverbot > backup.sql

# Restore database
docker compose exec -T postgres psql -U recoverbot recoverbot < backup.sql
```

### Health Checks
```bash
# Check service status
docker compose ps

# Check API health
curl http://localhost:8000/health

# Check PostgreSQL
docker compose exec postgres pg_isready -U recoverbot
```

## Development Workflow

### 1. First-Time Setup
```bash
# Clone repository
git clone <repo-url>
cd stockz

# Copy environment file
cp .env.example .env

# Start PostgreSQL
make db-up

# Run migrations
make db-migrate

# Start API (local, with hot-reload)
make dev
```

### 2. Daily Development
```bash
# Ensure PostgreSQL is running
docker compose ps postgres

# Start API locally
make dev

# Run tests
make test

# Format code
make format

# Lint code
make lint
```

### 3. Testing Full Stack
```bash
# Start everything in Docker
docker compose up -d

# View logs
docker compose logs -f

# Test API
curl http://localhost:8000/health

# Stop when done
docker compose down
```

## Production Deployment

### Build Production Image

Create `docker-compose.prod.yaml`:

```yaml
services:
  postgres:
    # Same as development

  api:
    build:
      context: .
      dockerfile: docker/Dockerfile
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - APP_DEBUG=false
      - LOG_LEVEL=WARNING
    # Remove --reload flag for production
    command: uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 4
    restart: unless-stopped
```

Deploy:
```bash
docker compose -f docker-compose.prod.yaml up -d
```

### Security Considerations

1. **Use secrets** for sensitive data:
   ```bash
   docker secret create postgres_password /path/to/password
   ```

2. **Run as non-root** (already configured in Dockerfile)

3. **Use environment-specific configs**:
   - Development: `docker-compose.yaml`
   - Production: `docker-compose.prod.yaml`

4. **Limit resource usage**:
   ```yaml
   deploy:
     resources:
       limits:
         cpus: '2'
         memory: 2G
   ```

## Troubleshooting

### PostgreSQL won't start
```bash
# Check logs
docker compose logs postgres

# Reset volume
docker compose down -v
docker compose up -d postgres
```

### API can't connect to database
```bash
# Verify network
docker network inspect stockz_recoverbot-network

# Check DATABASE_URL
docker compose exec api env | grep DATABASE_URL

# Verify PostgreSQL is healthy
docker compose ps postgres
```

### Migrations fail
```bash
# Check database connection
docker compose exec postgres psql -U recoverbot -d recoverbot -c "SELECT 1;"

# Run migrations manually
docker compose exec api alembic upgrade head

# Check Alembic version
docker compose exec api alembic current
```

### Port conflicts
```bash
# Change ports in docker-compose.yaml
ports:
  - "5433:5432"  # Use 5433 on host instead
```

## Advanced Usage

### Custom Network
```yaml
networks:
  recoverbot-network:
    external: true
    name: custom-network
```

### Volume Backups
```bash
# Create volume backup
docker run --rm -v stockz_postgres_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/postgres-backup.tar.gz -C /data .

# Restore volume backup
docker run --rm -v stockz_postgres_data:/data -v $(pwd):/backup \
  alpine tar xzf /backup/postgres-backup.tar.gz -C /data
```

### Multi-Stage Builds
The Dockerfile uses multi-stage builds for optimization. To customize:

```dockerfile
# Development target
docker build --target base -t recover-bot:dev .

# Production target (add in Dockerfile)
FROM base AS production
RUN pip install --no-dev ...
```

## Monitoring

### Resource Usage
```bash
# Container stats
docker stats

# Service-specific stats
docker stats recoverbot-api recoverbot-postgres
```

### Logs
```bash
# All logs
docker compose logs

# Follow logs
docker compose logs -f

# Last 100 lines
docker compose logs --tail=100

# Specific service
docker compose logs -f api
```

## References

- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [PostgreSQL Docker Hub](https://hub.docker.com/_/postgres)
- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/docker/)
