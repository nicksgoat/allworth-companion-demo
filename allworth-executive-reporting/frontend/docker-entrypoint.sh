#!/bin/sh

# Determine backend host:
# - In Azure Web App multi-container, containers can communicate via service name
# - Default is 'backend' which works for both local docker-compose and Azure
BACKEND_HOST=${BACKEND_HOST:-backend}

echo "Starting nginx with BACKEND_HOST=$BACKEND_HOST"

# Replace placeholder in nginx config
sed -i "s/BACKEND_HOST/$BACKEND_HOST/g" /etc/nginx/conf.d/default.conf

# Show the resulting proxy_pass line for debugging
grep proxy_pass /etc/nginx/conf.d/default.conf

# Start nginx
exec nginx -g 'daemon off;'
