#!/bin/bash

echo "🔄 Pulling latest changes..."
git pull --no-rebase origin main

echo "✅ Pull done."

echo "✅ Adding local changes..."
git add .

echo "✅ Committing local changes..."
git commit -m "Auto-sync commit" || echo "Nothing to commit."

echo "🚀 Pushing to remote..."
git push origin main

echo "✅ All synced!"
