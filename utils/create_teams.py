"""
Create teams from the first participants that signed up on Matcherino.
This script will fetch the first X participants needed to create the specified number of teams.
"""

import os
import asyncio
import logging
import random
import aiohttp
from typing import List, Dict, Any, Optional, Tuple
import sys

# Add the parent directory to sys.path to import from parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from matcherino_scraper import MatcherinoScraper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Configuration
DEFAULT_TEAM_COUNT = 128
PLAYERS_PER_TEAM = 3
DELAY_BETWEEN_TEAMS = 1.0  # seconds
DELAY_BETWEEN_MEMBERS = 0.5  # seconds

# Lists of adjectives and brainrot terms (divided by category)
adjectives = [
    "Screaming", "Gooning", "Silent", "Edged", "Rizzed", "Cooking", "Slippery",
    "Bussin'", "Vaped", "Nonchalant", "Digital", "Grilled", "Bizarre", "Dynamic",
    "Fierce", "Mighty", "Radical", "Epic", "Wild", "Electric"
]

# Characters/People
characters = [
    "Skibidi Toilet", "Baby Gronk", "Duke Dennis", "Kai Cenat",
    "IShowSpeed", "Grimace", "Quandale Dingle", "Livvy Dunne",
    "Sigma Male", "Chris Tyson", "Fanum"
]

# Objects/Things
objects_things = [
    "Grimace Shake", "Glizzy", "Gyatt", "Aura", "Fanta",
    "Life Saver Gummies", "Digital Circus", "Imposter",
    "Cap", "L", "Ratio", "Brisket", "Mewing", "Ohio"
]

# Phrases/Concepts
phrases = [
    "Let Him Cook", "On Skibidi", "L + Ratio", "Stop the Cap",
    "Goonmaxxing", "Looksmaxxing", "Biting the Curb", "Only in Ohio",
    "Pray Today", "1 2 Buckle My Shoe"
]

# Combine all brainrot terms into one list
all_terms = characters + objects_things + phrases

def generate_team_name() -> str:
    """Generate a single random team name by pairing an adjective with a brainrot term."""
    return f"{random.choice(adjectives)} {random.choice(all_terms)}"

async def create_team(session: aiohttp.ClientSession, auth_token: str, bounty_id: str = "146289") -> Tuple[Optional[int], Optional[str]]:
    """
    Create a team on Matcherino using the API.
    
    Args:
        session: aiohttp ClientSession for making requests
        auth_token: Bearer token for authentication
        bounty_id: The bounty/tournament ID (default: 146289)
        
    Returns:
        Tuple of (team_id, team_name) if successful, (None, None) if failed
    """
    team_name = generate_team_name()
    url = "https://api.matcherino.com/__api/teams/bounties/create"
    headers = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "text/plain;charset=UTF-8",
        "Origin": "https://api.matcherino.com",
        "Referer": "https://api.matcherino.com/__api/session/corsPreflightBypass",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        "x-mno-auth": f"Bearer {auth_token}"
    }
    
    # Convert payload to JSON string since we're using text/plain content type
    payload = f'{{"temporary":true,"name":"{team_name}","bountyId":{bounty_id}}}'
    
    try:
        async with session.post(url, data=payload, headers=headers) as response:
            if response.status != 200:
                response_text = await response.text()
                logger.error(f"Failed to create team. Status: {response.status}, Response: {response_text}")
                return None, None
            
            data = await response.json()
            team_id = data["body"]["id"]
            logger.info(f"Created team '{team_name}' with ID: {team_id}")
            return team_id, team_name
            
    except Exception as e:
        logger.error(f"Error creating team: {e}")
        return None, None

async def add_member_to_team(session: aiohttp.ClientSession, auth_token: str, team_id: int, user_id: int) -> bool:
    """
    Add a member to a team using the Matcherino API.
    
    Args:
        session: aiohttp ClientSession for making requests
        auth_token: Bearer token for authentication
        team_id: The ID of the team to add the member to
        user_id: The user ID of the member to add
        
    Returns:
        bool: True if successful, False if failed
    """
    url = "https://api.matcherino.com/__api/teams/bounties/members/upsert"
    headers = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "text/plain;charset=UTF-8",
        "Origin": "https://api.matcherino.com",
        "Referer": "https://api.matcherino.com/__api/session/corsPreflightBypass",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        "x-mno-auth": f"Bearer {auth_token}"
    }
    
    # Convert payload to JSON string since we're using text/plain content type
    payload = f'{{"bountyTeamId":{team_id},"members":[{{"userId":{user_id}}}]}}'
    
    try:
        async with session.post(url, data=payload, headers=headers) as response:
            if response.status != 200:
                response_text = await response.text()
                logger.error(f"Failed to add member {user_id} to team {team_id}. Status: {response.status}, Response: {response_text}")
                return False
            
            logger.info(f"Successfully added member {user_id} to team {team_id}")
            return True
            
    except Exception as e:
        logger.error(f"Error adding member to team: {e}")
        return False

async def create_team_with_members(session: aiohttp.ClientSession, auth_token: str, members: List[Dict[str, Any]], bounty_id: str = "146289") -> bool:
    """
    Create a team and add its members.
    
    Args:
        session: aiohttp ClientSession for making requests
        auth_token: Bearer token for authentication
        members: List of participant data to add as members
        bounty_id: The bounty/tournament ID (default: 146289)
        
    Returns:
        bool: True if successful, False if failed
    """
    # Create the team first
    team_result = await create_team(session, auth_token, bounty_id)
    if not team_result:
        return False
    
    team_id, team_name = team_result
    
    # Add each member to the team with a delay between requests
    success = True
    for member in members:
        user_id = member.get('user_id')
        if not user_id:
            logger.error(f"Missing user_id for member in team {team_name}")
            success = False
            continue
        
        # Add small delay before adding member
        await asyncio.sleep(DELAY_BETWEEN_MEMBERS)  # 500ms delay between adding members
            
        if not await add_member_to_team(session, auth_token, team_id, user_id):
            success = False
    
    return success

async def create_all_teams_with_members(auth_token: str, participants: List[Dict[str, Any]], team_count: int = DEFAULT_TEAM_COUNT) -> bool:
    """
    Create the specified number of teams and add members to each.
    
    Args:
        auth_token: Bearer token for authentication
        participants: List of shuffled participants to add to teams
        team_count: Number of teams to create
        
    Returns:
        bool: True if all operations were successful
    """
    async with aiohttp.ClientSession() as session:
        all_success = True
        
        # Process participants in groups of 3 for each team
        for i in range(team_count):
            team_members = participants[i*3:(i+1)*3]
            if len(team_members) != 3:
                logger.error(f"Not enough members for team {i+1}, needed 3 but got {len(team_members)}")
                all_success = False
                break
                
            logger.info(f"\nCreating team {i+1}/{team_count}")
            if not await create_team_with_members(session, auth_token, team_members):
                logger.error(f"Failed to create team {i+1} or add its members")
                all_success = False
            
            # Add delay between creating teams
            await asyncio.sleep(DELAY_BETWEEN_TEAMS)  # 1 second delay between teams
        
        return all_success

async def get_recent_participants(team_count: int = DEFAULT_TEAM_COUNT, players_per_team: int = PLAYERS_PER_TEAM) -> List[Dict[str, Any]]:
    """
    Get the first participants that signed up from Matcherino API (first come, first serve).
    The API returns most recent signups first, so we take from the end to get earliest signups.
    
    Args:
        team_count (int): Number of teams to create (default: DEFAULT_TEAM_COUNT)
        players_per_team (int): Number of players per team (default: PLAYERS_PER_TEAM)
        
    Returns:
        List[Dict[str, Any]]: List of participant data for the first players who signed up
    """
    total_players_needed = team_count * players_per_team
    logger.info(f"Fetching first {total_players_needed} players for {team_count} teams")
    
    try:
        async with MatcherinoScraper() as scraper:
            # Use the existing get_tournament_participants method
            # It already handles pagination and returns all participants
            all_participants = await scraper.get_tournament_participants("146289")
            
            if not all_participants:
                logger.error("No participants found")
                return []
            
            logger.info(f"Found {len(all_participants)} total participants")
            
            # Take the last entries (earliest signups) since API returns newest first
            first_participants = all_participants[-total_players_needed:][::-1]  # Reverse to get chronological order
            logger.info(f"Selected {len(first_participants)} earliest signups from the end of the list")
            
            # Randomly shuffle the participants
            random.shuffle(first_participants)
            logger.info("Randomly shuffled all participants")
            
            return first_participants
            
    except Exception as e:
        logger.error(f"Error fetching participants: {e}", exc_info=True)
        return []

async def main():
    """
    Main function to create teams and add members.
    """
    auth_token = os.getenv("MATCHERINO_AUTH_TOKEN")
    if not auth_token:
        logger.error("MATCHERINO_AUTH_TOKEN environment variable not set")
        return

    # Get number of teams to create, defaulting to DEFAULT_TEAM_COUNT if not specified
    try:
        team_count = int(input(f"How many teams would you like to create? (default: {DEFAULT_TEAM_COUNT}): ").strip() or DEFAULT_TEAM_COUNT)
        if team_count <= 0:
            logger.error("Number of teams must be positive")
            return
    except ValueError:
        logger.error("Invalid number provided")
        return

    logger.info(f"Creating {team_count} teams with {PLAYERS_PER_TEAM} players each...")
    
    # Get and shuffle participants
    participants = await get_recent_participants(team_count=team_count)
    if not participants:
        logger.error("Failed to get participants")
        return
    
    # Create teams and add members
    success = await create_all_teams_with_members(auth_token, participants, team_count=team_count)
    if success:
        logger.info(f"\nSuccessfully created {team_count} teams and added members")
    else:
        logger.error("\nSome operations failed while creating teams or adding members")

if __name__ == "__main__":
    asyncio.run(main())