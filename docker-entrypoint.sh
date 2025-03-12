#!/bin/bash
set -e

# Check if the marker file exists in the persistent volume
if [ ! -f /app/cache/.dependencies_installed ]; then
  echo "Installing/upgrading pip and dependencies..."
  pip install --no-cache-dir --upgrade pip
  pip install --no-cache-dir -r requirements.txt

  if [ -n "$EXTRA_REQUIREMENTS" ]; then
    echo "Installing extra requirements: $EXTRA_REQUIREMENTS"
    pip install --no-cache-dir $EXTRA_REQUIREMENTS
  fi

  # Optionally install any missing packages
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

  # Create the marker file in the persistent volume
  touch /app/cache/.dependencies_installed
fi

echo "Starting Matcherino Bot..."
exec python bot.py
