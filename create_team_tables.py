import asyncio
import asyncpg
import logging
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    logger.critical("DATABASE_URL environment variable not set")
    raise ValueError("DATABASE_URL environment variable not set")

async def create_team_tables():
    """Create the matcherino_teams and team_members tables if they don't exist."""
    try:
        # Create a connection to the database
        logger.info("Connecting to database...")
        conn = await asyncpg.connect(DATABASE_URL)
        
        # Create the matcherino_teams table
        logger.info("Creating matcherino_teams table...")
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS matcherino_teams (
                team_id SERIAL PRIMARY KEY,
                team_name TEXT NOT NULL UNIQUE,
                last_updated TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN NOT NULL DEFAULT TRUE
            )
        ''')
        
        # Create the team_members table
        logger.info("Creating team_members table...")
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS team_members (
                id SERIAL PRIMARY KEY,
                team_id INTEGER REFERENCES matcherino_teams(team_id) ON DELETE CASCADE,
                member_name TEXT NOT NULL,
                discord_user_id BIGINT REFERENCES registrations(user_id),
                UNIQUE(team_id, member_name)
            )
        ''')
        
        logger.info("Team tables created successfully!")
        
        # Close the connection
        await conn.close()
        
    except Exception as e:
        logger.error(f"Error creating team tables: {e}")
        raise

async def confirm_creation():
    """Ask for user confirmation before creating the tables."""
    print("\nThis will create two new tables in your database:")
    print("1. matcherino_teams - For storing team information")
    print("2. team_members - For tracking team membership\n")
    response = input("Do you want to proceed? (yes/no): ").strip().lower()
    
    if response != "yes":
        print("Table creation cancelled.")
        return False
        
    return True

if __name__ == "__main__":
    try:
        if asyncio.run(confirm_creation()):
            asyncio.run(create_team_tables())
            print("\nTeam tables created successfully! 🎉")
            print("\nNext steps:")
            print("1. Modify your registration command to collect Matcherino usernames")
            print("2. Implement the team synchronization logic")
            print("3. Create admin commands for team management")
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
    except Exception as e:
        logger.critical(f"Unexpected error: {e}") 