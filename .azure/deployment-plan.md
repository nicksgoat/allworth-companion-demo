# Deployment Plan

Status: Planning

## Current State

- Backend: FastAPI app in `backend/`, container-ready with `backend/Dockerfile`.
- Frontend: Expo React Native app in `frontend/`, configured with EAS.
- Current hosting markers:
  - `backend/fly.toml` targets Fly.io.
  - `frontend/eas.json` production env points to `https://allworth-demo-api.fly.dev`.
- Azure infrastructure files are not present yet:
  - No `azure.yaml`
  - No `infra/`
  - No Bicep/Terraform templates
- Data mode: mock/synthetic data supported locally.
- LLM mode: Azure OpenAI supported by backend environment variables.

## Deployment Goals

- Deploy backend API with mock data and live Azure OpenAI GPT-4o tooling.
- Keep Azure OpenAI keys backend-only.
- Point frontend builds at the deployed backend URL.
- Preserve local mock-data development path.

## Recommended Azure Architecture

- Azure Container Apps for the FastAPI backend container.
- Azure Container Registry for backend image storage.
- Azure Log Analytics / Application Insights for logs and telemetry.
- Azure OpenAI as an existing external dependency configured through secrets.
- Expo/EAS for mobile app builds, with `EXPO_PUBLIC_API_URL` set to the backend URL.

## Required Decisions

- Azure subscription.
- Azure region.
- Backend public hostname.
- Whether to deploy backend to Azure or keep Fly.io for now.
- Whether frontend web should also be hosted on Azure Static Web Apps or remain Expo/EAS only.

## Required Secrets

Backend runtime only:

- `LLM_PROVIDER=azure_openai`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_VERSION`
- `LLM_CHAT_MODEL`
- `LLM_EXTRACT_MODEL`
- `MOBILEAPP_TOOL_MODE=demo`

Frontend build only:

- `EXPO_PUBLIC_API_URL`

## Validation Checklist

- Backend `/api/health` responds.
- `/tools/*` financial tool endpoints match `docs/FINANCIAL_TOOLS.md`.
- `/api/chat` streams tool events using mock data and Azure OpenAI.
- MCP smoke test passes.
- Frontend can reach deployed backend and render chat tool chips.
- No API keys are present in frontend config or committed files.

## Next Step

Confirm Azure target choices, then generate deployment artifacts and run Azure validation before deploying.
