#!/bin/bash
# macOS equivalent of the Windows launcher, used for testing the same code path.
cd "$(dirname "$0")/solar_defect_camera" || exit 1
if [ ! -x ".venv/bin/python" ]; then
  echo "  First run: setting up..."
  python3 -m venv .venv || { echo "Could not create the environment."; read -r; exit 1; }
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -r requirements.txt || { echo "Install failed."; read -r; exit 1; }
fi
exec .venv/bin/python tools/launcher.py
