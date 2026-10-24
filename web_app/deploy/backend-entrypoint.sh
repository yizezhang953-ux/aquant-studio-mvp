#!/bin/sh
# Volumes are usually mounted root-owned: fix ownership of /data, then drop to the unprivileged user.
set -e
if [ "$(id -u)" = "0" ]; then
  mkdir -p /data/backups
  chown -R aquant:aquant /data
  exec setpriv --reuid=aquant --regid=aquant --init-groups "$@"
fi
exec "$@"
