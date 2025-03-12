#!/bin/bash
set -e

# Only install dependencies if the marker file doesn't exist
if [ ! -f /app/.dependencies_installed ]; then
  echo "Installing/upgrading pip and dependencies..."
  pip install --no-cache-dir --upgrade pip
  pip install --no-cache-dir -r requirements.txt

  if [ -n "$EXTRA_REQUIREMENTS" ]; then
    echo "Installing extra requirements: $EXTRA_REQUIREMENTS"
    pip install --no-cache-dir $EXTRA_REQUIREMENTS
  fi

  # Optionally install any other packages conditionally
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

  # Create a marker file to indicate installation has been completed
  touch /app/.dependencies_installed
fi

echo "Starting Matcherino Bot..."
exec python bot.py
