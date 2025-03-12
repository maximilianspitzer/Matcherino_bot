# Matcherino Bot - Unraid Installation Guide

This is a simplified guide for installing the Matcherino Discord bot on Unraid.

## Option 1: Install Using Unraid's Docker UI

1. In Unraid, go to the **Docker** tab
2. Click **Add Container**
3. Fill in these details:
   - **Name**: `matcherino-bot`
   - **Repository**: `ghcr.io/YOUR_GITHUB_USERNAME/matcherino-bot:latest`
   - Add these environment variables:
     - `BOT_TOKEN`: Your Discord bot token
     - `POSTGRES_PASSWORD`: A secure password
     - `MATCHERINO_TOURNAMENT_ID`: Your tournament ID

## Option 2: Install Using Docker Template

For an easier installation:

1. In Unraid, go to the **Docker** tab
2. Click **Add Container** at the bottom
3. In the **Template** field, paste:
   ```
   https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/matcherino-bot/main/matcherino-bot.xml
   ```
4. Click **Apply Template**
5. Fill in your Discord bot token and other settings
6. Click **Apply**

## Option 3: Using Docker Compose (Advanced)

If you prefer using Docker Compose:

1. SSH into your Unraid server
2. Create a directory:
   ```bash
   mkdir -p /mnt/user/appdata/matcherino-bot
   cd /mnt/user/appdata/matcherino-bot
   ```
3. Download the docker-compose file:
   ```bash
   curl -o docker-compose.yml https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/matcherino-bot/main/docker-compose.ghcr.yml
   ```
4. Create a .env file with your settings:
   ```bash
   echo "BOT_TOKEN=your_discord_bot_token" > .env
   echo "POSTGRES_PASSWORD=your_secure_password" >> .env
   echo "MATCHERINO_TOURNAMENT_ID=your_tournament_id" >> .env
   echo "GITHUB_USERNAME=YOUR_GITHUB_USERNAME" >> .env
   ```
5. Start the containers:
   ```bash
   docker-compose up -d
   ```

## Update the Bot

To update the bot, just:

1. Go to the Docker tab in Unraid
2. Click the update button next to the matcherino-bot container

Or, using the terminal:
```bash
cd /mnt/user/appdata/matcherino-bot
docker-compose pull
docker-compose up -d
``` 