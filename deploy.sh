#!/bin/bash
# Deploy script for Frappe AI Studio
# Usage: ./deploy.sh [bench_path] [site_name]

set -e

BENCH_PATH="${1:-$HOME/frappe-bench}"
SITE_NAME="${2:-erp.local}"
APP_NAME="frappe_ai_studio"

echo "========================================"
echo "Frappe AI Studio Deployment"
echo "========================================"
echo "Bench path: $BENCH_PATH"
echo "Site: $SITE_NAME"
echo ""

# Check if bench exists
if [ ! -d "$BENCH_PATH" ]; then
    echo "Error: Bench not found at $BENCH_PATH"
    exit 1
fi

cd "$BENCH_PATH"

# Check if app is installed
if [ ! -d "apps/$APP_NAME" ]; then
    echo "Installing $APP_NAME..."
    bench get-app https://github.com/your-org/frappe-ai-studio.git
else
    echo "Updating $APP_NAME..."
    cd "apps/$APP_NAME"
    git pull origin main
    cd "$BENCH_PATH"
fi

# Install on site
echo "Installing app on site $SITE_NAME..."
bench --site "$SITE_NAME" install-app "$APP_NAME" || echo "App may already be installed"

# Migrate
echo "Running migration..."
bench --site "$SITE_NAME" migrate

# Build assets
echo "Building assets..."
bench build --app "$APP_NAME"

# Restart bench
echo "Restarting bench..."
bench restart

echo ""
echo "========================================"
echo "Deployment complete!"
echo "========================================"
echo "Access AI Studio from the Frappe desk"
echo "or press Cmd+K / Ctrl+K from any DocType"
