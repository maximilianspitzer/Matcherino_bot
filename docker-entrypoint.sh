#!/bin/bash
set -e

echo "Starting Matcherino Bot..."

# Install or upgrade pip
echo "Ensuring pip is up-to-date..."
pip install --no-cache-dir --upgrade pip

# Install requirements
echo "Installing dependencies from requirements.txt..."
pip install --no-cache-dir -r requirements.txt

# If additional requirements are specified, install them too
if [ -n "$EXTRA_REQUIREMENTS" ]; then
  echo "Installing extra requirements: $EXTRA_REQUIREMENTS"
  pip install --no-cache-dir $EXTRA_REQUIREMENTS
fi

# Test if beautifulsoup4 is installed (this was missing in the error)
if ! python -c "import bs4" &>/dev/null; then
  echo "BeautifulSoup not found, installing..."
  pip install --no-cache-dir beautifulsoup4
fi

# Test if other commonly needed packages are installed
for package in requests lxml; do
  if ! python -c "import $package" &>/dev/null; then
    echo "$package not found, installing..."
    pip install --no-cache-dir $package
  fi
done

# Run the bot
echo "Starting bot..."
exec python bot.py 