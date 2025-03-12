#!/bin/bash
set -e

# Use the persistent /app/cache folder for the marker file
MARKER_FILE="/app/cache/.dependencies_installed"

if [ ! -f "$MARKER_FILE" ]; then
  echo "First run: Installing/upgrading pip and dependencies..."
  pip install --no-cache-dir --upgrade pip
  pip install --no-cache-dir -r requirements.txt

  if [ -n "$EXTRA_REQUIREMENTS" ]; then
    echo "Installing extra requirements: $EXTRA_REQUIREMENTS"
    pip install --no-cache-dir $EXTRA_REQUIREMENTS
  fi

  # Check and install specific packages if missing
  if ! python -c "import bs4" &>/dev/null; then
    echo "Installing beautifulsoup4..."
    pip install --no-cache-dir beautifulsoup4
  fi

  for package in requests lxml; do
    if ! python -c "import $package" &>/dev/null; then
      echo "Installing $package..."
      pip install --no-cache-dir $package
    fi
  done

  # Create the marker file to signal installation is complete
  touch "$MARKER_FILE"
fi

echo "Starting Matcherino Bot..."
exec python bot.py
