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
from typing import Dict, List, Optional, Tuple, Any
from bs4 import BeautifulSoup
import re
from dotenv import load_dotenv
import time
from datetime import datetime
import pathlib
import argparse

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
MATCHERINO_LOGIN_URL = "https://matcherino.com/api/auth/login"
MATCHERINO_BASE_URL = "https://matcherino.com"
MATCHERINO_TOURNAMENT_PATH = "/t/"  # Append tournament ID to this path

# Get credentials from environment variables (recommended to store in .env file)
MATCHERINO_EMAIL = os.getenv("MATCHERINO_EMAIL")
MATCHERINO_PASSWORD = os.getenv("MATCHERINO_PASSWORD")
DEFAULT_TOURNAMENT_ID = os.getenv("MATCHERINO_TOURNAMENT_ID")

class MatcherinoScraper:
    """
    Class for scraping team information from Matcherino tournament pages.
    
    This scraper can:
    1. Log in to Matcherino (if needed)
    2. Navigate to tournament pages
    3. Extract team information including names and member usernames
    4. Handle errors gracefully and provide robust data extraction
    """
    
    def __init__(self, email: Optional[str] = None, password: Optional[str] = None):
        """
        Initialize the Matcherino scraper with optional login credentials.
        
        Args:
            email (str, optional): Matcherino login email. Defaults to environment variable.
            password (str, optional): Matcherino login password. Defaults to environment variable.
        """
        self.email = email or MATCHERINO_EMAIL
        self.password = password or MATCHERINO_PASSWORD
        self.session = None
        self.logged_in = False
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
    
    async def login(self) -> bool:
        """
        Log in to Matcherino using the provided credentials.
        
        Returns:
            bool: True if login was successful, False otherwise
        """
        if not self.email or not self.password:
            logger.warning("Matcherino login credentials not provided. Some features may not work.")
            return False
        
        if self.logged_in:
            return True
        
        if not self.session:
            await self.create_session()
        
        try:
            # Login data payload
            login_data = {
                "email": self.email,
                "password": self.password
            }
            
            async with self.session.post(MATCHERINO_LOGIN_URL, json=login_data) as response:
                if response.status == 200:
                    response_json = await response.json()
                    if response_json.get("token"):
                        # Set auth token in headers if returned
                        self.headers["Authorization"] = f"Bearer {response_json['token']}"
                        self.session.headers.update(self.headers)
                        self.logged_in = True
                        logger.info("Successfully logged in to Matcherino")
                        return True
                
                logger.error(f"Failed to log in to Matcherino. Status: {response.status}")
                logger.debug(f"Response: {await response.text()}")
                return False
                
        except aiohttp.ClientError as e:
            logger.error(f"Error during Matcherino login: {e}")
            return False
    
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
                elif response.status == 403:
                    # Try logging in if we get a forbidden response
                    if await self.login():
                        # Retry after logging in
                        async with self.session.get(url) as retry_response:
                            if retry_response.status == 200:
                                html_content = await retry_response.text()
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
            # First, ensure we're logged in
            if not self.logged_in:
                login_success = await self.login()
                if not login_success:
                    logger.error("Failed to log in to Matcherino")
                    return []
                    
            # Get the teams page
            teams_page_url = f"{MATCHERINO_BASE_URL}{MATCHERINO_TOURNAMENT_PATH}{tournament_id}/teams"
            teams_data = await self._get_teams(teams_page_url)
            
            return teams_data
            
        except Exception as e:
            logger.error(f"Error fetching teams data: {e}")
            return []
    
    async def get_tournament_participants(self, tournament_id: str) -> List[Dict[str, Any]]:
        """
        Extract individual participant information from tournament.
        Alternative to get_teams_data for tournaments with individual participants.
        
        Args:
            tournament_id (str): The ID of the tournament to fetch participants from
            
        Returns:
            List[Dict[str, Any]]: List of dictionaries containing participant information
        """
        html_content = await self.get_tournament_page(tournament_id)
        
        if not html_content:
            logger.error("No HTML content retrieved, cannot extract participant information")
            return []
        
        try:
            # Parse the HTML content
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Participants data will be stored here
            participants_data = []
            
            # Look for participant information in the page
            participants_container = soup.find('div', class_=re.compile(r'.*participants.*', re.IGNORECASE))
            
            if participants_container:
                participant_elements = participants_container.find_all('div', class_=re.compile(r'.*participant.*', re.IGNORECASE))
                
                for participant_elem in participant_elements:
                    participant_data = {}
                    
                    # Extract participant name
                    name_elem = participant_elem.find('h3') or participant_elem.find('div', class_=re.compile(r'.*name.*', re.IGNORECASE))
                    if name_elem:
                        participant_data['name'] = name_elem.text.strip()
                    else:
                        participant_data['name'] = "Unknown Participant"
                    
                    # Extract other participant info if available
                    username_elem = participant_elem.find('div', class_=re.compile(r'.*username.*', re.IGNORECASE))
                    if username_elem:
                        participant_data['username'] = username_elem.text.strip()
                    
                    participants_data.append(participant_data)
            
            # If we couldn't find participants using the above method, try alternative approach
            if not participants_data:
                script_tags = soup.find_all('script', type='application/json')
                
                for script in script_tags:
                    try:
                        json_data = json.loads(script.string)
                        
                        # Look for participant data in the JSON
                        if isinstance(json_data, dict) and 'participants' in json_data:
                            participants_json = json_data.get('participants')
                            
                            if participants_json and isinstance(participants_json, list):
                                for participant in participants_json:
                                    if isinstance(participant, dict):
                                        participant_data = {
                                            'name': participant.get('name', 'Unknown Participant'),
                                            'username': participant.get('username', ''),
                                            'id': participant.get('id', '')
                                        }
                                        participants_data.append(participant_data)
                                
                                if participants_data:
                                    break  # Stop if we found participant data
                    except (json.JSONDecodeError, AttributeError):
                        continue
            
            return participants_data
            
        except Exception as e:
            logger.error(f"Error parsing tournament participants: {e}")
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
            # Try to log in (optional)
            if MATCHERINO_EMAIL and MATCHERINO_PASSWORD:
                login_success = await scraper.login()
                print(f"Login attempt {'successful' if login_success else 'failed'}")
            
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
                    print("2. Login required to view the tournament")
                    print("3. Changes in the Matcherino website structure")
    
    except Exception as e:
        print(f"Error during scraper test: {e}")


def integrate_with_discord_bot():
    """
    Plan and documentation for integrating with the Discord bot.
    
    This function provides documentation on how to integrate this scraper
    with the existing Discord bot for tracking tournament participants.
    """
    integration_doc = """
    Integration with Discord Bot
    ===========================
    
    To integrate this scraper with the Discord bot, follow these steps:
    
    1. Import the MatcherinoScraper class in bot.py:
       ```python
       from matcherino_scraper import MatcherinoScraper
       ```
    
    2. Add a new command to fetch and display team information:
       ```python
       @bot.tree.command(name="teams", description="Get tournament team information", guild=discord.Object(id=TARGET_GUILD_ID))
       async def teams_slash(interaction: discord.Interaction):
           # Check if the user has permission
           if not interaction.user.guild_permissions.administrator:
               await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
               return
           
           await interaction.response.defer(ephemeral=True)
           
           tournament_id = os.getenv("MATCHERINO_TOURNAMENT_ID")
           if not tournament_id:
               await interaction.followup.send("Tournament ID not configured. Please set the MATCHERINO_TOURNAMENT_ID environment variable.", ephemeral=True)
               return
           
           try:
               async with MatcherinoScraper() as scraper:
                   teams_data = await scraper.get_teams_data(tournament_id)
                   
                   if not teams_data:
                       await interaction.followup.send("No team data found for the tournament.", ephemeral=True)
                       return
                   
                   response = "**Tournament Teams:**\n\n"
                   
                   for i, team in enumerate(teams_data, 1):
                       response += f"{i}. **{team['name']}**\n"
                       if team.get('members'):
                           response += "   **Members:**\n"
                           for member in team['members']:
                               response += f"   - {member}\n"
                       response += "\n"
                       
                       # Handle Discord message length limits
                       if len(response) > 1900:
                           await interaction.followup.send(response, ephemeral=True)
                           response = "**Continued:**\n\n"
                   
                   if response:
                       await interaction.followup.send(response, ephemeral=True)
                   
           except Exception as e:
               logger.error(f"Error in teams command: {e}")
               await interaction.followup.send(f"An error occurred while retrieving team information: {str(e)}", ephemeral=True)
       ```
    
    3. Add a command to match Discord users with Matcherino participants:
       ```python
       @bot.tree.command(name="match-users", description="Match Discord users with Matcherino participants", guild=discord.Object(id=TARGET_GUILD_ID))
       async def match_users_slash(interaction: discord.Interaction):
           # Check if the user has permission
           if not interaction.user.guild_permissions.administrator:
               await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
               return
           
           await interaction.response.defer(ephemeral=True)
           
           tournament_id = os.getenv("MATCHERINO_TOURNAMENT_ID")
           if not tournament_id:
               await interaction.followup.send("Tournament ID not configured. Please set the MATCHERINO_TOURNAMENT_ID environment variable.", ephemeral=True)
               return
           
           try:
               # Get all registered Discord users
               registered_users = await db.get_registered_users()
               
               if not registered_users:
                   await interaction.followup.send("No users are registered in the Discord bot.", ephemeral=True)
                   return
               
               # Get Matcherino participants
               async with MatcherinoScraper() as scraper:
                   teams_data = await scraper.get_teams_data(tournament_id)
                   
                   # Extract all participant names from teams
                   matcherino_participants = []
                   for team in teams_data:
                       if team.get('members'):
                           for member in team['members']:
                               matcherino_participants.append({
                                   'name': member,
                                   'team': team['name']
                               })
                   
                   if not matcherino_participants:
                       # Try getting individual participants
                       participants = await scraper.get_tournament_participants(tournament_id)
                       for participant in participants:
                           matcherino_participants.append({
                               'name': participant.get('name') or participant.get('username'),
                               'team': 'Individual Participant'
                           })
                   
                   if not matcherino_participants:
                       await interaction.followup.send("No participants found in the Matcherino tournament.", ephemeral=True)
                       return
                   
                   # Match Discord users to Matcherino participants
                   # This is a simple matching strategy that can be improved
                   matches = []
                   unmatched_discord = []
                   unmatched_matcherino = matcherino_participants.copy()
                   
                   for user in registered_users:
                       discord_username = user['username']
                       discord_id = user['user_id']
                       matched = False
                       
                       # Try to find a match in Matcherino participants
                       for i, participant in enumerate(unmatched_matcherino):
                           # Simple matching logic - can be improved
                           if (discord_username.lower() in participant['name'].lower() or
                               participant['name'].lower() in discord_username.lower()):
                               matches.append({
                                   'discord_username': discord_username,
                                   'discord_id': discord_id,
                                   'matcherino_name': participant['name'],
                                   'team': participant.get('team', 'Unknown')
                               })
                               unmatched_matcherino.pop(i)
                               matched = True
                               break
                       
                       if not matched:
                           unmatched_discord.append({
                               'discord_username': discord_username,
                               'discord_id': discord_id
                           })
                   
                   # Format response
                   response = "**Discord Users Matched with Matcherino Participants:**\n\n"
                   
                   if matches:
                       for match in matches:
                           response += f"- Discord: {match['discord_username']} (ID: {match['discord_id']})\n"
                           response += f"  Matcherino: {match['matcherino_name']}\n"
                           response += f"  Team: {match['team']}\n\n"
                   else:
                       response += "No matches found.\n\n"
                   
                   response += "**Unmatched Discord Users:**\n\n"
                   if unmatched_discord:
                       for user in unmatched_discord:
                           response += f"- {user['discord_username']} (ID: {user['discord_id']})\n"
                   else:
                       response += "None\n\n"
                   
                   response += "**Unmatched Matcherino Participants:**\n\n"
                   if unmatched_matcherino:
                       for participant in unmatched_matcherino:
                           response += f"- {participant['name']} (Team: {participant.get('team', 'Unknown')})\n"
                   else:
                       response += "None\n\n"
                   
                   # Handle Discord message length limits
                   if len(response) > 1900:
                       await interaction.followup.send(response[:1900] + "...", ephemeral=True)
                       await interaction.followup.send("... " + response[1900:], ephemeral=True)
                   else:
                       await interaction.followup.send(response, ephemeral=True)
                   
           except Exception as e:
               logger.error(f"Error in match-users command: {e}")
               await interaction.followup.send(f"An error occurred while matching users: {str(e)}", ephemeral=True)
    """
    
    print(integration_doc)
    return integration_doc


if __name__ == "__main__":
    """Run the test function when the script is executed directly"""
    parser = argparse.ArgumentParser(description="Matcherino Team Scraper")
    parser.add_argument('--tournament', '-t', type=str, default=DEFAULT_TOURNAMENT_ID,
                        help=f'Tournament ID (default: {DEFAULT_TOURNAMENT_ID})')
    
    args = parser.parse_args()
    
    # Use passed tournament ID or default
    tournament_id = args.tournament
    
    if not tournament_id:
        print("Error: No tournament ID provided and MATCHERINO_TOURNAMENT_ID environment variable not set")
        exit(1)
    
    print(f"Fetching data for tournament ID: {tournament_id}")
    
    # Run the scraper
    async def run_scraper():
        async with MatcherinoScraper() as scraper:
            teams = await scraper.get_teams_data(tournament_id)
            
            print(f"\nFound {len(teams)} teams in tournament {tournament_id}:\n")
            for i, team in enumerate(teams, 1):
                print(f"{i}. {team['name']}")
                if team.get('members'):
                    print(f"   Members ({len(team['members'])}):")
                    for member in team['members']:
                        print(f"   - {member}")
                print()
    
    try:
        asyncio.run(run_scraper())
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
    except Exception as e:
        print(f"Error: {e}") 