# GitHub Actions Deployment

This repository uses GitHub Actions to automatically build and deploy to Azure Web App on every push to `main`.

## Setup Instructions

### 1. Azure Container Registry (ACR)

First, create an Azure Container Registry if you don't have one:

```bash
# Create ACR (if needed)
az acr create \
  --resource-group analytics-insights-westus \
  --name allworthacr \
  --sku Basic \
  --admin-enabled true

# Get ACR credentials
az acr credential show --name allworthacr
```

### 2. Configure Azure Web App for Containers

```bash
# Enable multi-container support with docker-compose
az webapp config container set \
  --resource-group analytics-insights-westus \
  --name allworth-executive-reporting \
  --multicontainer-config-type compose \
  --multicontainer-config-file docker-compose.azure.yml

# Enable container logging
az webapp log config \
  --resource-group analytics-insights-westus \
  --name allworth-executive-reporting \
  --docker-container-logging filesystem
```

### 3. Set Up GitHub Secrets

Go to your repository Settings → Secrets and variables → Actions, and add these secrets:

#### Required Secrets:

1. **ACR_USERNAME** - Azure Container Registry username
   ```bash
   az acr credential show --name allworthacr --query username -o tsv
   ```

2. **ACR_PASSWORD** - Azure Container Registry password
   ```bash
   az acr credential show --name allworthacr --query passwords[0].value -o tsv
   ```

3. **AZURE_CREDENTIALS** - Azure service principal credentials
   ```bash
   az ad sp create-for-rbac \
     --name "github-actions-allworth-reporting" \
     --role contributor \
     --scopes /subscriptions/a9fc166f-1e2f-45f9-81d7-d721c141dd2d/resourceGroups/analytics-insights-westus \
     --sdk-auth
   ```
   Copy the entire JSON output as the secret value.

4. **AUTH_METHOD** - `SqlPassword` or `ServicePrincipal`

5. **SYNAPSE_SERVER** - `allworthsynapse.sql.azuresynapse.net`

6. **SYNAPSE_DATABASE** - `DataWarehouse`

7. **SYNAPSE_USERNAME** - Your SQL admin username

8. **SYNAPSE_PASSWORD** - Your SQL admin password

9. **SF_USERNAME** - Salesforce integration username (used by SFP2)

10. **SF_PASSWORD** - Salesforce integration password (used by SFP2)

11. **SF_TOKEN** - Salesforce security token (used by SFP2)

### 4. Update Workflow Configuration

Edit `.github/workflows/azure-deploy.yml` and update:
- `ACR_NAME` if your ACR has a different name
- Any other environment-specific values

### 5. Deploy

Once secrets are configured, push to `main` branch:

```bash
git push origin main
```

The workflow will automatically:
1. Build both Docker images (backend + frontend)
2. Push images to Azure Container Registry
3. Deploy to Azure Web App
4. Configure application settings

### 6. Monitor Deployment

- **GitHub Actions**: Check the Actions tab in GitHub
- **Azure Portal**: Monitor deployment in Azure Web App deployment center
- **Logs**: View container logs in Azure Portal or via CLI:
  ```bash
  az webapp log tail --name allworth-executive-reporting --resource-group analytics-insights-westus
  ```

## Manual Deployment

To manually trigger a deployment without pushing code:

1. Go to Actions tab in GitHub
2. Select "Build and Deploy to Azure Web App"
3. Click "Run workflow"
4. Select `main` branch
5. Click "Run workflow"

## Troubleshooting

### Check container status
```bash
az webapp show \
  --name allworth-executive-reporting \
  --resource-group analytics-insights-westus \
  --query state
```

### View container logs
```bash
az webapp log tail \
  --name allworth-executive-reporting \
  --resource-group analytics-insights-westus
```

### Restart the app
```bash
az webapp restart \
  --name allworth-executive-reporting \
  --resource-group analytics-insights-westus
```

## Web App Configuration

The workflow automatically configures these app settings:
- `WEBSITES_ENABLE_APP_SERVICE_STORAGE=false`
- `WEBSITES_PORT=80`
- `DOCKER_ENABLE_CI=true`
- Database connection settings (from secrets)

Additional settings can be configured in the Azure Portal or added to the workflow.
