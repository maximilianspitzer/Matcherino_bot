import asyncio
import discord
from discord import app_commands
from discord.ext import commands, tasks
import logging
import os
from dotenv import load_dotenv
from db import Database
import datetime

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Get bot token and application ID from environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
APPLICATION_ID = os.getenv("APPLICATION_ID")
if not BOT_TOKEN:
    logger.critical("BOT_TOKEN environment variable not set")
    raise ValueError("BOT_TOKEN environment variable not set")

# Guild configuration
TARGET_GUILD_ID = 1212508610438107166  # Guild ID for slash command sync

# Tournament configuration
TOURNAMENT_JOIN_CODE = "lenamilize"  # Central definition of join code for Matcherino
TOURNAMENT_ID = os.getenv("MATCHERINO_TOURNAMENT_ID")
if not TOURNAMENT_ID:
    logger.warning("MATCHERINO_TOURNAMENT_ID environment variable not set - team syncing will not work")

# Team sync configuration
SYNC_INTERVAL_MINUTES = 15  # Sync every 15 minutes

# Initialize bot with intents
intents = discord.Intents.default()
intents.members = True  # Required for accessing member information
intents.message_content = True  # Required for message content

class CustomBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            application_id=int(APPLICATION_ID) if APPLICATION_ID else None
        )
        self.initial_extensions = [
            "cogs.admin_cog",
            "cogs.registration_cog",
            "cogs.teams_cog",
            "cogs.matcherino_cog"
        ]
        # Add configuration attributes
        self.TOURNAMENT_JOIN_CODE = TOURNAMENT_JOIN_CODE
        self.TOURNAMENT_ID = TOURNAMENT_ID

    async def setup_hook(self):
        """This is called when the bot starts, before it connects to Discord"""
        for extension in self.initial_extensions:
            try:
                await self.load_extension(extension)
                logger.info(f"Loaded extension: {extension}")
            except Exception as e:
                logger.error(f"Failed to load extension {extension}: {e}")

        # Sync the commands with Discord
        guild = discord.Object(id=TARGET_GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        logger.info(f"Synced {len(synced)} slash commands")
        for cmd in synced:
            logger.info(f"  - {cmd.name}")

bot = CustomBot()

# Create the database connection
db = None

# Disable the default help command
bot.help_command = None

@bot.event
async def on_ready():
    """Event triggered when the bot is ready."""
    try:
        # Create and set up database
        bot.db = await setup_database()
        
        # Start the scheduled tasks
        if not team_sync_task.is_running():
            team_sync_task.start()
        
        logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
        logger.info("Bot is ready!")
    except Exception as e:
        logger.error(f"Error during startup: {e}")

async def setup_database():
    """Setup the database connection."""
    from db import Database
    db = Database(join_code=TOURNAMENT_JOIN_CODE)
    await db.create_pool()
    await db.setup_tables()
    return db

@tasks.loop(minutes=SYNC_INTERVAL_MINUTES)
async def team_sync_task():
    """Scheduled task that runs every 15 minutes to sync team data from Matcherino."""
    if not TOURNAMENT_ID:
        logger.warning("MATCHERINO_TOURNAMENT_ID not set - skipping scheduled team sync")
        return
        
    try:
        logger.info("Starting scheduled team sync...")
        # Get the teams cog to perform the sync
        teams_cog = bot.get_cog("TeamsCog")
        if teams_cog:
            await teams_cog.sync_matcherino_teams()
            logger.info("Scheduled team sync completed")
        else:
            logger.warning("TeamsCog not found - could not perform scheduled team sync")
    except Exception as e:
        logger.error(f"Error during scheduled team sync: {e}")

@team_sync_task.before_loop
async def before_team_sync():
    """Wait until the bot is ready before starting the team sync task."""
    await bot.wait_until_ready()

@bot.event
async def on_command_error(ctx, error):
    """Global error handler for command errors."""
    if isinstance(error, commands.CommandOnCooldown):
        # Silently ignore the cooldown error
        return

    if isinstance(error, commands.CommandNotFound):
        # Silently ignore command not found errors
        return
    
    logger.error(f"Command error: {error}", exc_info=True)
    
    # Handle various command errors
    if isinstance(error, commands.MissingPermissions):
        await ctx.reply("You don't have permission to use this command.")
    elif isinstance(error, commands.BadArgument):
        await ctx.reply(f"Invalid argument: {str(error)}")
    else:
        await ctx.reply(f"An error occurred: {str(error)}")

async def main():
    """Main function to run the bot."""
    try:
        async with bot:
            await bot.start(BOT_TOKEN)
    except KeyboardInterrupt:
        # Handle clean shutdown on keyboard interrupt
        logger.info("Bot shutting down...")
        if hasattr(bot, 'db') and bot.db:
            await bot.db.close()
    except Exception as e:
        logger.critical(f"Unexpected error: {e}")
    finally:
        # Ensure clean shutdown
        if hasattr(bot, 'db') and bot.db:
            await bot.db.close()

# Execute the main function when the script is run directly
if __name__ == "__main__":
    asyncio.run(main())