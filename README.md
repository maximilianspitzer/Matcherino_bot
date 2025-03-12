# Matcherino Tournament Discord Bot

A Discord bot that manages tournament registrations using PostgreSQL. The bot integrates with Matcherino to track tournament participants and provides admin commands to manage registrations.

## Features

- **User Registration**: Users can register for tournaments using `/register` command
- **Role Assignment**: Automatically assigns a "Registered" role to registered users
- **Admin Commands**: Admins can view and manage registered users
- **Matcherino Integration**: Syncs with Matcherino tournament data
- **PostgreSQL Database**: All registration data is stored in a PostgreSQL database

## Installation

### Method 1: Standard Python Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd matcherino-bot
```

2. Create a virtual environment and install dependencies:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

3. Create a `.env` file in the root directory with your credentials:
```
BOT_TOKEN=your_discord_bot_token
DATABASE_URL=postgresql://username:password@localhost/database_name
MATCHERINO_TOURNAMENT_ID=your_tournament_id
```

4. Run the bot:
```bash
python bot.py
```

### Method 2: Docker Installation

#### Option A: Build Locally
1. Clone this repository:
```bash
git clone <repository-url>
cd matcherino-bot
```

2. Create an `.env` file with your credentials (see above)

3. Build and run with Docker Compose:
```bash
docker-compose up -d
```

#### Option B: Use Pre-built Container from GitHub Container Registry
1. Create a directory for your configuration:
```bash
mkdir -p matcherino_bot
cd matcherino_bot
```

2. Create a `.env` file with your credentials:
```
BOT_TOKEN=your_discord_bot_token
DATABASE_URL=postgresql://postgres:your_password@db/matcherino
MATCHERINO_TOURNAMENT_ID=your_tournament_id
GITHUB_USERNAME=yourusername  # Replace with the GitHub username of the container owner
```

3. Download the docker-compose file and start the containers:
```bash
curl -O https://raw.githubusercontent.com/yourusername/matcherino-bot/main/docker-compose.ghcr.yml
docker-compose -f docker-compose.ghcr.yml up -d
```

## Database Setup

The bot automatically creates the necessary tables on startup, but you need:

1. A PostgreSQL server running
2. A database created for the bot to use
3. Proper connection details configured in the DATABASE_URL

## Commands

### User Commands
- `/register` - Register for tournaments
- `/check-status` - Check your registration status

### Admin Commands
- `!registered` - List all registered users
- `!export` - Export registered users to CSV
- `!sync-teams` - Manually sync teams with Matcherino

## Deployment Options

### Deploy on Unraid
This repository includes configuration files for deploying on Unraid servers:

- Using Docker with the provided compose files
- GitHub Actions for automated deployment
- GitHub Container Registry integration
- Unraid Docker Templates

See the [Unraid Deployment Guide](UNRAID.md) for detailed instructions.

## Development

### Project Structure
- `bot.py` - Main Discord bot code
- `db.py` - Database interaction and management
- `matcherino_scraper.py` - Integration with Matcherino API
- `sync_teams.py` - Team synchronization logic
- Docker and deployment configuration files

### GitHub Actions Workflow

This project includes a GitHub Actions workflow that automatically:

1. Builds the Docker image when you push changes
2. Publishes the image to GitHub Container Registry
3. Optionally deploys to your Unraid server (when configured)

To enable automatic deployment to Unraid:
1. Generate an SSH key pair
2. Add the public key to your Unraid server
3. Add the private key and other required secrets to your GitHub repository
4. Set the `UNRAID_DEPLOY` variable to `true` in repository variables

For detailed setup instructions, see the [Unraid Deployment Guide](UNRAID.md).

### Contributing
1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a new Pull Request

## License

MIT 