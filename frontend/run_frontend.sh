#!/usr/bin/env bash
# Quickstart script to launch the BFSContext Comparison Dashboard

cd "$(dirname "$0")/.."
echo "Starting BFSContext Dashboard on http://localhost:5000..."
.venv/bin/python3 frontend/app.py
