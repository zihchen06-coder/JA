#!/bin/bash
# Double-click this file in Finder to open the Job Application Autofill UI.
# It handles the virtual environment for you -- nothing to type.

cd "$(dirname "$0")" || exit 1

if [ ! -d .venv ]; then
  echo "Setting up for the first time. This takes a few minutes..."
  python3 -m venv .venv || { echo "Could not create the environment. Is Python 3 installed?"; read -r; exit 1; }
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -q -r requirements.txt || { echo "Could not install dependencies."; read -r; exit 1; }
  python -m playwright install chromium
else
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

if [ ! -f profile.yaml ]; then
  cp profile.example.yaml profile.yaml
  echo "Created a starter profile.yaml -- fill it in on the 'My Profile' tab."
fi

python apply.py ui

echo
echo "Closed. You can close this window."
read -r
