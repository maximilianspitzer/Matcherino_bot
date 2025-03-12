"""
Matcherino Team Sync Script

This script fetches team data from Matcherino and updates the local database.
It can be run manually or scheduled to run periodically.
"""

import asyncio
import logging
import os
from dotenv import load_dotenv
from db import Database
from matcherino_scraper import MatcherinoScraper

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Get tournament ID from environment
TOURNAMENT_ID = os.getenv("MATCHERINO_TOURNAMENT_ID")
if not TOURNAMENT_ID:
    logger.critical("MATCHERINO_TOURNAMENT_ID environment variable not set")
    raise ValueError("MATCHERINO_TOURNAMENT_ID environment variable not set")

async def sync_teams():
    """Fetch team data from Matcherino and sync it to the database."""
    logger.info(f"Starting team sync for tournament ID: {TOURNAMENT_ID}")
    
    # Initialize database connection
    db = Database()
    await db.create_pool()
    
    try:
        # Fetch teams from Matcherino
        async with MatcherinoScraper() as scraper:
            teams_data = await scraper.get_teams_data(TOURNAMENT_ID)
            
            if not teams_data:
                logger.warning("No teams found in the tournament. Nothing to sync.")
                return
            
            logger.info(f"Found {len(teams_data)} teams with data to sync")
            
            # Update database with team data
            await db.update_matcherino_teams(teams_data)
            
            logger.info("Team sync completed successfully")
            
            # Display team information
            print(f"\nFetched {len(teams_data)} teams from Matcherino tournament {TOURNAMENT_ID}")
            for i, team in enumerate(teams_data, 1):
                print(f"\n{i}. Team: {team['name']}")
                if team.get('members'):
                    print(f"   Members ({len(team['members'])}):")
                    for member in team['members']:
                        print(f"   - {member}")
            
            # Now fetch from database to verify
            stored_teams = await db.get_matcherino_teams()
            
            print(f"\nStored {len(stored_teams)} teams in database")
            for i, team in enumerate(stored_teams, 1):
                print(f"\n{i}. Team: {team['team_name']}")
                if team.get('members'):
                    print(f"   Members ({len(team['members'])}):")
                    for member in team['members']:
                        discord_user = f" (Discord: {member['discord_username']})" if member['discord_username'] else ""
                        print(f"   - {member['member_name']}{discord_user}")
    
    except Exception as e:
        logger.error(f"Error during team sync: {e}")
        raise
    
    finally:
        # Close database connection
        await db.close()

if __name__ == "__main__":
    print("Matcherino Team Sync")
    print("=" * 50)
    
    try:
        asyncio.run(sync_teams())
        print("\nTeam sync completed!")
    except KeyboardInterrupt:
        print("\nSync interrupted by user")
    except Exception as e:
        logger.critical(f"Sync failed: {e}")
        print(f"\nError: {e}") 