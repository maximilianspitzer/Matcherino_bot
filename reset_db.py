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

async def reset_database():
    """Reset the database by dropping and recreating all tables."""
    try:
        # Create a connection to the database
        logger.info("Connecting to database...")
        conn = await asyncpg.connect(DATABASE_URL)
        
        # Drop the existing tables if they exist
        logger.info("Dropping existing tables...")
        await conn.execute("DROP TABLE IF EXISTS team_members")  # Drop this first due to foreign key
        await conn.execute("DROP TABLE IF EXISTS matcherino_teams")
        await conn.execute("DROP TABLE IF EXISTS registrations")
        
        # Recreate the registrations table
        logger.info("Recreating registrations table...")
        await conn.execute('''
            CREATE TABLE registrations (
                user_id BIGINT PRIMARY KEY,
                username TEXT NOT NULL,
                matcherino_username TEXT,
                registered_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                join_code TEXT
            )
        ''')
        
        # Create the matcherino_teams table
        logger.info("Creating matcherino_teams table...")
        await conn.execute('''
            CREATE TABLE matcherino_teams (
                team_id SERIAL PRIMARY KEY,
                team_name TEXT NOT NULL UNIQUE,
                last_updated TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN NOT NULL DEFAULT TRUE
            )
        ''')
        
        # Create the team_members table
        logger.info("Creating team_members table...")
        await conn.execute('''
            CREATE TABLE team_members (
                id SERIAL PRIMARY KEY,
                team_id INTEGER REFERENCES matcherino_teams(team_id) ON DELETE CASCADE,
                member_name TEXT NOT NULL,
                discord_user_id BIGINT REFERENCES registrations(user_id),
                UNIQUE(team_id, member_name)
            )
        ''')
        
        logger.info("Database reset successful!")
        
        # Close the connection
        await conn.close()
        
    except Exception as e:
        logger.error(f"Error resetting database: {e}")
        raise

async def confirm_reset():
    """Ask for user confirmation before resetting the database."""
    print("\n⚠️  WARNING: This will delete ALL registration and team data! ⚠️\n")
    print("This script will recreate the following tables:")
    print("1. registrations - User registration information")
    print("2. matcherino_teams - Teams from Matcherino tournaments")
    print("3. team_members - Links between team members and teams\n")
    
    response = input("Are you sure you want to reset the database? (yes/no): ").strip().lower()
    
    if response != "yes":
        print("Database reset cancelled.")
        return False
        
    return True

if __name__ == "__main__":
    try:
        if asyncio.run(confirm_reset()):
            asyncio.run(reset_database())
            print("\nDatabase reset complete! All tables have been recreated.")
            print("\nNext steps:")
            print("1. Update your bot.py file to include the team command handlers")
            print("2. Run the sync_teams.py script to pull in tournament data")
            print("3. Have users register with their Matcherino usernames")
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
    except Exception as e:
        logger.critical(f"Unexpected error: {e}") 