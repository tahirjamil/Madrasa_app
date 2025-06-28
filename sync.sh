#!/bin/bash

echo "🔄 Pulling latest..."
git pull --no-rebase origin main

echo "✅ Adding changes..."
git add .

echo "✅ Committing local work..."
git commit -m "Auto sync commit" || echo "Nothing new to commit."

echo "🚀 Pushing to remote..."
git push origin main

echo "✅ All synced!"
