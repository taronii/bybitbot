#!/bin/bash

# Bybit Trading Bot - Parallel Google Cloud Run Deployment Script
# This script deploys both backend and frontend to Cloud Run in parallel

set -e  # Exit on error

echo "🚀 Starting parallel deployment of Bybit Trading Bot to Google Cloud Run..."

# Configuration
PROJECT_ID="bybitbot-465812"
REGION="asia-northeast1"
BACKEND_SERVICE="bybitbot-backend"
FRONTEND_SERVICE="bybitbot-frontend"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
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
gcloud config set project $PROJECT_ID 2>/dev/null

# Enable required APIs
print_status "Enabling required Google Cloud APIs..."
gcloud services enable run.googleapis.com \
    cloudbuild.googleapis.com \
    containerregistry.googleapis.com \
    --project=$PROJECT_ID

# Get commit SHA for versioning
COMMIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "manual-$(date +%Y%m%d%H%M%S)")
print_status "Using version tag: $COMMIT_SHA"

# Create deployment logs directory
LOG_DIR="/tmp/bybit-deployment-logs"
mkdir -p "$LOG_DIR"

# Function to deploy backend
deploy_backend() {
    print_info "🔧 Starting backend deployment..."
    
    cd /Users/macbookpro/Desktop/サイト制作/🚀\ Bybit最強完全自動売買ツール/bybit-ultimate-trading-bot/backend
    
    # Build Docker image
    print_info "Building backend Docker image..."
    if gcloud builds submit \
        --tag gcr.io/$PROJECT_ID/$BACKEND_SERVICE:$COMMIT_SHA \
        --tag gcr.io/$PROJECT_ID/$BACKEND_SERVICE:latest \
        --project=$PROJECT_ID \
        --timeout=20m \
        > "$LOG_DIR/backend-build.log" 2>&1; then
        print_status "✅ Backend image built successfully"
    else
        print_error "❌ Backend build failed. Check $LOG_DIR/backend-build.log"
        return 1
    fi
    
    # Deploy to Cloud Run
    print_info "Deploying backend to Cloud Run..."
    if gcloud run deploy $BACKEND_SERVICE \
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
        --project=$PROJECT_ID \
        > "$LOG_DIR/backend-deploy.log" 2>&1; then
        print_status "✅ Backend deployed successfully"
        
        # Get backend URL
        BACKEND_URL=$(gcloud run services describe $BACKEND_SERVICE \
            --platform managed \
            --region $REGION \
            --format 'value(status.url)' \
            --project=$PROJECT_ID)
        
        echo "$BACKEND_URL" > "$LOG_DIR/backend-url.txt"
        print_status "Backend URL: $BACKEND_URL"
        print_info "Backend configuration:"
        print_info "  - Max positions: 30"
        print_info "  - Confidence threshold: 0.35"
        print_info "  - Scalping mode: Enabled"
    else
        print_error "❌ Backend deployment failed. Check $LOG_DIR/backend-deploy.log"
        return 1
    fi
}

# Function to deploy frontend
deploy_frontend() {
    print_info "🎨 Starting frontend deployment..."
    
    # Wait a bit to ensure backend URL is available
    sleep 5
    
    # Try to get backend URL from file
    if [ -f "$LOG_DIR/backend-url.txt" ]; then
        BACKEND_URL=$(cat "$LOG_DIR/backend-url.txt")
    else
        # If not available, get current backend URL
        BACKEND_URL=$(gcloud run services describe $BACKEND_SERVICE \
            --platform managed \
            --region $REGION \
            --format 'value(status.url)' \
            --project=$PROJECT_ID 2>/dev/null || echo "https://bybitbot-backend-elvv4omjba-an.a.run.app")
    fi
    
    cd /Users/macbookpro/Desktop/サイト制作/🚀\ Bybit最強完全自動売買ツール/bybit-ultimate-trading-bot/frontend
    
    # Build Docker image with backend URL
    print_info "Building frontend Docker image..."
    if gcloud builds submit \
        --tag gcr.io/$PROJECT_ID/$FRONTEND_SERVICE:$COMMIT_SHA \
        --tag gcr.io/$PROJECT_ID/$FRONTEND_SERVICE:latest \
        --project=$PROJECT_ID \
        --timeout=20m \
        > "$LOG_DIR/frontend-build.log" 2>&1; then
        print_status "✅ Frontend image built successfully"
    else
        print_error "❌ Frontend build failed. Check $LOG_DIR/frontend-build.log"
        return 1
    fi
    
    # Deploy to Cloud Run
    print_info "Deploying frontend to Cloud Run..."
    if gcloud run deploy $FRONTEND_SERVICE \
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
        --project=$PROJECT_ID \
        > "$LOG_DIR/frontend-deploy.log" 2>&1; then
        print_status "✅ Frontend deployed successfully"
        
        # Get frontend URL
        FRONTEND_URL=$(gcloud run services describe $FRONTEND_SERVICE \
            --platform managed \
            --region $REGION \
            --format 'value(status.url)' \
            --project=$PROJECT_ID)
        
        echo "$FRONTEND_URL" > "$LOG_DIR/frontend-url.txt"
        print_status "Frontend URL: $FRONTEND_URL"
        print_info "Frontend configuration:"
        print_info "  - 15 default selected currencies"
        print_info "  - Auto-trade threshold: 0.35"
        print_info "  - Connected to backend: $BACKEND_URL"
    else
        print_error "❌ Frontend deployment failed. Check $LOG_DIR/frontend-deploy.log"
        return 1
    fi
}

# Start parallel deployment
print_status "Starting parallel deployment..."

# Run deployments in background
deploy_backend &
BACKEND_PID=$!

deploy_frontend &
FRONTEND_PID=$!

# Monitor deployment progress
print_status "Deploying both services in parallel..."
print_info "You can monitor the logs in: $LOG_DIR"

# Wait for both deployments to complete
BACKEND_STATUS=0
FRONTEND_STATUS=0

wait $BACKEND_PID || BACKEND_STATUS=$?
wait $FRONTEND_PID || FRONTEND_STATUS=$?

echo
print_status "🎉 Deployment process completed!"
echo

# Check deployment results
if [ $BACKEND_STATUS -eq 0 ] && [ $FRONTEND_STATUS -eq 0 ]; then
    print_status "✅ Both services deployed successfully!"
    
    # Get URLs
    if [ -f "$LOG_DIR/backend-url.txt" ]; then
        BACKEND_URL=$(cat "$LOG_DIR/backend-url.txt")
    fi
    if [ -f "$LOG_DIR/frontend-url.txt" ]; then
        FRONTEND_URL=$(cat "$LOG_DIR/frontend-url.txt")
    fi
    
    # Verify deployments
    print_status "Verifying deployments..."
    
    # Check backend health
    if [ -n "$BACKEND_URL" ]; then
        print_info "Checking backend health..."
        if curl -f -s "$BACKEND_URL/health" > /dev/null 2>&1; then
            print_status "✅ Backend health check passed!"
        else
            print_warning "⚠️  Backend health check failed. Service might still be starting up."
        fi
    fi
    
    # Display summary
    echo
    print_status "📊 Deployment Summary:"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Backend URL:  $BACKEND_URL"
    echo "Frontend URL: $FRONTEND_URL"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    echo
    print_info "Updated Configuration:"
    print_info "Backend:"
    print_info "  - Max concurrent positions: 30 (increased from 15)"
    print_info "  - Confidence threshold: 0.35 (lowered from 0.40)"
    print_info "  - Scalping mode: Enabled"
    print_info "Frontend:"
    print_info "  - Default selected currencies: 15"
    print_info "  - Auto-trade threshold: 0.35 (lowered from 0.40)"
    
else
    print_error "❌ Deployment failed!"
    [ $BACKEND_STATUS -ne 0 ] && print_error "Backend deployment failed. Check $LOG_DIR/backend-*.log"
    [ $FRONTEND_STATUS -ne 0 ] && print_error "Frontend deployment failed. Check $LOG_DIR/frontend-*.log"
fi

echo
print_info "📋 Useful commands:"
echo "  View backend logs:  gcloud run logs read --service=$BACKEND_SERVICE --region=$REGION --project=$PROJECT_ID"
echo "  View frontend logs: gcloud run logs read --service=$FRONTEND_SERVICE --region=$REGION --project=$PROJECT_ID"
echo "  Backend details:    gcloud run services describe $BACKEND_SERVICE --region=$REGION --project=$PROJECT_ID"
echo "  Frontend details:   gcloud run services describe $FRONTEND_SERVICE --region=$REGION --project=$PROJECT_ID"
echo
echo "  View deployment logs:"
echo "    Backend build:    cat $LOG_DIR/backend-build.log"
echo "    Backend deploy:   cat $LOG_DIR/backend-deploy.log"
echo "    Frontend build:   cat $LOG_DIR/frontend-build.log"
echo "    Frontend deploy:  cat $LOG_DIR/frontend-deploy.log"