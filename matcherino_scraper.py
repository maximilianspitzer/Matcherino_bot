"""
Matcherino Scraper - Tournament Team Information

This module provides functionality to scrape team information from Matcherino tournament pages.
It extracts team names, member usernames, and other relevant information to integrate
with the Discord bot registration system.
"""

import os
import json
import logging
import asyncio
import aiohttp
from typing import Dict, List, Optional, Any
from bs4 import BeautifulSoup
import re
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
    Class for scraping team information from Matcherino tournament pages.
    
    This scraper can:
    1. Navigate to tournament pages
    2. Extract team information including names and member usernames
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
    
    async def get_tournament_page(self, tournament_id: str) -> Optional[str]:
        """
        Get the HTML content of a tournament page.
        
        Args:
            tournament_id (str): The ID of the tournament to fetch
            
        Returns:
            Optional[str]: HTML content of the tournament page if successful, None otherwise
        """
        if not self.session:
            await self.create_session()
        
        url = f"{MATCHERINO_BASE_URL}{MATCHERINO_TOURNAMENT_PATH}{tournament_id}"
        logger.info(f"Fetching tournament page: {url}")
        
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    html_content = await response.text()
                    logger.info(f"Successfully retrieved tournament page: {url}")
                    return html_content
                
                logger.error(f"Failed to fetch tournament page. Status: {response.status}")
                return None
                
        except aiohttp.ClientError as e:
            logger.error(f"Error fetching tournament page: {e}")
            return None
    
    async def _get_teams(self, teams_page_url: str) -> List[Dict[str, Any]]:
        """
        Extract team information from the teams page URL.
        
        Args:
            teams_page_url (str): URL of the teams page
            
        Returns:
            List[Dict[str, Any]]: List of dictionaries containing team information
        """
        try:
            # Get the HTML content
            async with self.session.get(teams_page_url) as response:
                if response.status != 200:
                    logger.error(f"Failed to get teams page. Status: {response.status}")
                    return []
                
                html_content = await response.text()
            
            # Parse the HTML content
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Teams data will be stored here
            teams_data = []
            
            # First, try to find the participant data in script tags
            logger.info("Looking for participant data in script tags...")
            scripts = soup.find_all('script')
            
            # This will hold all participants found in script tags
            participants_from_json = []
            
            for script in scripts:
                if script.string and ('participant' in script.string.lower() or 'player' in script.string.lower() or 'team' in script.string.lower()):
                    # Try to extract full participant data using regex
                    try:
                        # Look for complete participant JSON objects
                        participant_data_pattern = r'\{"id":\d+,"bountyId":\d+,"name":"([^"]+)"[^}]*"team":\{"id":\d+,"name":"([^"]+)"'
                        participant_matches = re.findall(participant_data_pattern, script.string)
                        
                        if participant_matches:
                            logger.info(f"Found {len(participant_matches)} participant-team pairs in script")
                            for participant_name, team_name in participant_matches:
                                participants_from_json.append({
                                    'name': participant_name,
                                    'team': team_name
                                })
                        else:
                            # If we couldn't find paired data, look for individual participant names
                            participant_pattern = r'\{"id":\d+,"bountyId":\d+,"name":"([^"]+)"'
                            participant_matches = re.findall(participant_pattern, script.string)
                            
                            if participant_matches:
                                logger.info(f"Found {len(participant_matches)} participants in script")
                                for name in participant_matches:
                                    participants_from_json.append({
                                        'name': name,
                                        'team': 'Individual Participant'  # Default team name
                                    })
                            
                            # Separately look for team information
                            team_pattern = r'"team":\{"id":\d+,"name":"([^"]+)"'
                            team_matches = re.findall(team_pattern, script.string)
                            if team_matches:
                                logger.info(f"Found {len(team_matches)} team references in script")
                                # Update the team names for participants if possible
                                for i, team_name in enumerate(team_matches):
                                    if i < len(participants_from_json):
                                        participants_from_json[i]['team'] = team_name
                    except Exception as e:
                        logger.error(f"Error parsing participant data: {e}")
            
            # If we found participants via JSON, group them by team
            if participants_from_json:
                # Group participants by team
                teams_by_name = {}
                for participant in participants_from_json:
                    team_name = participant.get('team', 'Individual Participant')
                    if team_name not in teams_by_name:
                        teams_by_name[team_name] = {
                            'name': team_name,
                            'members': []
                        }
                    teams_by_name[team_name]['members'].append(participant['name'])
                
                # Convert to list
                teams_data = list(teams_by_name.values())
                logger.info(f"Successfully extracted {len(teams_data)} teams with {len(participants_from_json)} participants total")
                return teams_data
            
            # If we didn't find data in scripts, try the HTML approach
            logger.info("No participants found in scripts, trying HTML elements...")
            
            # Look for the specific team section header with "Qualified" text
            team_section_header = soup.find('div', class_='team-section-header')
            
            if team_section_header and 'Qualified' in team_section_header.text:
                logger.info(f"Found team section header: {team_section_header.text.strip()}")
                
                # Get the parent container or next sibling that contains the teams
                team_container = team_section_header.parent
                
                # Find all team/participant elements in this container
                participant_elements = team_container.find_all('div', class_=lambda c: c and ('team-' in c or 'participant-' in c or 'player-' in c))
                
                if not participant_elements:
                    # If we can't find with specific classes, try to find all child divs
                    participant_elements = team_container.find_all('div', recursive=False)
                
                logger.info(f"Found {len(participant_elements)} potential participant elements")
                
                # Process each participant element
                for elem in participant_elements:
                    # Try to extract the participant name
                    name_elem = elem.find(['h3', 'h4', 'div', 'span'], class_=lambda c: c and ('name' in c or 'title' in c))
                    
                    if name_elem:
                        participant_name = name_elem.text.strip()
                        logger.info(f"Found participant: {participant_name}")
                        
                        # For individual participants in a tournament without teams
                        teams_data.append({
                            'name': 'Individual Participants',
                            'members': [participant_name]
                        })
            
            return teams_data
            
        except Exception as e:
            logger.error(f"Error parsing tournament page: {e}")
            return []
    
    async def get_teams_data(self, tournament_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get teams data for a specific tournament.
        
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
            # Get the teams page
            teams_page_url = f"{MATCHERINO_BASE_URL}{MATCHERINO_TOURNAMENT_PATH}{tournament_id}/teams"
            teams_data = await self._get_teams(teams_page_url)
            
            return teams_data
            
        except Exception as e:
            logger.error(f"Error fetching teams data: {e}")
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
    
    async def get_bounty_id(self, tournament_id: str) -> Optional[str]:
        """
        Extract the bountyId from the tournament page.
        
        Args:
            tournament_id (str): The tournament ID from the URL
            
        Returns:
            Optional[str]: The extracted bountyId or None if not found
        """
        if not self.session:
            await self.create_session()
        
        url = f"{MATCHERINO_BASE_URL}{MATCHERINO_TOURNAMENT_PATH}{tournament_id}"
        logger.info(f"Fetching tournament page to extract bountyId: {url}")
        
        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch tournament page. Status: {response.status}")
                    # Fallback to using tournament_id as bounty_id
                    logger.info(f"Falling back to using tournament ID as bountyId: {tournament_id}")
                    return tournament_id
                
                html_content = await response.text()
                
                # For debugging, log a small sample of the HTML content
                content_sample = html_content[:200] + "..." if len(html_content) > 200 else html_content
                logger.debug(f"HTML content sample: {content_sample}")
                
                # Search for bountyId in script tags using regex patterns
                # Pattern 1: Look for bountyId in JSON data
                pattern1 = r'"bountyId":\s*(\d+)'
                match = re.search(pattern1, html_content)
                if match:
                    bounty_id = match.group(1)
                    logger.info(f"Successfully extracted bountyId: {bounty_id}")
                    return bounty_id
                
                # Pattern 2: Look for bounty ID in API calls or object definitions
                pattern2 = r'bounty["\']?\s*:\s*["\']?(\d+)'
                match = re.search(pattern2, html_content, re.IGNORECASE)
                if match:
                    bounty_id = match.group(1)
                    logger.info(f"Successfully extracted bountyId (pattern 2): {bounty_id}")
                    return bounty_id
                
                # Pattern 3: Look for ID in URL parameters in script
                pattern3 = r'bountyId=(\d+)'
                match = re.search(pattern3, html_content)
                if match:
                    bounty_id = match.group(1)
                    logger.info(f"Successfully extracted bountyId (pattern 3): {bounty_id}")
                    return bounty_id
                
                # Pattern 4: Look for tiers with bounty ID
                pattern4 = r'tiers":\s*\[\s*{\s*"bountyId":\s*(\d+)'
                match = re.search(pattern4, html_content)
                if match:
                    bounty_id = match.group(1)
                    logger.info(f"Successfully extracted bountyId (pattern 4): {bounty_id}")
                    return bounty_id
                    
                # Pattern 5: Look for bounty ID in data attributes
                pattern5 = r'data-bounty-id=["\']?(\d+)'
                match = re.search(pattern5, html_content, re.IGNORECASE)
                if match:
                    bounty_id = match.group(1)
                    logger.info(f"Successfully extracted bountyId (pattern 5): {bounty_id}")
                    return bounty_id
                
                # If we get here, we couldn't find the bountyId in the HTML
                logger.warning("Could not extract bountyId from tournament page HTML")
                
                # As a last resort, try to use the tournament ID itself as fallback
                logger.info(f"Falling back to using tournament ID as bountyId: {tournament_id}")
                return tournament_id
                
        except Exception as e:
            logger.error(f"Error extracting bountyId from tournament page: {e}")
            # Fallback to tournament ID if any error occurs
            logger.info(f"Error occurred, falling back to using tournament ID as bountyId: {tournament_id}")
            return tournament_id


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