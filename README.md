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

- Using Docker with the provided `docker-compose.yml`
- GitHub Actions for automated deployment
- Docker Hub integration
- Unraid Docker Templates

See the [Unraid Deployment Guide](UNRAID.md) for detailed instructions.

## Development

### Project Structure
- `bot.py` - Main Discord bot code
- `db.py` - Database interaction and management
- `matcherino_scraper.py` - Integration with Matcherino API
- `sync_teams.py` - Team synchronization logic
- Docker and deployment configuration files

### Contributing
1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a new Pull Request

## License

MIT 