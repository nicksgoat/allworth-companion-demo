#!/bin/bash

# Build and Test Local Containers Script
# This script builds the Docker images and starts the containers locally

set -e  # Exit on error

echo "🚀 Building Docker images..."

# Build backend
echo "📦 Building backend image..."
docker build -t kpi-backend:local ./backend

# Build frontend
echo "📦 Building frontend image..."
docker build -t kpi-frontend:local ./frontend

echo "✅ All images built successfully!"
echo ""
echo "🏃 Starting containers with docker-compose..."
docker-compose up -d

echo ""
echo "⏳ Waiting for services to be healthy..."
sleep 10

echo ""
echo "🔍 Checking service health..."
docker-compose ps

echo ""
echo "✅ Setup complete!"
echo ""
echo "📍 Access points:"
echo "   Frontend: http://localhost"
echo "   Backend:  http://localhost:5000/api/health"
echo ""
echo "📊 View logs with: docker-compose logs -f"
echo "🛑 Stop with: docker-compose down"
