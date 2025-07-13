#!/bin/bash

# Bybit Trading Bot - Google Cloud Run Deployment Script
# This script deploys the updated backend with new portfolio settings to Cloud Run

set -e  # Exit on error

echo "🚀 Starting Bybit Trading Bot deployment to Google Cloud Run..."

# Configuration
PROJECT_ID="bybitbot-465812"
REGION="asia-northeast1"
BACKEND_SERVICE="bybitbot-backend"
FRONTEND_SERVICE="bybitbot-frontend"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[STATUS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if gcloud is authenticated
print_status "Checking Google Cloud authentication..."
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    print_error "No active Google Cloud account found!"
    echo "Please run: gcloud auth login"
    exit 1
fi

# Set project
print_status "Setting project to: $PROJECT_ID"
gcloud config set project $PROJECT_ID 2>/dev/null || {
    print_warning "Project $PROJECT_ID might not exist. Creating it..."
    read -p "Do you want to create the project? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        gcloud projects create $PROJECT_ID --name="Bybit Trading Bot" || {
            print_error "Failed to create project. It might already exist."
        }
    else
        exit 1
    fi
}

# Enable required APIs
print_status "Enabling required Google Cloud APIs..."
gcloud services enable run.googleapis.com \
    cloudbuild.googleapis.com \
    containerregistry.googleapis.com \
    --project=$PROJECT_ID

# Get commit SHA for versioning
COMMIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "manual")
print_status "Using version tag: $COMMIT_SHA"

# Deploy Backend
print_status "Building and deploying backend..."
cd backend

# Build Docker image
print_status "Building backend Docker image..."
gcloud builds submit \
    --tag gcr.io/$PROJECT_ID/$BACKEND_SERVICE:$COMMIT_SHA \
    --tag gcr.io/$PROJECT_ID/$BACKEND_SERVICE:latest \
    --project=$PROJECT_ID \
    --timeout=20m

# Deploy to Cloud Run
print_status "Deploying backend to Cloud Run..."
gcloud run deploy $BACKEND_SERVICE \
    --image gcr.io/$PROJECT_ID/$BACKEND_SERVICE:latest \
    --platform managed \
    --region $REGION \
    --allow-unauthenticated \
    --port 8080 \
    --memory 1Gi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 10 \
    --set-env-vars "ENCRYPTION_KEY=ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=" \
    --project=$PROJECT_ID

# Get backend URL
BACKEND_URL=$(gcloud run services describe $BACKEND_SERVICE \
    --platform managed \
    --region $REGION \
    --format 'value(status.url)' \
    --project=$PROJECT_ID)

print_status "Backend deployed successfully!"
print_status "Backend URL: $BACKEND_URL"

# Verify deployment
print_status "Verifying backend deployment..."
HEALTH_CHECK_URL="$BACKEND_URL/health"
print_status "Checking health endpoint: $HEALTH_CHECK_URL"

# Wait a bit for the service to be ready
sleep 5

# Check health endpoint
if curl -f -s "$HEALTH_CHECK_URL" > /dev/null; then
    print_status "✅ Backend health check passed!"
    echo "Backend is running with:"
    echo "  - Max concurrent positions: 15"
    echo "  - Max portfolio risk: 10%"
    echo "  - Port: 8080"
else
    print_warning "Health check failed. The service might still be starting up."
    echo "You can check the logs with:"
    echo "gcloud run logs read --service=$BACKEND_SERVICE --region=$REGION --project=$PROJECT_ID"
fi

# Optional: Deploy Frontend
read -p "Do you want to deploy the frontend as well? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    cd ../frontend
    
    print_status "Building frontend Docker image..."
    gcloud builds submit \
        --tag gcr.io/$PROJECT_ID/$FRONTEND_SERVICE:$COMMIT_SHA \
        --tag gcr.io/$PROJECT_ID/$FRONTEND_SERVICE:latest \
        --project=$PROJECT_ID \
        --timeout=20m
    
    print_status "Deploying frontend to Cloud Run..."
    gcloud run deploy $FRONTEND_SERVICE \
        --image gcr.io/$PROJECT_ID/$FRONTEND_SERVICE:latest \
        --platform managed \
        --region $REGION \
        --allow-unauthenticated \
        --port 80 \
        --memory 512Mi \
        --cpu 1 \
        --min-instances 0 \
        --max-instances 10 \
        --set-env-vars "REACT_APP_API_URL=$BACKEND_URL" \
        --project=$PROJECT_ID
    
    FRONTEND_URL=$(gcloud run services describe $FRONTEND_SERVICE \
        --platform managed \
        --region $REGION \
        --format 'value(status.url)' \
        --project=$PROJECT_ID)
    
    print_status "✅ Frontend deployed successfully!"
    print_status "Frontend URL: $FRONTEND_URL"
fi

echo
print_status "🎉 Deployment completed!"
echo
echo "Useful commands:"
echo "  View backend logs:  gcloud run logs read --service=$BACKEND_SERVICE --region=$REGION --project=$PROJECT_ID"
echo "  View backend info:  gcloud run services describe $BACKEND_SERVICE --region=$REGION --project=$PROJECT_ID"
echo "  Update env vars:    gcloud run services update $BACKEND_SERVICE --update-env-vars KEY=VALUE --region=$REGION --project=$PROJECT_ID"
echo
echo "Backend URL: $BACKEND_URL"