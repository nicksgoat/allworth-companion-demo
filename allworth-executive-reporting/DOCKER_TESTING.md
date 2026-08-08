# Local Docker Testing Guide

## Prerequisites
- Docker Desktop installed and running
- Azure credentials configured (for Synapse connectivity)

## Quick Start

### 1. Setup Environment
```bash
# Copy the example environment file and configure your values
cp .env.example .env
```

Edit `.env` with your Azure Synapse details.

### 2. Build and Run
```bash
# Make the build script executable
chmod +x build-local.sh

# Build and start the containers
./build-local.sh
```

Or manually:
```bash
# Build images
docker-compose build

# Start containers
docker-compose up -d

# View logs
docker-compose logs -f
```

### 3. Access the Application
- **Frontend**: http://localhost
- **Backend API**: http://localhost:5000/api/health

### 4. Development Commands

```bash
# View logs
docker-compose logs -f backend
docker-compose logs -f frontend

# Rebuild after code changes
docker-compose up -d --build

# Stop containers
docker-compose down

# Stop and remove volumes
docker-compose down -v

# View running containers
docker-compose ps

# Execute commands in containers
docker-compose exec backend python --version
docker-compose exec frontend sh
```

## Testing

### Backend Health Check
```bash
curl http://localhost:5000/api/health
```

### Frontend Check
```bash
curl http://localhost/
```

### Check Container Logs
```bash
# All services
docker-compose logs

# Specific service
docker-compose logs backend
docker-compose logs frontend

# Follow logs
docker-compose logs -f
```

## Troubleshooting

### Container won't start
```bash
# Check logs
docker-compose logs

# Rebuild from scratch
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Port conflicts
If ports 80 or 5000 are already in use, modify [docker-compose.yml](docker-compose.yml):
```yaml
ports:
  - "8080:80"  # Change frontend to port 8080
  - "5001:5000"  # Change backend to port 5001
```

### Azure Authentication Issues
The backend uses Azure AD Interactive authentication for Synapse. Ensure:
- You're logged into Azure CLI: `az login`
- Your account has access to the Synapse workspace

## Architecture

```
┌─────────────┐         ┌─────────────┐         ┌──────────────┐
│   Browser   │ ──────▶ │   Nginx     │ ──────▶ │    Flask     │
│             │  :80    │  (Frontend) │  :5000  │   (Backend)  │
└─────────────┘         └─────────────┘         └──────────────┘
                              │                         │
                              │                         │
                         React App               Azure Synapse
                         (TypeScript)            (SQL Server)
```

## Next Steps

After successful local testing:
1. Test the GitHub Actions workflow
2. Deploy to Azure Web App
3. Configure Azure Web App environment variables
