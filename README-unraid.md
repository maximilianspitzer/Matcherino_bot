# Matcherino Bot - Unraid Installation Guide

This guide shows how to install the Matcherino Discord bot on Unraid.

## Option 1: One-Click Installation (Recommended)

1. In Unraid, go to the **Docker** tab
2. Click **Add Container** at the bottom
3. In the **Template** field, paste:
   ```
   https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/matcherino-bot/main/matcherino-bot-stack.xml
   ```
4. Click **Apply Template**
5. Fill in your Discord bot token and other settings
6. Click **Apply**

This will automatically create:
- The Matcherino bot container
- A PostgreSQL database container
- All necessary connections between them

## Option 2: Manual Installation

1. In Unraid, go to the **Docker** tab
2. Click **Add Container**
3. Fill in these details:
   - **Name**: `matcherino-bot`
   - **Repository**: `ghcr.io/YOUR_GITHUB_USERNAME/matcherino-bot:latest`
   - Add these environment variables:
     - `BOT_TOKEN`: Your Discord bot token
     - `POSTGRES_PASSWORD`: A secure password
     - `MATCHERINO_TOURNAMENT_ID`: Your tournament ID
     - `EXTRA_REQUIREMENTS`: `beautifulsoup4 requests lxml`
   - Add a volume mapping:
     - Container path: `/app/cache`
     - Host path: `/mnt/user/appdata/matcherino-bot/cache`
4. Create a PostgreSQL container:
   - **Name**: `matcherino-db`
   - **Repository**: `postgres:14-alpine`
   - Add these environment variables:
     - `POSTGRES_PASSWORD`: Same password as above
     - `POSTGRES_DB`: `matcherino`
   - Add a volume mapping:
     - Container path: `/var/lib/postgresql/data`
     - Host path: `/mnt/user/appdata/matcherino-bot/database`

## Troubleshooting

### Missing Dependencies
If you encounter errors about missing Python modules:

1. Go to the Docker tab in Unraid
2. Click on matcherino-bot container details
3. Edit the container
4. Add or update the `EXTRA_REQUIREMENTS` variable with any missing packages
5. Apply and restart the container

## Update the Bot

To update to the latest version:

1. Go to the Docker tab in Unraid
2. Click the update button next to the matcherino-bot container

Or, using the terminal:
```bash
cd /mnt/user/appdata/matcherino-bot
docker-compose pull
docker-compose up -d
``` 