# Deploying Matcherino Bot on Unraid

This guide provides detailed instructions for deploying the Matcherino Discord bot on an Unraid server.

## Method 1: Docker Compose Deployment

The simplest method to deploy on Unraid using Docker Compose.

### Prerequisites
- Docker and Docker Compose installed on your Unraid server
- Git installed (or ability to transfer files to the server)

### Steps

1. **Create a directory for the bot on your Unraid server**:
   ```bash
   mkdir -p /mnt/user/appdata/matcherino_bot
   cd /mnt/user/appdata/matcherino_bot
   ```

2. **Clone the repository**:
   ```bash
   git clone https://github.com/yourusername/matcherino-bot.git .
   # Replace with your actual repository URL
   ```

3. **Create the environment file**:
   ```bash
   cp .env.example .env
   nano .env  # Edit with your actual credentials
   ```

4. **Deploy with Docker Compose**:
   ```bash
   # Using local build
   docker-compose up -d
   
   # OR using pre-built GitHub container image
   docker-compose -f docker-compose.ghcr.yml up -d
   ```

5. **Check logs to verify operation**:
   ```bash
   docker-compose logs -f bot
   ```

## Method 2: Automated Deployment with GitHub Actions

For automatic deployment whenever you push to your GitHub repository.

### Prerequisites
- SSH access to your Unraid server
- GitHub repository with the bot code

### Steps

1. **Generate an SSH key pair**:
   ```bash
   ssh-keygen -t ed25519 -C "github-actions-deploy"
   ```

2. **Add the public key to your Unraid server**:
   ```bash
   # On your local machine
   cat ~/.ssh/id_ed25519.pub
   
   # On the Unraid server
   nano ~/.ssh/authorized_keys
   # Paste the public key on a new line
   ```

3. **Add the private key and other secrets to GitHub**:
   - Go to your GitHub repository → Settings → Secrets and variables → Actions
   - Add the following secrets:
     - `SSH_PRIVATE_KEY`: The contents of your `~/.ssh/id_ed25519` file
     - `UNRAID_HOST`: Your Unraid server IP or hostname
     - `UNRAID_USER`: The user to connect to your Unraid server (usually 'root')
     - `BOT_TOKEN`: Your Discord bot token
     - `POSTGRES_PASSWORD`: A secure password for PostgreSQL
     - `MATCHERINO_TOURNAMENT_ID`: Your Matcherino tournament ID

4. **The workflow files are already in the repository**:
   - `.github/workflows/build-publish.yml` - Builds and publishes the container to GitHub Container Registry
   - `.github/workflows/deploy.yml` - Deploys to your Unraid server

5. **Trigger deployment by pushing to your repository**:
   ```bash
   git add .
   git commit -m "Update configuration"
   git push origin main
   ```

6. **Monitor the GitHub Actions workflows**:
   - Go to your repository on GitHub → Actions tab
   - You should see your workflows running

## Method 3: Using GitHub Container Registry

This method uses GitHub Container Registry to distribute your bot as a container image.

### Steps

1. **On your Unraid server**:
   ```bash
   mkdir -p /mnt/user/appdata/matcherino_bot
   cd /mnt/user/appdata/matcherino_bot
   
   # Download the docker-compose file
   curl -o docker-compose.yml https://raw.githubusercontent.com/yourusername/matcherino-bot/main/docker-compose.ghcr.yml
   
   # Create .env file with your credentials
   echo "BOT_TOKEN=your_discord_bot_token" > .env
   echo "POSTGRES_PASSWORD=your_secure_password" >> .env
   echo "MATCHERINO_TOURNAMENT_ID=your_tournament_id" >> .env
   echo "GITHUB_USERNAME=yourusername" >> .env
   
   # Start the containers
   docker-compose up -d
   ```

2. **Authentication (if needed)**:
   If your GitHub Container Registry image is private, you'll need to authenticate:
   ```bash
   # On your Unraid server
   docker login ghcr.io -u yourusername -p your_personal_access_token
   ```

## Method 4: Using the Unraid Docker Template

The most Unraid-friendly method using the built-in Community Applications.

### Steps

1. **In Unraid web UI**:
   - Go to the "Apps" tab
   - Click on "Community Applications"
   - Go to Settings → Template Repositories
   - Add: `https://raw.githubusercontent.com/yourusername/matcherino-bot/main/matcherino-bot.xml`
   - Click "Save"
   
2. **Install the container**:
   - Search for "matcherino" in the Apps search
   - Click the Matcherino Bot app
   - Fill in your settings (Bot Token, etc.)
   - Click "Apply"

3. **Authentication for Private Images**:
   If your GitHub Container Registry image is private, you'll need to add your credentials to Unraid:
   - In the Docker tab, click on "Settings"
   - Under "Registry credentials", add:
     - Registry: `ghcr.io`
     - Username: Your GitHub username
     - Password: Your GitHub personal access token with `read:packages` scope

## Troubleshooting

### GitHub Container Registry Access Issues
- Ensure your container image is public, or you've authenticated with GitHub credentials
- If using a private repository, you need a Personal Access Token with `read:packages` scope
- Check if you can pull the image manually: `docker pull ghcr.io/yourusername/matcherino-bot:latest`

### Database Connection Issues
- Check that the PostgreSQL container is running: `docker ps`
- Verify database credentials in the .env file
- Check logs: `docker-compose logs db`

### Bot Not Starting
- Verify your Discord bot token is correct
- Check bot logs: `docker-compose logs bot`
- Ensure your bot has proper permissions in Discord

### Network Connectivity
- Ensure Unraid's Docker network has internet access
- Check if the bot can reach the Discord API
- Test with: `docker exec matcherino-bot ping discord.com`

## Maintenance

### Updating the Bot
- When using Docker Compose with ghcr.io: `docker-compose -f docker-compose.ghcr.yml pull && docker-compose -f docker-compose.ghcr.yml up -d`
- When using GitHub Actions: just push to your repository
- When using the Unraid template: Update the container in the Docker tab

### Backing Up
- Database data is stored in Docker volumes
- Use the Unraid backup system to back up `/mnt/user/appdata/matcherino_bot`
- Consider using a backup plugin like CA Backup 