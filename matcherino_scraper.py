"""
Matcherino Scraper - Tournament Team Information

This module provides functionality to retrieve team information from Matcherino tournaments.
It extracts team names, member usernames, and other relevant information to integrate
with the Discord bot registration system.
"""

import os
import json
import logging
import asyncio
import aiohttp
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Constants
MATCHERINO_BASE_URL = "https://matcherino.com"
MATCHERINO_TOURNAMENT_PATH = "/t/"  # Append tournament ID to this path

# Get tournament ID from environment variables
DEFAULT_TOURNAMENT_ID = os.getenv("MATCHERINO_TOURNAMENT_ID")

class MatcherinoScraper:
    """
    Class for retrieving team information from Matcherino tournaments using the API.
    
    This scraper can:
    1. Retrieve team information including names and member usernames
    2. Get tournament participant data
    3. Handle errors gracefully and provide robust data extraction
    """
    
    def __init__(self):
        """
        Initialize the Matcherino scraper.
        """
        self.session = None
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.create_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close_session()
    
    async def create_session(self):
        """Create an aiohttp session for making requests"""
        if self.session is None:
            self.session = aiohttp.ClientSession(headers=self.headers)
        return self.session
    
    async def close_session(self):
        """Close the aiohttp session if it exists"""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def get_teams_data(self, tournament_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get teams data for a specific tournament using the Matcherino API.
        
        Args:
            tournament_id (str, optional): The tournament ID. Defaults to environment variable.
            
        Returns:
            List[Dict[str, Any]]: A list of teams, each containing name and members
        """
        if not tournament_id:
            tournament_id = DEFAULT_TOURNAMENT_ID
            if not tournament_id:
                logger.error("No tournament ID provided and DEFAULT_TOURNAMENT_ID not set")
                return []
        
        if not self.session:
            await self.create_session()
        
        logger.info(f"Fetching teams data for tournament: {tournament_id}")
        
        try:
            # API endpoint for getting bounty data
            api_url = "https://api.matcherino.com/__api/bounties/findById"
            
            # Parameters for the request
            params = {
                "id": 0,  # This will be ignored when shortlink is provided
                "shortlink": tournament_id
            }
            
            # API-specific headers
            api_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Origin": "https://matcherino.com",
                "Referer": f"https://matcherino.com/t/{tournament_id}",
            }
            
            logger.info(f"Requesting team data from API: {api_url} for tournament: {tournament_id}")
            
            # Make the API request
            async with self.session.get(api_url, params=params, headers=api_headers) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch team data from API. Status: {response.status}")
                    return []
                
                # Parse the JSON response
                data = await response.json()
                
                # Check if the response contains team data
                if 'body' not in data or 'teams' not in data['body']:
                    logger.error("API response doesn't contain team data")
                    return []
                
                # Extract teams data
                teams_raw = data['body']['teams']
                logger.info(f"Successfully retrieved {len(teams_raw)} teams from API")
                
                # Format the team data to match the expected structure
                teams_data = []
                for team in teams_raw:
                    # Get team name, with fallback
                    team_name = team.get('name', 'Unknown Team')
                    
                    # Extract team members - checking both 'members' and possibly nested 'team.members'
                    members = []
                    
                    # Check for members directly in the team object
                    if 'members' in team and isinstance(team['members'], list):
                        for member in team['members']:
                            if 'displayName' in member:
                                display_name = member['displayName'].strip()
                                members.append({
                                    'name': display_name,
                                    'user_id': member.get('userId', ''),
                                    'auth_id': member.get('authId', ''),
                                    'auth_provider': member.get('authProvider', ''),
                                    'is_captain': member.get('captain', False),
                                    'game_username': member.get('participantInfo', {}).get('gameUsername', '')
                                })
                    
                    # If no members found and there's a nested team structure, check there
                    if not members and 'team' in team and isinstance(team['team'], dict) and 'members' in team['team']:
                        for member in team['team']['members']:
                            if 'displayName' in member:
                                display_name = member['displayName'].strip()
                                members.append({
                                    'name': display_name,
                                    'user_id': member.get('userId', ''),
                                    'auth_id': member.get('authId', ''),
                                    'auth_provider': member.get('authProvider', ''),
                                    'is_captain': member.get('captain', False),
                                    'game_username': ''  # No game username in this structure
                                })
                    
                    # Format for compatibility with existing code
                    member_names = [member['name'] for member in members]
                    
                    teams_data.append({
                        'name': team_name,
                        'members': member_names,
                        'members_data': members,  # Full member data
                        'team_id': team.get('id') or (team.get('team', {}) or {}).get('id', None),
                        'bounty_team_id': team.get('bountyTeamId', None),
                        'created_at': team.get('createdAt', None),
                        'raw_data': team  # Include the raw data for debugging/future use
                    })
                
                logger.info(f"Successfully processed {len(teams_data)} teams with {sum(len(t['members']) for t in teams_data)} total members")
                return teams_data
                
        except Exception as e:
            logger.error(f"Error fetching teams data from API: {e}", exc_info=True)
            return []
    
    async def get_tournament_participants(self, tournament_id: str) -> List[Dict[str, Any]]:
        """
        Extract individual participant information from tournament using the Matcherino API.
        
        Args:
            tournament_id (str): The ID of the tournament to fetch participants from
            
        Returns:
            List[Dict[str, Any]]: List of dictionaries containing participant information
        """
        if not self.session:
            await self.create_session()
            
        try:
            # Use the specified bountyId (146289) directly
            bounty_id = "146289"  # Hardcoded bountyId as specified
            
            logger.info(f"Using hard-coded bountyId: {bounty_id} for tournament {tournament_id}")
            participants_data = []
            current_page = 0
            total_pages = None
            
            # Define API-specific headers
            api_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Origin": "https://matcherino.com",
                "Referer": f"https://matcherino.com/t/{tournament_id}",
            }

            # Loop through all pages
            while total_pages is None or current_page < total_pages:
                # Use the direct API endpoint to get participants with the specified bountyId
                api_url = f"https://api.matcherino.com/__api/bounties/participants?bountyId={bounty_id}&page={current_page}&pageSize=500"
                logger.info(f"Fetching participants from API (page {current_page+1}): {api_url}")
                
                async with self.session.get(api_url, headers=api_headers) as response:
                    if response.status != 200:
                        logger.error(f"Failed to fetch participants from API. Status: {response.status}")
                        break
                    
                    data = await response.json()
                    logger.info(f"Successfully fetched participant data from API page {current_page+1}")
                    
                    # Update total pages if needed
                    if total_pages is None and "body" in data and "pageCount" in data["body"]:
                        total_pages = data["body"]["pageCount"]
                        logger.info(f"Total pages: {total_pages}")
                    
                    # Extract participants from the API response
                    if "body" in data and "contents" in data["body"]:
                        contents = data["body"]["contents"]
                        logger.info(f"Found {len(contents)} potential participants in API response (page {current_page+1})")
                        
                        # Process each participant
                        for participant in contents:
                            # Skip entries without displayName
                            if "displayName" not in participant:
                                continue
                                
                            display_name = participant.get("displayName", "").strip()
                            
                            # Skip empty names or obvious non-player entries
                            if not display_name or display_name.lower() in ['do not make a team', 'dont make a team', 'looking for team']:
                                continue
                                
                            # Create participant entry
                            participant_data = {
                                'name': display_name,
                                'user_id': participant.get("userId", ""),
                                'auth_id': participant.get("authId", ""),
                                'auth_provider': participant.get("authProvider", ""),
                                'game_username': participant.get("gameUsername", "")
                            }
                            
                            participants_data.append(participant_data)
                
                # Move to the next page
                current_page += 1
                
            logger.info(f"Total participants found across all pages: {len(participants_data)}")
            return participants_data
        except Exception as e:
            logger.error(f"Error getting participants from API: {e}", exc_info=True)
            return []


async def test_scraper(tournament_id: Optional[str] = None):
    """
    Test function to run the scraper and print the extracted team data.
    
    Args:
        tournament_id (str, optional): The ID of the tournament to scrape.
                                      Defaults to the value from environment variables.
    """
    tournament_id = tournament_id or DEFAULT_TOURNAMENT_ID
    
    if not tournament_id:
        print("Error: No tournament ID provided. Please specify a tournament ID.")
        return
    
    print(f"Testing Matcherino scraper for tournament ID: {tournament_id}")
    
    # Create scraper instance using context manager
    try:
        async with MatcherinoScraper() as scraper:
            # Get teams data
            print("\nFetching teams data...")
            teams_data = await scraper.get_teams_data(tournament_id)
            
            if teams_data:
                print(f"\nFound {len(teams_data)} teams:")
                for i, team in enumerate(teams_data, 1):
                    print(f"\n{i}. Team: {team['name']}")
                    if team.get('members'):
                        print(f"   Members ({len(team['members'])}):")
                        for member in team['members']:
                            print(f"   - {member}")
            else:
                print("\nNo team data found. Trying to get individual participants...")
                participants = await scraper.get_tournament_participants(tournament_id)
                
                if participants:
                    print(f"\nFound {len(participants)} participants:")
                    for i, participant in enumerate(participants, 1):
                        print(f"\n{i}. Participant: {participant['name']}")
                        if 'username' in participant:
                            print(f"   Username: {participant['username']}")
                else:
                    print("\nNo team data or individual participants found.")
                    print("This could be due to:")
                    print("1. Invalid tournament ID")
                    print("2. Changes in the Matcherino website structure")
    
    except Exception as e:
        print(f"Error during scraper test: {e}")