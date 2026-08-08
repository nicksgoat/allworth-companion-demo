# Allworth Executive Reporting

A real-time executive reporting dashboard for tracking organic growth metrics and net flows across acquisition channels. Built with React + TypeScript frontend and Flask + Python backend, containerized with Docker, and connected to Azure Synapse.

## Repository

**URL**: https://allworth.ghe.com/AllworthIntelligence/allworth-executive-reporting

| Branch | Description |
|--------|-------------|
| `main` | Production-ready code |
| `dev` | Development and testing |

![Dashboard Preview](docs/dashboard-preview.png)

## Features

- **Real-time metrics** from Azure Synapse dedicated SQL pool
- **Two data panels**:
  - **Net Flows Column** (left): Net Flows, NCNM, ECNM, Distributions, Attrition
  - **Organic Growth Grid** (right): NCNM, Clients, Appointments, Leads across channels
- **Channel breakdown**: Total, Advisor Enabled, CRP, Paid Leads, Media
- **Period comparison**: View current month vs prior months
- **Pro-rated comparisons**: Current month values are pro-rated based on days elapsed
- **Previous Year (PY) and Plan comparisons** for each metric

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

## Quick Start (Docker)

### Prerequisites

- Docker Desktop installed and running
- Azure Synapse credentials (SQL auth or Service Principal)

### 1. Configure Credentials

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env and add your credentials:
# - For SQL Auth: SYNAPSE_USERNAME and SYNAPSE_PASSWORD
# - For Service Principal: AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID
```

### 2. Build and Run

```bash
# Build and start all containers
./build-local.sh

# Or manually:
docker-compose up -d
```

### 3. Access the Dashboard

- **Frontend**: http://localhost
- **Backend API**: http://localhost:5000/api/health

### 4. View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f frontend
```

### 5. Stop Containers

```bash
docker-compose down
```

## Local Development (Non-Docker)

See [DOCKER_TESTING.md](DOCKER_TESTING.md) for alternative local development setup.

## Local Preview (No Auth, No Backend)

Use this when you just want to **view and update visual changes** to the
dashboard without signing in or connecting to Synapse. It renders bundled demo
data with Vite hot-reload.

```bash
cd frontend
npm install
npm run dev:demo
```

Then open the printed URL (default http://localhost:5173). Edits to
`src/**` (e.g. `App.tsx`, `App.css`, `components/`) hot-reload instantly.

- No Entra/SSO sign-in (`VITE_ENTRA_CLIENT_ID` is unset).
- No Flask backend or Synapse connection required (data comes from
  `src/data/demoMetrics.ts`).
- Enabled by `VITE_DEMO_MODE=true` in `frontend/.env.demo` (loaded via
  `vite --mode demo`).


## Project Structure

```
allworth-executive-reporting/
├── backend/
│   ├── app.py              # Flask API server
│   ├── requirements.txt    # Python dependencies
│   ├── Dockerfile          # Backend container image
│   └── .dockerignore       # Docker build exclusions
├── frontend/
│   ├── src/
│   │   ├── App.tsx         # Main dashboard component
│   │   ├── App.css         # Dashboard styles
│   │   ├── main.tsx        # Bootstrap and data fetching
│   │   ├── components/
│   │   │   └── KpiTile.tsx # Individual KPI tile component
│   │   ├── services/
│   │   │   └── api.ts      # API client for backend
│   │   └── types/
│   │       └── kpi.ts      # TypeScript types
│   ├── package.json        # Node dependencies
│   ├── Dockerfile          # Frontend container image
│   ├── nginx.conf          # Nginx configuration
│   └── .dockerignore       # Docker build exclusions
├── docker-compose.yml      # Multi-container orchestration
├── build-local.sh          # Automated build script
├── .env.example            # Environment template
├── .gitignore              # Git exclusions
├── DOCKER_TESTING.md       # Container testing guide
├── CONTAINER_STATUS.md     # Container build status
└── README.md
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Health check |
| `GET /api/all-metrics` | **Combined** — returns KPI, net flows, and detailed metrics in one response (preferred) |
| `GET /api/kpi-metrics` | Organic growth metrics (NCNM, Clients, Appointments, Leads) |
| `GET /api/net-flows` | Net flows metrics (Net Flows, NCNM, ECNM, Distributions, Attrition) |
| `GET /api/kpi-metrics-detailed` | Detailed KPI metrics with channel_middle granularity |
| `POST /api/cache-clear` | Force-clear the server-side response cache |
| `POST /api/track` | Record a page-view event (fire-and-forget from frontend) |
| `GET /api/analytics` | Page-view analytics summary (total views, unique visitors, daily breakdown) |
| `* /api/nfbc/*` | **NFBC Adjustment Console** — Jira queue, household investigation, and write-capable NFBC flow adjustments (see below) |

### NFBC Adjustment Console (`/nfbc`)

A self-contained module for the Net Flows Bonus Calculation (NFBC) adjustment
workflow: read an NFBC Jira ticket, auto-resolve the household(s), review the
recommended flow adjustment, then **preview → confirm** the write into
`tho.NFBC_Adjustment` and re-run the rollforward stored procedures so the
advisor scorecard reflects the correction.

- **UI**: React page at `/nfbc` (SSO-gated, styles scoped under `.nfbc-console`).
- **Backend**: blueprint at `/api/nfbc` (`backend/nfbc/`). Reuses the shared
  `get_database_connection()` pool and the global JWT middleware; writes go
  through a 5-minute SHA-256 preview token. Physical table/column names are
  resolved from the TML semantic-layer registry in `backend/nfbc/semantic_layer/`.
- **Config**: requires `JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` in `backend/.env`
  (see `.env.example`). Without them the page loads but the ticket queue is empty.

Key endpoints (all under `/api/nfbc`): `GET /tickets`, `GET /resolve-ticket/<key>`,
`GET /investigate/<avhhid>`, `POST /preview`, `POST /confirm`,
`POST /rollforward`, `GET /audit`, and `POST|PUT|DELETE /adjustment`.

## Data Sources

### Organic Growth Metrics (`/api/kpi-metrics`)
- **Source Tables**: `aip.goals_20260109`, `tho.Combined_Fact_Hashed`
- **Metrics**: Leads, Appointments, New Clients, NCNM
- **Channels**: Advisor Driven, CRP, Paid Leads, Radio, Other Media, Target Market (aggregated to Media)

### Net Flows Metrics (`/api/net-flows`)
- **Source Tables**: `tho.Household_Rollforward`, `aip.Goals_Net_Flows_2025`, `aip.DateDimension`
- **Metrics**: Net Flows, NCNM, ECNM, Distributions, Attrition

## Configuration

### Backend Environment

The backend connects to Azure Synapse using Azure AD Interactive authentication. Configure in `backend/app.py`:

```python
SERVER = 'allworthsynapse.sql.azuresynapse.net'
DATABASE = 'DataWarehouse'
```

### Frontend Environment

Create a `.env` file in the frontend directory:

```env
VITE_API_URL=http://localhost:5000/api
```

## Development

### Running Tests

```bash
# Backend
cd backend
python -m pytest

# Frontend
cd frontend
npm test
```

### Building for Production

```bash
# Frontend
cd frontend
npm run build
```

## Troubleshooting

### Deployed Code Not Showing on Website
If you push changes to the dev or main branch and the deployment succeeds but the website still shows old code:

**Cause**: Azure Web Apps can cache Docker images even when new images are built with unique SHA tags.

**Solution**: The deployment workflow now includes:
1. `pull_policy: always` in the docker-compose configuration to force pulling fresh images
2. An explicit restart step after deployment to ensure containers use the new images

If issues persist, manually restart the web app in Azure Portal or run:
```bash
# For dev slot
az webapp restart --name allworth-executive-reporting --resource-group analytics-insights-westus --slot dev

# For production
az webapp restart --name allworth-executive-reporting --resource-group analytics-insights-westus
```

### "Connection is busy with results for another command"
This occurs when parallel requests hit Azure Synapse. The frontend fetches endpoints sequentially to avoid this.

### Azure AD Authentication Popup Not Appearing
1. Ensure you're logged into Azure AD
2. Check your network connection
3. Verify you have access to the DataWarehouse
4. Try accessing Synapse in Azure Portal first

### ODBC Driver Not Found
Install ODBC Driver 17 for SQL Server:
- Windows: [Download from Microsoft](https://docs.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)
- macOS: `brew install msodbcsql17`

## License

Internal use only - Allworth Financial
