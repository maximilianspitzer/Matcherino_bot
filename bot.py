import asyncio
import discord
from discord import app_commands
from discord.ext import commands, tasks
import logging
import os
import csv
import io
from dotenv import load_dotenv
from db import Database
from matcherino_scraper import MatcherinoScraper
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

# Get bot token from environment variable
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logger.critical("BOT_TOKEN environment variable not set")
    raise ValueError("BOT_TOKEN environment variable not set")

# Guild configuration
TARGET_GUILD_ID = 1212508610438107166  # Guild ID for slash command sync

# Tournament configuration
TOURNAMENT_JOIN_CODE = "test test test"  # Central definition of join code for Matcherino
TOURNAMENT_ID = os.getenv("MATCHERINO_TOURNAMENT_ID")
if not TOURNAMENT_ID:
    logger.warning("MATCHERINO_TOURNAMENT_ID environment variable not set - team syncing will not work")

# Team sync configuration
SYNC_INTERVAL_MINUTES = 15  # Sync every 15 minutes

# Initialize bot with intents
intents = discord.Intents.default()
intents.members = True  # Required for accessing member information
intents.message_content = True  # Required for message content

# Use "!" as the command prefix to enable standard prefix commands
bot = commands.Bot(command_prefix="!", intents=intents)
db = Database(join_code=TOURNAMENT_JOIN_CODE)

# Disable the default help command
bot.help_command = None

@bot.event
async def on_ready():
    """Event triggered when the bot is ready."""
    try:
        # Create and set up database
        await db.create_pool()
        await db.setup_tables()
        
        # Start the scheduled tasks
        if not team_sync_task.is_running():
            team_sync_task.start()
        
        logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
        logger.info("Bot is ready!")
        
        # Sync slash commands if not already done
        await sync_commands()
    except Exception as e:
        logger.error(f"Error during startup: {e}")

async def sync_commands():
    """Simple function to sync slash commands to the guild only."""
    try:
        logger.info(f"Syncing commands to guild {TARGET_GUILD_ID}...")
        
        # Create guild object
        guild = discord.Object(id=TARGET_GUILD_ID)
        
        # Sync commands to guild
        synced = await bot.tree.sync(guild=guild)
        
        # Log results
        logger.info(f"Synced {len(synced)} guild commands")
        for cmd in synced:
            logger.info(f"  - {cmd.name}")
        
        return True, f"Successfully synced {len(synced)} commands to the server"
    except Exception as e:
        logger.error(f"Error syncing commands: {e}", exc_info=True)
        return False, f"Failed to sync commands: {str(e)}"

@bot.command(name="sync")
async def sync_legacy(ctx):
    """Legacy command to sync slash commands to the guild (admin only)."""
    # Silent ignore if user doesn't have admin permissions
    if not ctx.author.guild_permissions.administrator:
        return
    
    # Log who used the command for auditing
    logger.info(f"Sync command used by admin {ctx.author.name} (ID: {ctx.author.id})")
    
    # Send initial message
    message = await ctx.reply("Syncing slash commands to this server... This may take a moment.")
    
    # Perform sync
    success, result = await sync_commands()
    
    # Update message with result
    if success:
        await message.edit(content=f"✅ {result}")
    else:
        await message.edit(content=f"❌ Command sync failed: {result}")

@bot.tree.command(name="register", description="Register for the tournament", guild=discord.Object(id=TARGET_GUILD_ID))
@app_commands.describe(matcherino_username="Your Matcherino username (required for team assignment)")
async def register(interaction: discord.Interaction, matcherino_username: str):
    """Slash command to register a user for the tournament."""
    try:
        user_id = interaction.user.id
        username = str(interaction.user)
        
        # Validate Matcherino username format
        # Basic validation - non-empty and reasonable length
        if len(matcherino_username.strip()) < 3:
            await interaction.response.send_message(
                "Invalid Matcherino username. Please provide a valid username (at least 3 characters).",
                ephemeral=True
            )
            return
            
        # Remove any whitespace
        matcherino_username = matcherino_username.strip()
        
        logger.info(f"User {username} ({user_id}) registering with Matcherino username: {matcherino_username}")
        
        # Check if the user is already registered
        is_registered = await db.is_user_registered(user_id)
        
        # Register the user or get existing join code
        success, join_code = await db.register_user(user_id, username, matcherino_username)
        
        if not success and is_registered:
            await interaction.response.send_message(
                f"Your Matcherino username has been updated to: **{matcherino_username}**\n\nThe tournament join code is: **`{join_code}`**\n\nUse this code when registering on Matcherino to verify your participation.", 
                ephemeral=True
            )
            return
        
        # Try to assign the "Registered" role if it exists
        guild = interaction.guild
        
        # Find the "Registered" role
        registered_role = discord.utils.get(guild.roles, name="Registered")
        
        if registered_role:
            try:
                await interaction.user.add_roles(registered_role)
                logger.info(f"Assigned 'Registered' role to user {username} ({user_id})")
                
                await interaction.response.send_message(
                    f"You have been successfully registered for the tournament with Matcherino username **{matcherino_username}** and assigned the 'Registered' role!\n\nThe tournament join code is: **`{join_code}`**\n\nUse this code when registering on Matcherino to verify your participation.",
                    ephemeral=True
                )
            except discord.Forbidden:
                logger.error(f"Bot doesn't have permission to assign roles to {username} ({user_id})")
                await interaction.response.send_message(
                    f"You have been registered for the tournament with Matcherino username **{matcherino_username}**, but I couldn't assign you the 'Registered' role due to permission issues.\n\nThe tournament join code is: **`{join_code}`**\n\nUse this code when registering on Matcherino to verify your participation.",
                    ephemeral=True
                )
            except Exception as e:
                logger.error(f"Error assigning role to {username} ({user_id}): {e}")
                await interaction.response.send_message(
                    f"You have been registered for the tournament with Matcherino username **{matcherino_username}**, but there was an error assigning the 'Registered' role.\n\nThe tournament join code is: **`{join_code}`**\n\nUse this code when registering on Matcherino to verify your participation.",
                    ephemeral=True
                )
        else:
            logger.warning("'Registered' role not found in the server")
            await interaction.response.send_message(
                f"You have been successfully registered for the tournament with Matcherino username **{matcherino_username}**! (No 'Registered' role found to assign)\n\nThe tournament join code is: **`{join_code}`**\n\nUse this code when registering on Matcherino to verify your participation.",
                ephemeral=True
            )
            
    except Exception as e:
        logger.error(f"Error in register command: {e}")
        await interaction.response.send_message(
            "An error occurred while processing your registration. Please try again later.",
            ephemeral=True
        )

@bot.tree.command(name="mycode", description="Get the tournament join code", guild=discord.Object(id=TARGET_GUILD_ID))
async def mycode(interaction: discord.Interaction):
    """Slash command to retrieve the tournament join code."""
    try:
        user_id = interaction.user.id
        
        # Check if the user is registered
        is_registered = await db.is_user_registered(user_id)
        
        if not is_registered:
            await interaction.response.send_message(
                "You are not registered for the tournament. Please use `/register` first to get the join code.", 
                ephemeral=True
            )
            return
        
        # Get the tournament join code
        join_code = await db.get_user_join_code(user_id)
        
        if join_code:
            await interaction.response.send_message(
                f"The tournament join code is: **`{join_code}`**\n\nUse this code when registering on Matcherino to verify your participation.",
                ephemeral=True
            )
        else:
            # This shouldn't normally happen if they're registered
            await interaction.response.send_message(
                "You are registered, but there was an error retrieving the join code. Please contact an admin for assistance.",
                ephemeral=True
            )
            
    except Exception as e:
        logger.error(f"Error in mycode command: {e}")
        await interaction.response.send_message(
            "An error occurred while retrieving the join code. Please try again later.",
            ephemeral=True
        )

@bot.tree.command(
    name="registered", 
    description="Admin command to view all registered users", 
    guild=discord.Object(id=TARGET_GUILD_ID)
)
@app_commands.default_permissions(administrator=True)
async def registered_slash(interaction: discord.Interaction):
    """Slash command to retrieve all registered users."""
    try:
        # Get all registered users
        registered_users = await db.get_registered_users()
        
        if not registered_users:
            await interaction.response.send_message("No users are currently registered for the tournament.", ephemeral=True)
            return
            
        # Format the response
        response = "**Registered Users:**\n\n"
        response += f"Tournament join code for all users: **`{TOURNAMENT_JOIN_CODE}`**\n\n"
        
        for i, user in enumerate(registered_users, 1):
            user_id = user['user_id']
            username = user['username']
            registered_at = user['registered_at'].strftime("%Y-%m-%d %H:%M:%S UTC")
            
            response += f"{i}. {username} (ID: {user_id})\n   Registered at: {registered_at}\n\n"
            
            # Discord has a character limit for messages, so we need to handle long responses
            if len(response) > 1800:  # Safe limit to stay under Discord's 2000 character limit
                await interaction.followup.send(response)
                response = "**Continued:**\n\n"
                
        # Send any remaining response
        if response:
            # For the first response, use response.send_message
            if len(registered_users) <= 10 or i <= 10:  # If it's the first chunk
                await interaction.response.send_message(response, ephemeral=True)
            else:  # For subsequent chunks
                await interaction.followup.send(response, ephemeral=True)
            
    except Exception as e:
        logger.error(f"Error in registered command: {e}")
        # If we haven't responded yet
        try:
            await interaction.response.send_message("An error occurred while retrieving registered users.", ephemeral=True)
        except:
            await interaction.followup.send("An error occurred while retrieving registered users.", ephemeral=True)

@bot.tree.command(
    name="check-code", 
    description="Admin command to check if a user is registered", 
    guild=discord.Object(id=TARGET_GUILD_ID)
)
@app_commands.default_permissions(administrator=True)
async def check_code_slash(interaction: discord.Interaction, user: discord.User):
    """Slash command to check if a user is registered for the tournament."""
    try:
        # Get the user's registration info
        user_id = user.id
        username = str(user)
        
        # Check if the user is registered
        is_registered = await db.is_user_registered(user_id)
        
        if not is_registered:
            await interaction.response.send_message(f"User {username} is not registered for the tournament.", ephemeral=True)
            return
            
        # The join code is the same for everyone
        join_code = TOURNAMENT_JOIN_CODE
        
        await interaction.response.send_message(
            f"User: {username} (ID: {user_id})\nStatus: Registered\nThe tournament join code is: **`{join_code}`**", 
            ephemeral=True
        )
            
    except Exception as e:
        logger.error(f"Error in check-code command: {e}")
        await interaction.response.send_message("An error occurred while checking the user's registration status.", ephemeral=True)

@bot.tree.command(
    name="export", 
    description="Admin command to export all registered users to a CSV file", 
    guild=discord.Object(id=TARGET_GUILD_ID)
)
@app_commands.default_permissions(administrator=True)
async def export_slash(interaction: discord.Interaction):
    """Slash command to export all registered users."""
    try:
        # Defer the response since this might take some time
        await interaction.response.defer(ephemeral=True)
            
        # Get all registered users
        registered_users = await db.get_registered_users()
        
        if not registered_users:
            await interaction.followup.send("No users are currently registered for the tournament.", ephemeral=True)
            return
            
        # Create a CSV file in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['User ID', 'Username', 'Registered At'])
        
        # Write data
        for user in registered_users:
            writer.writerow([
                user['user_id'],
                user['username'],
                user['registered_at'].strftime("%Y-%m-%d %H:%M:%S UTC")
            ])
            
        output.seek(0)  # Reset to beginning of file
        
        # Convert to bytes for Discord attachment
        csv_bytes = output.getvalue().encode('utf-8')
        file = discord.File(io.BytesIO(csv_bytes), filename="tournament_registrations.csv")
        
        await interaction.followup.send("Here's the export of all registered users:", file=file, ephemeral=True)
            
    except Exception as e:
        logger.error(f"Error in export command: {e}")
        await interaction.followup.send("An error occurred while exporting registered users data.", ephemeral=True)

@bot.tree.command(
    name="resync", 
    description="Admin command to resync slash commands for this server", 
    guild=discord.Object(id=TARGET_GUILD_ID)
)
@app_commands.default_permissions(administrator=True)
async def resync_slash(interaction: discord.Interaction):
    """Slash command to resync slash commands with improved error handling."""
    try:
        await interaction.response.send_message("Resyncing slash commands... This may take a moment.", ephemeral=True)
        
        # Use the dedicated sync function for consistency
        success, result = await sync_commands()
        
        if success:
            await interaction.followup.send(f"✅ {result}", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Command sync failed: {result}", ephemeral=True)
            
    except Exception as e:
        logger.error(f"Error in resync command: {e}", exc_info=True)
        try:
            await interaction.followup.send("An error occurred while resyncing slash commands.", ephemeral=True)
        except:
            # If we haven't responded yet
            await interaction.response.send_message("An error occurred while resyncing slash commands.", ephemeral=True)

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

@bot.tree.command(name="help", description="Show available commands", guild=discord.Object(id=TARGET_GUILD_ID))
async def help_slash(interaction: discord.Interaction):
    """Show available commands and their descriptions."""
    embed = discord.Embed(
        title="Bot Commands",
        description="Here are the available commands:",
        color=discord.Color.blue()
    )
    
    # Regular user commands
    embed.add_field(
        name="/register <matcherino_username>",
        value="Register for the tournament and get your join code. You must provide your Matcherino username.",
        inline=False
    )
    embed.add_field(
        name="/mycode",
        value="Get your tournament join code",
        inline=False
    )
    embed.add_field(
        name="/my-team",
        value="View your team and its members",
        inline=False
    )
    embed.add_field(
        name="/user-team",
        value="Check which team a Discord user belongs to",
        inline=False
    )
    
    # Add admin commands if user has admin permissions
    if interaction.user.guild_permissions.administrator:
        embed.add_field(
            name="Admin Commands",
            value="The following commands are available to administrators only:",
            inline=False
        )
        embed.add_field(
            name="/registered",
            value="View all registered users",
            inline=False
        )
        embed.add_field(
            name="/check-code",
            value="Check if a user is registered",
            inline=False
        )
        embed.add_field(
            name="/export",
            value="Export registered users to CSV",
            inline=False
        )
        embed.add_field(
            name="/sync-teams",
            value="Manually trigger team synchronization from Matcherino",
            inline=False
        )
        embed.add_field(
            name="/resync",
            value="Resync slash commands for this server",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# Add a basic ping slash command directly
@bot.tree.command(name="ping", description="Check bot latency", guild=discord.Object(id=TARGET_GUILD_ID))
async def ping_slash(interaction: discord.Interaction):
    """Responds with the bot's latency."""
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(f"Pong! Latency: {latency}ms", ephemeral=True)

@tasks.loop(minutes=SYNC_INTERVAL_MINUTES)
async def team_sync_task():
    """Scheduled task that runs every 15 minutes to sync team data from Matcherino."""
    if not TOURNAMENT_ID:
        logger.warning("MATCHERINO_TOURNAMENT_ID not set - skipping scheduled team sync")
        return
        
    try:
        logger.info("Starting scheduled team sync...")
        await sync_matcherino_teams()
        logger.info("Scheduled team sync completed")
    except Exception as e:
        logger.error(f"Error during scheduled team sync: {e}")

@team_sync_task.before_loop
async def before_team_sync():
    """Wait until the bot is ready before starting the team sync task."""
    await bot.wait_until_ready()

async def sync_matcherino_teams():
    """Fetch team data from Matcherino and sync it to the database."""
    if not TOURNAMENT_ID:
        return
        
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
            
            logger.info(f"Team sync completed successfully - updated {len(teams_data)} teams")
            return teams_data
            
    except Exception as e:
        logger.error(f"Error during team sync: {e}")
        raise

@bot.tree.command(
    name="sync-teams", 
    description="Admin command to manually sync teams from Matcherino", 
    guild=discord.Object(id=TARGET_GUILD_ID)
)
@app_commands.default_permissions(administrator=True)
async def sync_teams_command(interaction: discord.Interaction):
    """Admin command to manually trigger team synchronization from Matcherino."""
    if not TOURNAMENT_ID:
        await interaction.response.send_message("MATCHERINO_TOURNAMENT_ID is not set. Please set it in the .env file.", ephemeral=True)
        return
        
    await interaction.response.defer(ephemeral=True)
    
    try:
        teams_data = await sync_matcherino_teams()
        
        if teams_data:
            await interaction.followup.send(f"Successfully synced {len(teams_data)} teams from Matcherino tournament.", ephemeral=True)
        else:
            await interaction.followup.send("No teams found in the tournament or sync failed.", ephemeral=True)
    
    except Exception as e:
        logger.error(f"Error in sync-teams command: {e}")
        await interaction.followup.send(f"Error syncing teams: {str(e)}", ephemeral=True)

@bot.tree.command(name="my-team", description="View your team and its members", guild=discord.Object(id=TARGET_GUILD_ID))
async def my_team_command(interaction: discord.Interaction):
    """Command to view the user's team and its members."""
    await interaction.response.defer(ephemeral=True)
    
    try:
        user_id = interaction.user.id
        team_info = await db.get_user_team(user_id)
        
        if not team_info:
            await interaction.followup.send(
                "You are not currently assigned to any team. Make sure you've registered with your Matcherino username using the /register command.",
                ephemeral=True
            )
            return
            
        # Build an embed to display the team
        embed = discord.Embed(
            title=f"Team: {team_info['team_name']}",
            description=f"You are a member of this team with {len(team_info['members'])} total members.",
            color=discord.Color.green(),
            timestamp=datetime.datetime.utcnow()
        )
        
        # Add members to the embed
        member_list = ""
        for member in team_info['members']:
            is_you = " (You)" if str(member.get('discord_id', "")) == str(user_id) else ""
            discord_user = f" (Discord: {member['discord_username']})" if member.get('discord_username') else ""
            member_list += f"• {member['member_name']}{discord_user}{is_you}\n"
            
        embed.add_field(
            name="Team Members",
            value=member_list if member_list else "No members found",
            inline=False
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
    except Exception as e:
        logger.error(f"Error in my-team command: {e}")
        await interaction.followup.send(f"Error retrieving your team: {str(e)}", ephemeral=True)

@bot.tree.command(name="user-team", description="Check which team a Discord user belongs to", guild=discord.Object(id=TARGET_GUILD_ID))
async def user_team_command(interaction: discord.Interaction, user: discord.User):
    """Command to check which team a Discord user belongs to."""
    await interaction.response.defer(ephemeral=True)
    
    try:
        team_info = await db.get_user_team(user.id)
        
        if not team_info:
            await interaction.followup.send(
                f"{user.display_name} is not currently assigned to any team. They may need to register with their Matcherino username.",
                ephemeral=True
            )
            return
            
        # Build an embed to display the team
        embed = discord.Embed(
            title=f"Team: {team_info['team_name']}",
            description=f"{user.display_name} is a member of this team with {len(team_info['members'])} total members.",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.utcnow()
        )
        
        # Add members to the embed
        member_list = ""
        for member in team_info['members']:
            is_target = " (Target User)" if str(member.get('discord_id', "")) == str(user.id) else ""
            discord_user = f" (Discord: {member['discord_username']})" if member.get('discord_username') else ""
            member_list += f"• {member['member_name']}{discord_user}{is_target}\n"
            
        embed.add_field(
            name="Team Members",
            value=member_list if member_list else "No members found",
            inline=False
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
    except Exception as e:
        logger.error(f"Error in user-team command: {e}")
        await interaction.followup.send(f"Error retrieving the user's team: {str(e)}", ephemeral=True)

@bot.command(name="job")
@commands.cooldown(1, 20, commands.BucketType.default)  # Global cooldown of 20 seconds
async def job(ctx):
    """Command to send a specific link and delete the invocation."""
    try:
        
        # Send the link
        await ctx.send("https://media.discordapp.net/attachments/1118988563577577574/1150888584778371153/YiEtFVn.gif")
    except Exception as e:
        logger.error(f"Error in job command: {e}")

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
        if db.pool:
            await db.close()

if __name__ == "__main__":
    asyncio.run(main()) 