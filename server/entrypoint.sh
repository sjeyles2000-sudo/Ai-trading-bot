#!/bin/sh
set -eu
if [ "$(id -u)" = "0" ]; then
  if [ ! -d /data ]; then
    echo "Persistent /data mount missing; refusing to start" >&2
    exit 1
  fi
  chown paper:paper /data
  exec gosu paper "$@"
fi
if [ "$(id -u)" = "$(id -u paper)" ]; then
  exec "$@"
fi
echo "Unexpected runtime user; refusing to start" >&2
exit 1
