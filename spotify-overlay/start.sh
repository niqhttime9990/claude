#!/usr/bin/env bash
# Run to launch the Spotify Overlay on macOS / Linux.
cd "$(dirname "$0")" || exit 1

if ! command -v node >/dev/null 2>&1; then
  echo "Node.js isn't installed. Get it from https://nodejs.org then run this again."
  exit 1
fi

[ -d node_modules ] || npm install || { echo "npm install failed."; exit 1; }
npm start
