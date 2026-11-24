#!/bin/sh
set -eu
API_UPSTREAM="${API_UPSTREAM:-api:8000}"
export API_UPSTREAM
CONF=/tmp/nginx.conf
envsubst '${API_UPSTREAM}' < /etc/nginx/nginx.conf.template > "${CONF}"
exec nginx -c "${CONF}" -g 'daemon off;'
