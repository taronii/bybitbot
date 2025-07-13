# Bybit Trading Bot - Cloud Run Deployment Instructions

## Updated Portfolio Settings
The bot has been updated with the following portfolio management settings:
- **Maximum concurrent positions**: 15 (up from 5)
- **Maximum portfolio risk**: 10% (up from 3%)
- **Maximum single position risk**: 0.8% (adjusted for 15 positions)

## Prerequisites
1. Google Cloud account with billing enabled
2. Google Cloud CLI (`gcloud`) installed
3. Docker installed (optional, Cloud Build will handle it)

## Quick Deployment Steps

### 1. Authenticate with Google Cloud
```bash
gcloud auth login
```

### 2. Set or Create Project
```bash
# Use existing project
gcloud config set project bybitbot-project

# OR create new project
gcloud projects create bybitbot-project --name="Bybit Trading Bot"
gcloud config set project bybitbot-project
```

### 3. Enable Required APIs
```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com containerregistry.googleapis.com
```

### 4. Deploy Backend
Navigate to the project directory and run:

```bash
cd "/Users/macbookpro/Desktop/サイト制作/🚀 Bybit最強完全自動売買ツール/bybit-ultimate-trading-bot"

# Option A: Use the automated deployment script
./deploy.sh

# Option B: Manual deployment
cd backend
gcloud builds submit --tag gcr.io/bybitbot-project/bybitbot-backend:latest

gcloud run deploy bybitbot-backend \
    --image gcr.io/bybitbot-project/bybitbot-backend:latest \
    --platform managed \
    --region asia-northeast1 \
    --allow-unauthenticated \
    --port 8080 \
    --memory 1Gi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 10 \
    --set-env-vars "ENCRYPTION_KEY=ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg="
```

### 5. Verify Deployment
After deployment, get the service URL:
```bash
gcloud run services describe bybitbot-backend \
    --platform managed \
    --region asia-northeast1 \
    --format 'value(status.url)'
```

Test the health endpoint:
```bash
curl https://YOUR-SERVICE-URL/health
```

## Important Configuration Changes

### Port Configuration
The backend Dockerfile has been updated to use port 8080 (required by Cloud Run):
- Changed from port 8000 to 8080
- Updated health check endpoint

### Portfolio Manager Settings
The following settings are now active in `backend/app/trading/portfolio_manager.py`:
```python
max_concurrent_positions: int = 15  # Increased from 5
max_portfolio_risk: float = 0.10    # 10% (increased from 3%)
max_single_position_risk: float = 0.008  # 0.8% per position
```

## Monitoring and Logs

View deployment logs:
```bash
gcloud run logs read --service=bybitbot-backend --region=asia-northeast1
```

View real-time logs:
```bash
gcloud run logs tail --service=bybitbot-backend --region=asia-northeast1
```

## Cost Optimization

The deployment is configured with:
- **Min instances**: 0 (scales to zero when not in use)
- **Max instances**: 10 (can handle traffic spikes)
- **Memory**: 1Gi (sufficient for trading operations)
- **CPU**: 1 (adequate for the workload)

## Troubleshooting

### If deployment fails:
1. Check if all APIs are enabled
2. Verify project billing is enabled
3. Check Docker build logs in Cloud Console

### If health check fails:
1. Wait 30-60 seconds for cold start
2. Check logs for startup errors
3. Verify the service URL is correct

### Common issues:
- **Port mismatch**: Ensure Dockerfile uses port 8080
- **Memory issues**: Increase memory if needed (--memory 2Gi)
- **API permissions**: Ensure all required APIs are enabled

## Next Steps
1. Deploy the frontend (optional)
2. Set up custom domain (optional)
3. Configure monitoring and alerts
4. Test trading functionality with small amounts first

## Security Notes
- The encryption key is hardcoded for demo purposes
- In production, use Google Secret Manager for sensitive data
- Consider implementing authentication for production use