import asyncio
import asyncpg
import logging
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Join code for tournament - can be overridden by bot.py
TOURNAMENT_JOIN_CODE = "Vladilena Milize"

class Database:
    """
    Database utility class for handling PostgreSQL operations.
    Uses asyncpg for asynchronous database operations.
    """
    def __init__(self, join_code=None):
        self.pool = None
        self.database_url = os.getenv("DATABASE_URL")
        if not self.database_url:
            logger.critical("DATABASE_URL environment variable not set")
            raise ValueError("DATABASE_URL environment variable not set")
            
        # Use provided join code or fallback to default
        self.join_code = join_code or TOURNAMENT_JOIN_CODE

    async def create_pool(self):
        """Create a connection pool to the PostgreSQL database."""
        try:
            self.pool = await asyncpg.create_pool(self.database_url, min_size=1, max_size=10)
            logger.info("Connected to PostgreSQL database")
        except Exception as e:
            logger.critical(f"Failed to create database connection pool: {e}")
            raise

    async def setup_tables(self):
        """Create necessary tables if they don't exist."""
        if not self.pool:
            await self.create_pool()
        
        try:
            async with self.pool.acquire() as conn:
                # Create the registrations table if it doesn't exist
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS registrations (
                        user_id BIGINT PRIMARY KEY,
                        username TEXT NOT NULL,
                        registered_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        join_code TEXT,
                        matcherino_username TEXT,
                        banned BOOLEAN NOT NULL DEFAULT FALSE
                    )
                ''')
                
                # Add join_code column if it doesn't exist (for backwards compatibility)
                try:
                    await conn.execute('''
                        ALTER TABLE registrations 
                        ADD COLUMN IF NOT EXISTS join_code TEXT
                    ''')
                except Exception as e:
                    logger.error(f"Error adding join_code column: {e}")
                
                # Add matcherino_username column if it doesn't exist (for backwards compatibility)
                try:
                    await conn.execute('''
                        ALTER TABLE registrations 
                        ADD COLUMN IF NOT EXISTS matcherino_username TEXT
                    ''')
                except Exception as e:
                    logger.error(f"Error adding matcherino_username column: {e}")
                
                # Add banned column if it doesn't exist (for backwards compatibility)
                try:
                    await conn.execute('''
                        ALTER TABLE registrations 
                        ADD COLUMN IF NOT EXISTS banned BOOLEAN DEFAULT FALSE
                    ''')
                except Exception as e:
                    logger.error(f"Error adding banned column: {e}")
                
                # Create the matcherino_teams table if it doesn't exist
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS matcherino_teams (
                        team_id SERIAL PRIMARY KEY,
                        team_name TEXT NOT NULL UNIQUE,
                        last_updated TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        is_active BOOLEAN NOT NULL DEFAULT TRUE
                    )
                ''')
                
                # Create the team_members table if it doesn't exist
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS team_members (
                        id SERIAL PRIMARY KEY,
                        team_id INTEGER REFERENCES matcherino_teams(team_id) ON DELETE CASCADE,
                        member_name TEXT NOT NULL,
                        discord_user_id BIGINT REFERENCES registrations(user_id),
                        UNIQUE(team_id, member_name)
                    )
                ''')
                
                logger.info("Database tables initialized")
        except Exception as e:
            logger.error(f"Error setting up database tables: {e}")
            raise

    async def register_user(self, user_id: int, username: str, matcherino_username: str = None) -> tuple:
        """
        Register a user in the database with the fixed join code.
        
        Args:
            user_id: The Discord user ID
            username: The Discord username
            matcherino_username: Optional Matcherino username
            
        Returns:
            tuple: (success, join_code) where success is True if registration was successful
                  and join_code is the fixed code for Matcherino registration
        """
        # Fixed join code for all users comes from instance variable
        
        try:
            async with self.pool.acquire() as conn:
                # Check if user is already registered
                existing = await conn.fetchrow(
                    "SELECT * FROM registrations WHERE user_id = $1", user_id
                )
                
                if existing:
                    # User already registered
                    if matcherino_username and not existing['matcherino_username']:
                        # Update the Matcherino username if it wasn't set before
                        await conn.execute(
                            "UPDATE registrations SET matcherino_username = $1 WHERE user_id = $2",
                            matcherino_username, user_id
                        )
                        logger.info(f"Updated Matcherino username for user {username} ({user_id})")
                    
                    return (False, self.join_code)
                
                # Register the user with the fixed join code
                await conn.execute(
                    "INSERT INTO registrations (user_id, username, registered_at, join_code, matcherino_username) VALUES ($1, $2, $3, $4, $5)",
                    user_id, username, datetime.utcnow(), self.join_code, matcherino_username
                )
                return (True, self.join_code)
        except Exception as e:
            logger.error(f"Error registering user {username} ({user_id}): {e}")
            raise

    async def get_registered_users(self):
        """
        Get all registered users from the database.
        
        Returns:
            list: A list of records containing user information
        """
        try:
            async with self.pool.acquire() as conn:
                records = await conn.fetch("SELECT * FROM registrations ORDER BY registered_at")
                return records
        except Exception as e:
            logger.error(f"Error retrieving registered users: {e}")
            raise

    async def is_user_registered(self, user_id: int) -> bool:
        """
        Check if a user is already registered.
        
        Args:
            user_id: The Discord user ID
            
        Returns:
            bool: True if user is registered, False otherwise
        """
        try:
            async with self.pool.acquire() as conn:
                record = await conn.fetchrow(
                    "SELECT * FROM registrations WHERE user_id = $1", user_id
                )
                return bool(record)
        except Exception as e:
            logger.error(f"Error checking if user {user_id} is registered: {e}")
            raise

    async def get_user_join_code(self, user_id: int) -> str:
        """
        Get a user's join code.
        
        Args:
            user_id: The Discord user ID
            
        Returns:
            str: The fixed join code or None if not registered
        """
        # Fixed join code for all users comes from instance variable
        
        try:
            async with self.pool.acquire() as conn:
                # Check if user is registered
                exists = await conn.fetchval(
                    "SELECT COUNT(*) FROM registrations WHERE user_id = $1", user_id
                )
                
                if exists:
                    return self.join_code
                return None
        except Exception as e:
            logger.error(f"Error retrieving join code for user {user_id}: {e}")
            raise

    async def close(self):
        """Close the database connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("Database connection pool closed")

    # Team management methods
    async def update_matcherino_teams(self, teams_data):
        """
        Update the database with the latest teams data from Matcherino.
        
        Args:
            teams_data: List of dictionaries containing team information
                        Each team should have 'name' and 'members' keys
        """
        if not self.pool:
            await self.create_pool()
            
        try:
            async with self.pool.acquire() as conn:
                # Start a transaction
                async with conn.transaction():
                    # First, mark all teams as potentially inactive
                    await conn.execute(
                        "UPDATE matcherino_teams SET is_active = FALSE"
                    )
                    
                    # Process each team
                    for team in teams_data:
                        team_name = team['name']
                        
                        # Insert or update team
                        team_id = await conn.fetchval(
                            """
                            INSERT INTO matcherino_teams (team_name, last_updated, is_active) 
                            VALUES ($1, CURRENT_TIMESTAMP, TRUE)
                            ON CONFLICT (team_name) 
                            DO UPDATE SET last_updated = CURRENT_TIMESTAMP, is_active = TRUE
                            RETURNING team_id
                            """, 
                            team_name
                        )
                        
                        # Delete old team members for this team
                        await conn.execute(
                            "DELETE FROM team_members WHERE team_id = $1",
                            team_id
                        )
                        
                        # Insert team members
                        if team.get('members'):
                            for member_name in team['members']:
                                # Try to find matching Discord user
                                discord_user_id = await conn.fetchval(
                                    """
                                    SELECT user_id FROM registrations 
                                    WHERE matcherino_username = $1
                                    """,
                                    member_name
                                )
                                
                                # Insert team member with Discord user ID if found
                                await conn.execute(
                                    """
                                    INSERT INTO team_members 
                                    (team_id, member_name, discord_user_id)
                                    VALUES ($1, $2, $3)
                                    """,
                                    team_id, member_name, discord_user_id
                                )
            
            logger.info(f"Successfully updated {len(teams_data)} teams in database")
        except Exception as e:
            logger.error(f"Error updating Matcherino teams in database: {e}")
            raise
    
    async def get_matcherino_teams(self, active_only=True):
        """
        Get all teams from the database with their members.
        
        Args:
            active_only: If True, only return active teams
            
        Returns:
            list: A list of dictionaries containing team information with members
        """
        if not self.pool:
            await self.create_pool()
            
        try:
            async with self.pool.acquire() as conn:
                # Get all teams
                query = "SELECT * FROM matcherino_teams"
                if active_only:
                    query += " WHERE is_active = TRUE"
                query += " ORDER BY team_name"
                
                teams = await conn.fetch(query)
                
                # Get members for each team
                result = []
                for team in teams:
                    team_dict = dict(team)
                    
                    # Get members
                    members = await conn.fetch(
                        """
                        SELECT tm.member_name, tm.discord_user_id, r.username AS discord_username
                        FROM team_members tm
                        LEFT JOIN registrations r ON tm.discord_user_id = r.user_id
                        WHERE tm.team_id = $1
                        ORDER BY tm.member_name
                        """,
                        team['team_id']
                    )
                    
                    team_dict['members'] = [dict(member) for member in members]
                    result.append(team_dict)
                
                return result
        except Exception as e:
            logger.error(f"Error retrieving Matcherino teams: {e}")
            raise
    
    async def get_user_team(self, user_id):
        """
        Get the team information for a Discord user.
        
        Args:
            user_id: The Discord user ID
            
        Returns:
            dict: Team information if the user is part of a team, None otherwise
        """
        if not self.pool:
            await self.create_pool()
            
        try:
            async with self.pool.acquire() as conn:
                # Get team for this user
                team = await conn.fetchrow(
                    """
                    SELECT t.*, tm.member_name
                    FROM matcherino_teams t
                    JOIN team_members tm ON t.team_id = tm.team_id
                    WHERE tm.discord_user_id = $1 AND t.is_active = TRUE
                    """,
                    user_id
                )
                
                if not team:
                    return None
                    
                # Get all teammates
                teammates = await conn.fetch(
                    """
                    SELECT tm.member_name, tm.discord_user_id, r.username AS discord_username
                    FROM team_members tm
                    LEFT JOIN registrations r ON tm.discord_user_id = r.user_id
                    WHERE tm.team_id = $1 AND tm.discord_user_id != $2
                    ORDER BY tm.member_name
                    """,
                    team['team_id'], user_id
                )
                
                # Convert to dictionary
                result = dict(team)
                result['teammates'] = [dict(teammate) for teammate in teammates]
                
                return result
        except Exception as e:
            logger.error(f"Error retrieving user team: {e}")
            raise
            
    async def unregister_user(self, user_id: int) -> bool:
        """
        Unregister a user from the tournament.
        
        Args:
            user_id: The Discord user ID to unregister
            
        Returns:
            bool: True if user was successfully unregistered, False if user wasn't registered
        """
        try:
            async with self.pool.acquire() as conn:
                # Check if user is registered
                is_registered = await self.is_user_registered(user_id)
                
                if not is_registered:
                    return False
                
                # Remove user from team_members if they are part of a team
                await conn.execute(
                    "UPDATE team_members SET discord_user_id = NULL WHERE discord_user_id = $1",
                    user_id
                )
                
                # Delete the user from registrations
                await conn.execute(
                    "DELETE FROM registrations WHERE user_id = $1",
                    user_id
                )
                
                logger.info(f"Unregistered user with ID {user_id}")
                return True
                
        except Exception as e:
            logger.error(f"Error unregistering user {user_id}: {e}")
            raise
            
    async def ban_user(self, user_id: int, username: str) -> tuple:
        """
        Ban a user from registering for the tournament.
        If the user is already registered, they will be marked as banned.
        If not registered yet, a banned entry will be created for them.
        
        Args:
            user_id: The Discord user ID to ban
            username: The Discord username 
            
        Returns:
            tuple: (was_registered, was_banned) 
                  was_registered is True if user was already registered
                  was_banned is True if user was successfully banned
        """
        try:
            async with self.pool.acquire() as conn:
                # Check if user is already registered
                existing = await conn.fetchrow(
                    "SELECT * FROM registrations WHERE user_id = $1", user_id
                )
                
                if existing:
                    # User already exists, update the banned status
                    await conn.execute(
                        "UPDATE registrations SET banned = TRUE WHERE user_id = $1",
                        user_id
                    )
                    
                    # Remove user from team_members if they are part of a team
                    await conn.execute(
                        "UPDATE team_members SET discord_user_id = NULL WHERE discord_user_id = $1",
                        user_id
                    )
                    
                    logger.info(f"Banned existing user {username} ({user_id})")
                    return (True, True)
                else:
                    # User doesn't exist, create a banned entry
                    await conn.execute(
                        "INSERT INTO registrations (user_id, username, registered_at, banned) VALUES ($1, $2, $3, TRUE)",
                        user_id, username, datetime.utcnow()
                    )
                    
                    logger.info(f"Created banned entry for user {username} ({user_id})")
                    return (False, True)
                    
        except Exception as e:
            logger.error(f"Error banning user {username} ({user_id}): {e}")
            raise
            
    async def is_user_banned(self, user_id: int) -> bool:
        """
        Check if a user is banned from registration.
        
        Args:
            user_id: The Discord user ID to check
            
        Returns:
            bool: True if user is banned, False otherwise
        """
        try:
            async with self.pool.acquire() as conn:
                banned = await conn.fetchval(
                    "SELECT banned FROM registrations WHERE user_id = $1",
                    user_id
                )
                
                return bool(banned)
        except Exception as e:
            logger.error(f"Error checking if user {user_id} is banned: {e}")
            raise

    async def unban_user(self, user_id: int) -> bool:
        """Unban a user from tournament registration.
        
        Args:
            user_id (int): The Discord user ID to unban
            
        Returns:
            bool: True if the user was successfully unbanned, False otherwise
        """
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    query = """
                        UPDATE registrations 
                        SET banned = FALSE 
                        WHERE user_id = $1 AND banned = TRUE
                        RETURNING user_id
                    """
                    result = await conn.fetchrow(query, user_id)
                    return result is not None
                    
        except Exception as e:
            logger.error(f"Error unbanning user {user_id}: {e}")
            return False