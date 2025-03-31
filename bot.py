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
        
        # Check if the user is banned
        is_banned = await db.is_user_banned(user_id)
        if is_banned:
            await interaction.response.send_message(
                "You are banned from registering for this tournament. Please contact an administrator for assistance.",
                ephemeral=True
            )
            return
        
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
        
        # Check if signups are closed - this is the new part
        if success is None:
            # Signups are closed and user is not already registered
            await interaction.response.send_message(
                "⛔ **Tournament signups are currently closed for new registrations.**\n\nOnly existing participants can update their Matcherino usernames at this time. Please contact an administrator for assistance.",
                ephemeral=True
            )
            return
        
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
        
        # Check if user is banned
        is_banned = await db.is_user_banned(user_id)
        if is_banned:
            await interaction.response.send_message(
                "You are banned from participating in this tournament. Please contact an administrator for assistance.",
                ephemeral=True
            )
            return
        
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
            
        # Get all registered users who are not banned
        registered_users = await db.get_registered_users()
        active_users = [user for user in registered_users if not user['banned']]
        
        if not active_users:
            await interaction.followup.send("No users are currently registered for the tournament.", ephemeral=True)
            return
            
        # Create a CSV file in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['User ID', 'Username', 'Registered At'])
        
        # Write data
        for user in active_users:
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
        name="/leave",
        value="Remove your own tournament registration",
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
    embed.add_field(
        name="/verify-username",
        value="Check if your Matcherino username is properly formatted",
        inline=False
    )
    embed.add_field(
        name="/ping",
        value="Check bot latency",
        inline=False
    )
    embed.add_field(
        name="/help",
        value="Show this help message",
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
        embed.add_field(
            name="/unregister",
            value="Unregister a user from the tournament",
            inline=False
        )
        embed.add_field(
            name="/ban",
            value="Ban a user from registering for the tournament",
            inline=False
        )
        embed.add_field(
            name="/unban",
            value="Unban a user from the tournament",
            inline=False
        )
        embed.add_field(
            name="/match-free-agents",
            value="Match Matcherino participants with Discord users",
            inline=False
        )
        embed.add_field(
            name="/send-username-reminders",
            value="Send reminders to users with improperly formatted Matcherino usernames",
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
            
            # Update database with team data - this marks all teams as inactive first,
            # then marks the current teams as active
            await db.update_matcherino_teams(teams_data)
            
            # Get all inactive teams (those no longer on Matcherino)
            inactive_teams = await db.get_inactive_teams()
                
            if inactive_teams:
                logger.info(f"Found {len(inactive_teams)} teams that are no longer on Matcherino")
                
                # Delete all inactive teams
                removed_count = 0
                for team in inactive_teams:
                    team_id = team['team_id']
                    team_name = team['team_name']
                    logger.info(f"Removing inactive team: {team_name} (ID: {team_id})")
                    
                    # Use the Database.remove_team method to delete the team
                    success = await db.remove_team(team_id)
                    if success:
                        removed_count += 1
                
                logger.info(f"Successfully removed {removed_count} inactive teams")
            
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
        
        # Check if user is banned
        is_banned = await db.is_user_banned(user_id)
        if is_banned:
            await interaction.followup.send(
                "You are banned from participating in this tournament. Please contact an administrator for assistance.",
                ephemeral=True
            )
            return
        
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
        # Check if the requesting user is banned
        requester_id = interaction.user.id
        is_banned = await db.is_user_banned(requester_id)
        if is_banned:
            await interaction.followup.send(
                "You are banned from participating in this tournament. Please contact an administrator for assistance.",
                ephemeral=True
            )
            return
            
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
        # Check if user has admin permissions
        if not ctx.author.guild_permissions.administrator:
            return  # Silently ignore if user doesn't have admin permissions
        
        # Send the link
        await ctx.send("https://media.discordapp.net/attachments/1118988563577577574/1150888584778371153/YiEtFVn.gif")
    except Exception as e:
        logger.error(f"Error in job command: {e}")

@bot.tree.command(
    name="unregister", 
    description="Admin command to unregister a user from the tournament", 
    guild=discord.Object(id=TARGET_GUILD_ID)
)
@app_commands.default_permissions(administrator=True)
async def unregister_command(interaction: discord.Interaction, user: discord.User):
    """Admin command to unregister a user from the tournament."""
    try:
        user_id = user.id
        username = str(user)
        
        # Check if the user is registered first
        is_registered = await db.is_user_registered(user_id)
        
        if not is_registered:
            await interaction.response.send_message(f"User {username} is not registered for the tournament.", ephemeral=True)
            return
        
        # Try to remove the "Registered" role if it exists
        guild = interaction.guild
        registered_role = discord.utils.get(guild.roles, name="Registered")
        
        if registered_role and user in guild.members:
            member = guild.get_member(user_id)
            if member and registered_role in member.roles:
                try:
                    await member.remove_roles(registered_role)
                    logger.info(f"Removed 'Registered' role from user {username} ({user_id})")
                except discord.Forbidden:
                    logger.error(f"Bot doesn't have permission to remove roles from {username} ({user_id})")
                except Exception as e:
                    logger.error(f"Error removing role from {username} ({user_id}): {e}")
        
        # Unregister the user
        success = await db.unregister_user(user_id)
        
        if success:
            await interaction.response.send_message(f"User {username} has been unregistered from the tournament.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Failed to unregister user {username}. There might have been a database error.", ephemeral=True)
            
    except Exception as e:
        logger.error(f"Error in unregister command: {e}")
        await interaction.response.send_message("An error occurred while unregistering the user.", ephemeral=True)

@bot.tree.command(
    name="ban", 
    description="Admin command to ban a user from registering for the tournament", 
    guild=discord.Object(id=TARGET_GUILD_ID)
)
@app_commands.default_permissions(administrator=True)
async def ban_command(interaction: discord.Interaction, user: discord.User):
    """Admin command to ban a user from registering for the tournament."""
    try:
        user_id = user.id
        username = str(user)
        
        # Check if user is registered and unregister them first
        is_registered = await db.is_user_registered(user_id)
        if is_registered:
            await db.unregister_user(user_id)
            logger.info(f"Unregistered banned user {username} ({user_id})")
        
        # Try to remove the "Registered" role if it exists
        guild = interaction.guild
        registered_role = discord.utils.get(guild.roles, name="Registered")
        
        if registered_role and user in guild.members:
            member = guild.get_member(user_id)
            if member and registered_role in member.roles:
                try:
                    await member.remove_roles(registered_role)
                    logger.info(f"Removed 'Registered' role from banned user {username} ({user_id})")
                except discord.Forbidden:
                    logger.error(f"Bot doesn't have permission to remove roles from {username} ({user_id})")
                except Exception as e:
                    logger.error(f"Error removing role from {username} ({user_id}): {e}")
        
        # Ban the user
        success = await db.ban_user(user_id, username)
        
        if success:
            message = f"User {username} has been banned from registering for the tournament"
            if is_registered:
                message += " and was unregistered from the tournament"
            await interaction.response.send_message(f"{message}.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Failed to ban user {username}.", ephemeral=True)
            
    except Exception as e:
        logger.error(f"Error in ban command: {e}")
        await interaction.response.send_message("An error occurred while banning the user.", ephemeral=True)

@bot.tree.command(
    name="unban", 
    description="Admin command to unban a user from the tournament", 
    guild=discord.Object(id=TARGET_GUILD_ID)
)
@app_commands.default_permissions(administrator=True)
async def unban_command(interaction: discord.Interaction, user: discord.User):
    """Admin command to unban a user from tournament registration."""
    try:
        user_id = user.id
        username = str(user)
        
        # Check if user is banned first
        is_banned = await db.is_user_banned(user_id)
        
        if not is_banned:
            await interaction.response.send_message(f"User {username} is not banned from the tournament.", ephemeral=True)
            return
        
        # Unban the user
        success = await db.unban_user(user_id)
        
        if success:
            await interaction.response.send_message(f"User {username} has been unbanned and can now register for the tournament.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Failed to unban user {username}.", ephemeral=True)
            
    except Exception as e:
        logger.error(f"Error in unban command: {e}")
        await interaction.response.send_message("An error occurred while unbanning the user.", ephemeral=True)

@bot.tree.command(
    name="matcherino-username",
    description="Admin command to get a user's Matcherino username",
    guild=discord.Object(id=TARGET_GUILD_ID)
)
@app_commands.default_permissions(administrator=True)
async def matcherino_username_command(interaction: discord.Interaction, user: discord.User):
    """Admin command to get a user's Matcherino username."""
    try:
        user_id = user.id
        username = str(user)
        
        # Get the user's Matcherino username
        matcherino_username = await db.get_matcherino_username(user_id)
        await interaction.response.send_message(
            f"User: {username} (ID: {user_id})\nMatcherino Username: **{matcherino_username}**",
            ephemeral=True
        )


    except Exception as e:
        logger.error(f"Error in matcherino-username command: {e}")
        await interaction.response.send_message("An error occurred while retrieving the user's Matcherino username.", ephemeral=True)
        return



@bot.tree.command(
    name="leave", 
    description="Remove your own tournament registration", 
    guild=discord.Object(id=TARGET_GUILD_ID)
)
async def leave_command(interaction: discord.Interaction):
    """Command for users to unregister themselves from the tournament."""
    try:
        user_id = interaction.user.id
        username = str(interaction.user)
        
        # Check if the user is registered first
        is_registered = await db.is_user_registered(user_id)
        
        if not is_registered:
            await interaction.response.send_message("You are not registered for the tournament.", ephemeral=True)
            return
        
        # Try to remove the "Registered" role if it exists
        guild = interaction.guild
        registered_role = discord.utils.get(guild.roles, name="Registered")
        
        if registered_role and registered_role in interaction.user.roles:
            try:
                await interaction.user.remove_roles(registered_role)
                logger.info(f"Removed 'Registered' role from user {username} ({user_id})")
            except discord.Forbidden:
                logger.error(f"Bot doesn't have permission to remove roles from {username} ({user_id})")
            except Exception as e:
                logger.error(f"Error removing role from {username} ({user_id}): {e}")
        
        # Unregister the user
        success = await db.unregister_user(user_id)
        
        if success:
            await interaction.response.send_message("You have been unregistered from the tournament.", ephemeral=True)
        else:
            await interaction.response.send_message("Failed to unregister you from the tournament. There might have been a database error.", ephemeral=True)
            
    except Exception as e:
        logger.error(f"Error in leave command: {e}")
        await interaction.response.send_message("An error occurred while unregistering you from the tournament.", ephemeral=True)

async def match_participants_with_db_users(participants, db_users):
    """
    Match participants from Matcherino API with users in the database.
    
    Args:
        participants (list): List of participants from Matcherino API
        db_users (list): List of users from the database with Matcherino usernames
        
    Returns:
        tuple: (exact_matches, name_only_matches, ambiguous_matches, 
                unmatched_participants, unmatched_db_users)
    """
    # Initialize result containers
    exact_matches = []        # Perfect matches (user with matcherino_username = participant name)
    name_only_matches = []    # Matches based on username only (no tag)
    ambiguous_matches = []    # Multiple potential matches for the same username
    
    # Track discord users that have been matched to avoid duplicates
    matched_discord_ids = set()
    
    # Track participant names that have been processed
    processed_participants = set()
    
    # Pre-process db_users into dictionaries for O(1) lookups
    # 1. Dictionary for exact matches (lowercase full username -> user)
    exact_match_dict = {}
    # 2. Dictionary for name-only matches (lowercase name part -> list of users)
    name_match_dict = {}
    
    for user in db_users:
        matcherino_username = user.get('matcherino_username', '').strip()
        if not matcherino_username:
            continue
            
        # Store for exact match lookup
        exact_match_dict[matcherino_username.lower()] = user
        
        # Store for name-only match lookup
        name_part = matcherino_username.split('#')[0].strip().lower()
        if name_part not in name_match_dict:
            name_match_dict[name_part] = []
        name_match_dict[name_part].append(user)
    
    # Process each participant once with O(1) lookups
    for participant in participants:
        participant_name = participant.get('name', '').strip()
        game_username = participant.get('game_username', '').strip()
        
        if not participant_name or participant_name.lower() in processed_participants:
            continue
            
        # Format for exact match: displayName#userId
        expected_full_username = f"{participant_name}#{participant.get('user_id', '')}"
        expected_full_username_lower = expected_full_username.lower()
        
        # Check for exact match with O(1) lookup
        if expected_full_username_lower in exact_match_dict:
            user = exact_match_dict[expected_full_username_lower]
            if user['user_id'] not in matched_discord_ids:
                logger.info(f"Found exact match: '{user.get('matcherino_username', '')}' matches with '{expected_full_username}'")
                exact_matches.append({
                    'participant': participant_name,
                    'participant_id': participant.get('user_id', ''),
                    'discord_username': user['username'],
                    'discord_id': user['user_id'],
                    'matcherino_id': participant.get('user_id', ''),
                    'game_username': game_username,
                    'db_matcherino_username': user.get('matcherino_username', '')
                })
                matched_discord_ids.add(user['user_id'])
                processed_participants.add(participant_name.lower())
                continue
        
        # If no exact match, try name-only match with O(1) lookup
        name_only = participant_name.split('#')[0].strip().lower()
        potential_matches = name_match_dict.get(name_only, [])
        
        # Filter out already matched users
        potential_matches = [user for user in potential_matches if user['user_id'] not in matched_discord_ids]
        
        # Process potential matches
        if len(potential_matches) == 1:
            # Single name match found
            match = potential_matches[0]
            name_only_matches.append({
                'participant': participant_name,
                'participant_tag': game_username,
                'discord_username': match['username'],
                'discord_id': match['user_id'],
                'matcherino_id': participant.get('user_id', ''),
                'game_username': game_username,
                'db_matcherino_username': match.get('matcherino_username', '')
            })
            matched_discord_ids.add(match['user_id'])
            processed_participants.add(participant_name.lower())
        elif len(potential_matches) > 1:
            # Multiple potential matches - ambiguous
            ambiguous_matches.append({
                'participant': participant_name,
                'participant_tag': game_username,
                'potential_matches': [{
                    'discord_username': user['username'],
                    'discord_id': user['user_id'],
                    'matcherino_username': user.get('matcherino_username', '')
                } for user in potential_matches]
            })
            processed_participants.add(participant_name.lower())
    
    # Collect unmatched participants and users in a single pass
    unmatched_participants = [
        {
            'name': p.get('name', '').strip(),
            'matcherino_id': p.get('user_id', ''),
            'game_username': p.get('game_username', '')
        }
        for p in participants
        if p.get('name', '').strip() and p.get('name', '').strip().lower() not in processed_participants
    ]
    
    unmatched_db_users = [
        {
            'discord_username': user['username'],
            'discord_id': user['user_id'],
            'matcherino_username': user.get('matcherino_username', '')
        }
        for user in db_users
        if user['user_id'] not in matched_discord_ids
    ]
    
    return (
        exact_matches, 
        name_only_matches, 
        ambiguous_matches,
        unmatched_participants,
        unmatched_db_users
    )

async def generate_match_results_csv(
    exact_matches, 
    name_only_matches,
    ambiguous_matches,
    unmatched_participants,
    unmatched_db_users
):
    """
    Generate a CSV file with match results.
    
    Returns:
        discord.File: CSV file for Discord attachment
    """
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)
    
    # Write header
    writer.writerow(['Match Type', 'Matcherino Username', 'Discord Username', 'Discord ID', 
                    'Matcherino ID', 'Game Username', 'DB Matcherino Username'])
    
    # Write exact matches
    for match in exact_matches:
        writer.writerow([
            'Exact Match', 
            match['participant'], 
            match['discord_username'], 
            match['discord_id'],
            match['matcherino_id'],
            match['game_username'],
            match['db_matcherino_username']
        ])
    
    # Write name-only matches
    for match in name_only_matches:
        writer.writerow([
            'Name Match', 
            match['participant'], 
            match['discord_username'], 
            match['discord_id'],
            match['matcherino_id'],
            match['game_username'],
            match['db_matcherino_username']
        ])
    
    # Write ambiguous matches
    for match in ambiguous_matches:
        for potential in match['potential_matches']:
            writer.writerow([
                'Ambiguous', 
                match['participant'], 
                potential['discord_username'], 
                potential['discord_id'],
                '',
                match.get('participant_tag', ''),
                potential['matcherino_username']
            ])
    
    # Write unmatched participants
    for participant in unmatched_participants:
        writer.writerow([
            'Unmatched Matcherino', 
            participant['name'], 
            '', 
            '',
            participant['matcherino_id'],
            participant['game_username'],
            ''
        ])
            
    # Write unmatched DB users
    for user in unmatched_db_users:
        writer.writerow([
            'Unmatched DB', 
            '', 
            user['discord_username'], 
            user['discord_id'],
            '',
            '',
            user['matcherino_username']
        ])

    # Prepare the CSV file for downloading
    csv_buffer.seek(0)
    csv_bytes = csv_buffer.getvalue().encode('utf-8')
    return discord.File(io.BytesIO(csv_bytes), filename="matcherino_participant_matches.csv")

@bot.tree.command(
    name="match-free-agents", 
    description="Match free agents from Matcherino with Discord users",
    guild=discord.Object(id=TARGET_GUILD_ID)
)
@app_commands.default_permissions(administrator=True)
async def match_free_agents_command(interaction: discord.Interaction):
    """Command to match Matcherino participants with Discord users using three-level matching approach."""
    if not TOURNAMENT_ID:
        await interaction.response.send_message("MATCHERINO_TOURNAMENT_ID is not set. Please set it in the .env file.", ephemeral=True)
        return
        
    await interaction.response.defer(ephemeral=True)
    
    try:
        logger.info("Starting free agent matching process")
        
        # Step 1: Get database users with their Matcherino usernames
        db_users = await db.get_all_matcherino_usernames()
        if not db_users:
            await interaction.followup.send("No users with Matcherino usernames found in database.", ephemeral=True)
            return
        
        logger.info(f"Found {len(db_users)} users with Matcherino usernames in database")
        
        # Step 2: Fetch all participants from Matcherino API
        async with MatcherinoScraper() as scraper:
            participants = await scraper.get_tournament_participants(TOURNAMENT_ID)
            
            if not participants:
                await interaction.followup.send("No participants found in the Matcherino tournament.", ephemeral=True)
                return
                
            logger.info(f"Found {len(participants)} participants from Matcherino")
        
        # Step 3: Match participants with database users
        (exact_matches, name_only_matches, ambiguous_matches,
         unmatched_participants, unmatched_db_users) = await match_participants_with_db_users(
             participants, db_users
        )
        
        logger.info(f"Found {len(exact_matches)} exact matches and {len(name_only_matches)} name-only matches")
        logger.info(f"Found {len(ambiguous_matches)} ambiguous matches")
        logger.info(f"{len(unmatched_participants)} participants remain unmatched")
        logger.info(f"{len(unmatched_db_users)} registered users were not found on Matcherino")
        
        # Step 4: Prepare and send the matching results report
        total_matched = len(exact_matches) + len(name_only_matches)
        embed = discord.Embed(
            title="Free Agent Matching Results",
            description=f"Matched {total_matched} out of {len(participants)} participants",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.utcnow()
        )
        
        # Add summary statistics
        embed.add_field(
            name="Summary",
            value=f"""
• **{len(exact_matches)}** exact username matches (with tag)
• **{len(name_only_matches)}** name-only matches (without tag)
• **{len(ambiguous_matches)}** ambiguous matches (need manual review)
• **{len(unmatched_participants)}** unmatched participants
• **{len(unmatched_db_users)}** unmatched database users
            """,
            inline=False
        )
        
        # Generate CSV report file
        csv_file = await generate_match_results_csv(
            exact_matches, name_only_matches, ambiguous_matches,
            unmatched_participants, unmatched_db_users
        )
        
        await interaction.followup.send(embed=embed, file=csv_file, ephemeral=True)
        
    except Exception as e:
        logger.error(f"Error matching free agents: {e}", exc_info=True)
        await interaction.followup.send(f"An error occurred while matching free agents: {str(e)}", ephemeral=True)

@bot.tree.command(
    name="close-signups", 
    description="Admin command to toggle whether new signups are allowed", 
    guild=discord.Object(id=TARGET_GUILD_ID)
)
@app_commands.default_permissions(administrator=True)
async def close_signups_command(interaction: discord.Interaction):
    """Admin command to toggle whether new signups are allowed.
    When signups are closed, existing users can still update their Matcherino usernames."""
    try:
        # Toggle the signups status
        from db import SIGNUPS_OPEN
        import db as db_module
        
        # Toggle the value
        db_module.SIGNUPS_OPEN = not SIGNUPS_OPEN
        
        if SIGNUPS_OPEN:
            status_message = "Signups are now **CLOSED**. New users cannot register, but existing users can still update their Matcherino usernames."
            logger.info(f"Admin {interaction.user.name} ({interaction.user.id}) closed tournament signups")
        else:
            status_message = "Signups are now **OPEN**. New users can register for the tournament."
            logger.info(f"Admin {interaction.user.name} ({interaction.user.id}) opened tournament signups")
        
        await interaction.response.send_message(
            f"{status_message}\n\nCurrent status: **{'OPEN' if db_module.SIGNUPS_OPEN else 'CLOSED'}**", 
            ephemeral=True
        )
            
    except Exception as e:
        logger.error(f"Error in close-signups command: {e}", exc_info=True)
        await interaction.response.send_message("An error occurred while toggling signup status.", ephemeral=True)




@bot.tree.command(
    name="send-username-reminders", 
    description="Send reminders to all users with improperly formatted Matcherino usernames",
    guild=discord.Object(id=TARGET_GUILD_ID)
)
@app_commands.default_permissions(administrator=True)
async def send_username_reminders_command(interaction: discord.Interaction, confirm: bool = False, batch_size: int = 20, delay_seconds: float = 0.5):
    """
    Admin command to send reminders to users with improperly formatted Matcherino usernames.
    
    Args:
        confirm (bool): Set to True to confirm sending multiple DMs
        batch_size (int): Number of users to process in each batch
        delay_seconds (float): Delay between each DM to avoid rate limits
    """
    if not TOURNAMENT_ID:
        await interaction.response.send_message("MATCHERINO_TOURNAMENT_ID is not set. Please set it in the .env file.", ephemeral=True)
        return
        
    await interaction.response.defer(ephemeral=True)
    
    try:
        # Check for confirmation to prevent accidental mass DM
        if not confirm:
            await interaction.followup.send(
                "⚠️ **Warning**: This command will send DMs to all users who have incorrectly formatted Matcherino usernames. "
                "To confirm, run this command again with `confirm` set to `True`.\n\n"
                "You can also specify `batch_size` (default: 20) and `delay_seconds` (default: 0.5) parameters for rate limiting.",
                ephemeral=True
            )
            return
        
        logger.info(f"Starting username format reminder process with batch_size={batch_size}, delay_seconds={delay_seconds}")
        
        # Get all users with their Matcherino usernames
        try:
            db_users = await db.get_all_matcherino_usernames()
            if not db_users:
                await interaction.followup.send("No users with Matcherino usernames found in database.", ephemeral=True)
                return
            
            logger.info(f"Found {len(db_users)} users with Matcherino usernames in database")
        except Exception as e:
            logger.error(f"Error retrieving users from database: {e}", exc_info=True)
            await interaction.followup.send(
                f"Error retrieving users from database: {str(e)}",
                ephemeral=True
            )
            return
        
        # Fetch Matcherino participants to get correct userId format
        try:
            async with MatcherinoScraper() as scraper:
                participants = await scraper.get_tournament_participants(TOURNAMENT_ID)
                
                if not participants:
                    await interaction.followup.send("No participants found in the Matcherino tournament.", ephemeral=True)
                    return
                    
                logger.info(f"Found {len(participants)} participants from Matcherino")
        except Exception as e:
            logger.error(f"Error fetching participants from Matcherino: {e}", exc_info=True)
            await interaction.followup.send(
                f"Error fetching participants from Matcherino: {str(e)}",
                ephemeral=True
            )
            return
        
        # Create participant lookup dictionaries
        participant_by_name = {}
        for p in participants:
            name = p.get('name', '').strip().lower()
            if name:
                participant_by_name[name] = p
                
        # Track users who need reminders
        users_needing_reminders = []
        
        # Check each user's Matcherino username format
        for user in db_users:
            matcherino_username = user.get('matcherino_username', '').strip()
            user_id = user.get('user_id')
            discord_username = user.get('username', '')
            
            if not matcherino_username:
                continue
                
            # Check if username has proper format (has userId tag)
            has_tag = '#' in matcherino_username
            base_name = matcherino_username.split('#')[0].strip().lower()
            
            # Try to find matching participant
            participant = participant_by_name.get(base_name)
            
            # If no tag or doesn't match expected format, add to reminder list
            if not has_tag or (participant and not matcherino_username.lower().endswith(f"#{participant['user_id']}".lower())):
                users_needing_reminders.append({
                    'user': user,
                    'participant': participant,
                    'base_name': base_name,
                    'status': 'pending'  # Track status for backup purposes
                })
                logger.info(f"User {discord_username} (ID: {user_id}) needs reminder - current format: {matcherino_username}")
        
        # Report how many users need reminders
        if not users_needing_reminders:
            await interaction.followup.send("No users with improperly formatted Matcherino usernames found. All usernames appear to be correct.", ephemeral=True)
            return
        
        logger.info(f"Found {len(users_needing_reminders)} users with improperly formatted Matcherino usernames")
        
        # Create a backup CSV with all users who need reminders
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"username_reminders_{timestamp}.csv"
        
        # Create backup CSV
        with open(backup_filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['discord_id', 'discord_username', 'matcherino_username', 'suggested_format', 'status']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for entry in users_needing_reminders:
                user = entry['user']
                participant = entry['participant']
                
                if participant:
                    suggested_format = f"{participant['name']}#{participant['user_id']}"
                else:
                    suggested_format = f"{user.get('matcherino_username', '').strip()}#userId"
                    
                writer.writerow({
                    'discord_id': user.get('user_id', ''),
                    'discord_username': user.get('username', ''),
                    'matcherino_username': user.get('matcherino_username', '').strip(),
                    'suggested_format': suggested_format,
                    'status': 'pending'
                })
                
        logger.info(f"Created backup file with {len(users_needing_reminders)} entries: {backup_filename}")
        
        # Send initial status update that won't be edited later
        try:
            await interaction.followup.send(
                f"Starting to process {len(users_needing_reminders)} users in batches of {batch_size}.\n"
                f"📋 Created backup file: `{backup_filename}`\n⏳ Processing reminders...\n\n"
                "I'll send a final report when complete. This may take several minutes.",
                ephemeral=True
            )
        except discord.HTTPException as e:
            logger.error(f"Error sending initial status update: {e}")
            # Continue processing anyway
        
        # Create a message directly in the channel for status updates
        status_channel = interaction.channel
        status_message = None
        
        # Track results
        success_count = 0
        failed_count = 0
        failed_users = []
        
        # Process users in batches
        total_users = len(users_needing_reminders)
        total_batches = (total_users + batch_size - 1) // batch_size  # Ceiling division
        
        for batch_index in range(total_batches):
            batch_start = batch_index * batch_size
            batch_end = min(batch_start + batch_size, total_users)
            current_batch = users_needing_reminders[batch_start:batch_end]
            
            logger.info(f"Processing batch {batch_index + 1}/{total_batches} ({len(current_batch)} users)")
            
            # Update status message periodically
            if batch_index > 0 and batch_index % 2 == 0:  # Update every 2 batches to reduce API calls
                progress = (batch_start / total_users) * 100
                progress_embed = discord.Embed(
                    title="Username Reminder Progress",
                    description=f"Processing batch {batch_index + 1}/{total_batches}",
                    color=discord.Color.blue(),
                    timestamp=datetime.datetime.utcnow()
                )
                
                progress_embed.add_field(
                    name="Status",
                    value=f"✅ Completed: {batch_start}/{total_users} ({progress:.1f}%)\n"
                          f"📊 Success: {success_count}, Failed: {failed_count}",
                    inline=False
                )
                
                # Create or update status message
                try:
                    if status_message is None and status_channel:
                        status_message = await status_channel.send(
                            content=f"Status update for {interaction.user.mention}'s username reminder command:",
                            embed=progress_embed
                        )
                    elif status_message:
                        await status_message.edit(embed=progress_embed)
                except Exception as e:
                    logger.error(f"Error updating status message: {e}")
                    # Continue processing even if status updates fail
            
            # Process each user in current batch
            for entry in current_batch:
                user = entry['user']
                participant = entry['participant']
                base_name = entry['base_name']
                
                user_id = user['user_id']
                discord_username = user['username']
                matcherino_username = user.get('matcherino_username', '').strip()
                
                # Create proper format suggestion based on participant data
                if participant:
                    proper_format = f"{participant['name']}#{participant['user_id']}"
                    id_info_message = "We've found what we believe is your Matcherino user ID, but please verify that this matches your account and update it accordingly. \n\n 1. Navigate to your profile (top right) \n 2. Copy your entire username to your clipboard."
                else:
                    # If no participant found, just suggest adding a generic tag
                    proper_format = f"{matcherino_username}#userId"
                    id_info_message = "We couldn't automatically find your Matcherino user ID. Please follow these instructions to locate it: \n\n 1. Navigate to your profile (top right) \n 2. Copy your entire username to your clipboard."
                
                try:
                    # Get discord user
                    discord_user = await bot.fetch_user(user_id)
                    
                    if not discord_user:
                        logger.warning(f"Could not find Discord user with ID {user_id}")
                        failed_count += 1
                        failed_users.append(f"{discord_username} (ID: {user_id}) - User not found")
                        entry['status'] = 'failed - user not found'
                        continue
                        
                    # Create and send the DM
                    dm_embed = discord.Embed(
                        title="Matcherino Username Format Update Required",
                        description=f"Hello! We noticed your Matcherino username format needs to be updated for proper matching in our tournament system.",
                        color=discord.Color.blue()
                    )
                    
                    # Add warning message at the top
                    dm_embed.add_field(
                        name="⚠️ IMPORTANT WARNING ⚠️",
                        value="**❗ Users with improperly formatted usernames will be automatically UNREGISTERED from both Discord and Matcherino systems ❗**\n\n🚫 This will PREVENT your participation in the tournament\n\n⏰ Please update your username format IMMEDIATELY to avoid removal\n ‼️ You will be automatically disqualified <t:1743613200:R> if you don't update your username! ‼️",
                        inline=False
                    )
                    
                    dm_embed.add_field(
                        name="Your current Matcherino username",
                        value=f"`{matcherino_username}`",
                        inline=False
                    )
                    
                    dm_embed.add_field(
                        name="Please update to this format",
                        value=f"`{proper_format}`",
                        inline=False
                    )
                    
                    # Add different messages based on whether we found their ID
                    dm_embed.add_field(
                        name="Verify your user ID" if participant else "Find your user ID",
                        value=id_info_message,
                        inline=False
                    )
                    
                    dm_embed.add_field(
                        name="How to update",
                        value=f"Use the `/register` command with your corrected username:\n`/register {proper_format}`\nRemember: You are supposed to edit your matcherino username on discord, not on matcherino.com!",
                        inline=False
                    )
                    
                    # Add footer with disclaimer
                    dm_embed.set_footer(text="This message was sent from Secondbest Server as you registered for the tournament.")
                    
                    await discord_user.send(embed=dm_embed)
                    success_count += 1
                    entry['status'] = 'success'
                    logger.info(f"Sent username reminder to {discord_username} (ID: {user_id})")
                        
                    # Add delay to avoid rate limiting
                    await asyncio.sleep(delay_seconds)
                        
                except discord.Forbidden:
                    logger.warning(f"Cannot send DM to {discord_username} (ID: {user_id}) - they may have DMs closed")
                    failed_count += 1
                    failed_users.append(f"{discord_username} (ID: {user_id}) - DMs closed")
                    entry['status'] = 'failed - DMs closed'
                    
                except Exception as e:
                    logger.error(f"Error sending DM to {discord_username} (ID: {user_id}): {e}")
                    failed_count += 1
                    failed_users.append(f"{discord_username} (ID: {user_id}) - Error: {str(e)}")
                    entry['status'] = f'failed - {str(e)}'
            
            # Update backup CSV after each batch to allow resuming if the process fails
            try:
                with open(backup_filename, 'w', newline='', encoding='utf-8') as csvfile:
                    fieldnames = ['discord_id', 'discord_username', 'matcherino_username', 'suggested_format', 'status']
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    
                    for entry in users_needing_reminders:
                        user = entry['user']
                        participant = entry['participant']
                        
                        if participant:
                            suggested_format = f"{participant['name']}#{participant['user_id']}"
                        else:
                            suggested_format = f"{user.get('matcherino_username', '').strip()}#userId"
                            
                        writer.writerow({
                            'discord_id': user.get('user_id', ''),
                            'discord_username': user.get('username', ''),
                            'matcherino_username': user.get('matcherino_username', '').strip(),
                            'suggested_format': suggested_format,
                            'status': entry.get('status', 'unknown')
                        })
                
                logger.info(f"Updated backup file after batch {batch_index+1}")
            except Exception as e:
                logger.error(f"Error updating backup file: {e}")
                # Continue processing even if backup file update fails
        
        # Create final result embed
        result_embed = discord.Embed(
            title="Username Reminder Results",
            description=f"Processed {len(users_needing_reminders)} users with improperly formatted usernames",
            color=discord.Color.green() if failed_count == 0 else discord.Color.orange(),
            timestamp=datetime.datetime.utcnow()
        )
        
        result_embed.add_field(
            name="Summary",
            value=f"✅ Successfully sent: **{success_count}** reminders\n❌ Failed to send: **{failed_count}** reminders",
            inline=False
        )
        
        # Add batch processing details
        result_embed.add_field(
            name="Processing Details",
            value=f"⏱️ Delay between messages: **{delay_seconds}s**\n"
                  f"📊 Batch size: **{batch_size}** users\n"
                  f"📋 Backup file: `{backup_filename}`",
            inline=False
        )
        
        # If there were failures, add them to the embed
        if failed_users:
            # Truncate the list if it's too long for Discord
            failure_text = "\n".join(failed_users[:10])
            if len(failed_users) > 10:
                failure_text += f"\n... and {len(failed_users) - 10} more"
                
            result_embed.add_field(
                name="Failed Reminders",
                value=failure_text,
                inline=False
            )
        
        # Send final results - Try interaction first, fall back to channel message
        try:
            await interaction.followup.send(embed=result_embed, ephemeral=True)
        except discord.HTTPException as e:
            # If the interaction token expired, send directly to the channel
            if status_channel:
                # Only send if we have a channel reference
                await status_channel.send(
                    content=f"Final results for {interaction.user.mention}'s username reminder command:",
                    embed=result_embed
                )
            logger.error(f"Could not send results via interaction followup: {e}")
        
        # Update any existing status message to show completion
        if status_message:
            try:
                await status_message.edit(
                    content=f"✅ **COMPLETED**: {interaction.user.mention}'s username reminder command finished!",
                    embed=result_embed
                )
            except Exception as e:
                logger.error(f"Error updating final status message: {e}")
        
    except Exception as e:
        logger.error(f"Error in send-username-reminders command: {e}", exc_info=True)
        
        # Try to send error message through followup first
        try:
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)
        except Exception as followup_error:
            # If that fails, try to send directly to the channel
            if interaction.channel:
                await interaction.channel.send(
                    f"{interaction.user.mention} An error occurred while processing username reminders: {str(e)}"
                )
            logger.error(f"Failed to send error message via followup: {followup_error}")

@bot.tree.command(
    name="continue-username-reminders", 
    description="Continue sending reminders from a previous backup file",
    guild=discord.Object(id=TARGET_GUILD_ID)
)
@app_commands.default_permissions(administrator=True)
async def continue_username_reminders_command(interaction: discord.Interaction, backup_filename: str, batch_size: int = 20, delay_seconds: float = 0.5):
    """
    Admin command to continue sending reminders to users from a previous backup file.
    
    Args:
        backup_filename: The name of the backup CSV file to resume from
        batch_size: Number of users to process in each batch
        delay_seconds: Delay between each DM to avoid rate limits
    """
    await interaction.response.defer(ephemeral=True)
    
    try:
        # Verify the backup file exists
        if not os.path.exists(backup_filename):
            await interaction.followup.send(
                f"❌ Backup file `{backup_filename}` not found. Please check the filename and try again.",
                ephemeral=True
            )
            return
        
        logger.info(f"Continuing username reminder process from backup: {backup_filename}")
        
        # Load users from the backup CSV
        users_to_process = []
        try:
            with open(backup_filename, 'r', newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    # Only process users that haven't been successful yet
                    if row['status'] != 'success':
                        users_to_process.append({
                            'user': {
                                'user_id': int(row['discord_id']),
                                'username': row['discord_username'],
                                'matcherino_username': row['matcherino_username']
                            },
                            'suggested_format': row['suggested_format'],
                            'status': row['status']
                        })
        except Exception as e:
            logger.error(f"Error reading backup file: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ Error reading backup file: {str(e)}",
                ephemeral=True
            )
            return
            
        if not users_to_process:
            await interaction.followup.send(
                "✅ No pending users found in the backup file. All users might have already been processed successfully.",
                ephemeral=True
            )
            return
            
        logger.info(f"Found {len(users_to_process)} users to process from backup file")
        
        # Send initial status update
        try:
            await interaction.followup.send(
                f"Continuing to process {len(users_to_process)} remaining users in batches of {batch_size}.\n"
                f"📋 Using backup file: `{backup_filename}`\n⏳ Processing reminders...\n\n"
                "I'll send a final report when complete. This may take several minutes.",
                ephemeral=True
            )
        except discord.HTTPException as e:
            logger.error(f"Error sending initial status update: {e}")
            # Continue processing anyway
            
        # Create a message directly in the channel for status updates
        status_channel = interaction.channel
        status_message = None
        
        # Track results
        success_count = 0
        failed_count = 0
        failed_users = []
        
        # Process users in batches
        total_users = len(users_to_process)
        total_batches = (total_users + batch_size - 1) // batch_size  # Ceiling division
        
        for batch_index in range(total_batches):
            batch_start = batch_index * batch_size
            batch_end = min(batch_start + batch_size, total_users)
            current_batch = users_to_process[batch_start:batch_end]
            
            logger.info(f"Processing batch {batch_index + 1}/{total_batches} ({len(current_batch)} users)")
            
            # Update status message periodically
            if batch_index > 0 and batch_index % 2 == 0:  # Update every 2 batches to reduce API calls
                progress = (batch_start / total_users) * 100
                progress_embed = discord.Embed(
                    title="Username Reminder Progress (Continuing)",
                    description=f"Processing batch {batch_index + 1}/{total_batches}",
                    color=discord.Color.blue(),
                    timestamp=datetime.datetime.utcnow()
                )
                
                progress_embed.add_field(
                    name="Status",
                    value=f"✅ Completed: {batch_start}/{total_users} ({progress:.1f}%)\n"
                          f"📊 Success: {success_count}, Failed: {failed_count}",
                    inline=False
                )
                
                # Create or update status message
                try:
                    if status_message is None and status_channel:
                        status_message = await status_channel.send(
                            content=f"Status update for {interaction.user.mention}'s username reminder continuation:",
                            embed=progress_embed
                        )
                    elif status_message:
                        await status_message.edit(embed=progress_embed)
                except Exception as e:
                    logger.error(f"Error updating status message: {e}")
                    # Continue processing even if status updates fail
            
            # Process each user in current batch
            for entry in current_batch:
                user = entry['user']
                suggested_format = entry['suggested_format']
                
                user_id = user['user_id']
                discord_username = user['username']
                matcherino_username = user.get('matcherino_username', '').strip()
                
                # Extract participant name from suggested format if possible
                name_parts = suggested_format.split('#')
                participant_name = name_parts[0] if len(name_parts) > 1 else matcherino_username
                has_user_id = len(name_parts) > 1 and name_parts[1] != 'userId'
                
                # Create message content based on whether we have a user ID
                if has_user_id:
                    id_info_message = "We've found what we believe is your Matcherino user ID, but please verify that this matches your account and update it accordingly. \n\n 1. Navigate to your profile (top right) \n 2. Copy your entire username to your clipboard."
                else:
                    id_info_message = "We couldn't automatically find your Matcherino user ID. Please follow these instructions to locate it: \n\n 1. Navigate to your profile (top right) \n 2. Copy your entire username to your clipboard."
                
                try:
                    # Get discord user
                    discord_user = await bot.fetch_user(user_id)
                    
                    if not discord_user:
                        logger.warning(f"Could not find Discord user with ID {user_id}")
                        failed_count += 1
                        failed_users.append(f"{discord_username} (ID: {user_id}) - User not found")
                        entry['status'] = 'failed - user not found'
                        continue
                        
                    # Create and send the DM
                    dm_embed = discord.Embed(
                        title="Matcherino Username Format Update Required",
                        description=f"Hello! We noticed your Matcherino username format needs to be updated for proper matching in our tournament system.",
                        color=discord.Color.blue()
                    )
                    
                    # Add warning message at the top
                    dm_embed.add_field(
                        name="⚠️ IMPORTANT WARNING ⚠️",
                        value="**❗ Users with improperly formatted usernames will be automatically UNREGISTERED from both Discord and Matcherino systems ❗**\n\n🚫 This will PREVENT your participation in the tournament\n\n⏰ Please update your username format IMMEDIATELY to avoid removal",
                        inline=False
                    )
                    
                    dm_embed.add_field(
                        name="Your current Matcherino username",
                        value=f"`{matcherino_username}`",
                        inline=False
                    )
                    
                    dm_embed.add_field(
                        name="Please update to this format",
                        value=f"`{suggested_format}`",
                        inline=False
                    )
                    
                    # Add different messages based on whether we found their ID
                    dm_embed.add_field(
                        name="Verify your user ID" if has_user_id else "Find your user ID",
                        value=id_info_message,
                        inline=False
                    )
                    
                    dm_embed.add_field(
                        name="How to update",
                        value=f"Use the `/register` command with your corrected username:\n`/register {suggested_format}`",
                        inline=False
                    )
                    
                    # Add footer with disclaimer
                    dm_embed.set_footer(text="This message was sent from Secondbest Server as you registered for the tournament.")
                    
                    await discord_user.send(embed=dm_embed)
                    success_count += 1
                    entry['status'] = 'success'
                    logger.info(f"Sent username reminder to {discord_username} (ID: {user_id})")
                        
                    # Add delay to avoid rate limiting
                    await asyncio.sleep(delay_seconds)
                        
                except discord.Forbidden:
                    logger.warning(f"Cannot send DM to {discord_username} (ID: {user_id}) - they may have DMs closed")
                    failed_count += 1
                    failed_users.append(f"{discord_username} (ID: {user_id}) - DMs closed")
                    entry['status'] = 'failed - DMs closed'
                    
                except Exception as e:
                    logger.error(f"Error sending DM to {discord_username} (ID: {user_id}): {e}")
                    failed_count += 1
                    failed_users.append(f"{discord_username} (ID: {user_id}) - Error: {str(e)}")
                    entry['status'] = f'failed - {str(e)}'
            
            # Update backup CSV after each batch
            try:
                # First read all existing entries
                all_entries = []
                with open(backup_filename, 'r', newline='', encoding='utf-8') as csvfile:
                    reader = csv.DictReader(csvfile)
                    all_entries = list(reader)
                    
                # Update status for entries that were processed
                for i, entry in enumerate(users_to_process[:batch_end]):
                    user = entry['user']
                    user_id = str(user['user_id'])
                    
                    # Find corresponding entry in original list
                    for original_entry in all_entries:
                        if original_entry['discord_id'] == user_id:
                            original_entry['status'] = entry['status']
                            break
                            
                # Write updated entries back to file
                with open(backup_filename, 'w', newline='', encoding='utf-8') as csvfile:
                    fieldnames = ['discord_id', 'discord_username', 'matcherino_username', 'suggested_format', 'status']
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(all_entries)
                    
                logger.info(f"Updated backup file after batch {batch_index+1}")
                
            except Exception as e:
                logger.error(f"Error updating backup file: {e}")
                # Continue processing even if backup update fails
        
        # Create final result embed
        result_embed = discord.Embed(
            title="Username Reminder Continuation Results",
            description=f"Processed {len(users_to_process)} remaining users from backup file",
            color=discord.Color.green() if failed_count == 0 else discord.Color.orange(),
            timestamp=datetime.datetime.utcnow()
        )
        
        result_embed.add_field(
            name="Summary",
            value=f"✅ Successfully sent: **{success_count}** reminders\n❌ Failed to send: **{failed_count}** reminders",
            inline=False
        )
        
        # Add batch processing details
        result_embed.add_field(
            name="Processing Details",
            value=f"⏱️ Delay between messages: **{delay_seconds}s**\n"
                  f"📊 Batch size: **{batch_size}** users\n"
                  f"📋 Backup file: `{backup_filename}`",
            inline=False
        )
        
        # If there were failures, add them to the embed
        if failed_users:
            # Truncate the list if it's too long for Discord
            failure_text = "\n".join(failed_users[:10])
            if len(failed_users) > 10:
                failure_text += f"\n... and {len(failed_users) - 10} more"
                
            result_embed.add_field(
                name="Failed Reminders",
                value=failure_text,
                inline=False
            )
        
        # Send final results - Try interaction first, fall back to channel message
        try:
            await interaction.followup.send(embed=result_embed, ephemeral=True)
        except discord.HTTPException as e:
            # If the interaction token expired, send directly to the channel
            if status_channel:
                # Only send if we have a channel reference
                await status_channel.send(
                    content=f"Final results for {interaction.user.mention}'s username reminder continuation:",
                    embed=result_embed
                )
            logger.error(f"Could not send results via interaction followup: {e}")
        
        # Update any existing status message to show completion
        if status_message:
            try:
                await status_message.edit(
                    content=f"✅ **COMPLETED**: {interaction.user.mention}'s username reminder continuation finished!",
                    embed=result_embed
                )
            except Exception as e:
                logger.error(f"Error updating final status message: {e}")
        
    except Exception as e:
        logger.error(f"Error in continue-username-reminders command: {e}", exc_info=True)
        
        # Try to send error message through followup first
        try:
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)
        except Exception as followup_error:
            # If that fails, try to send directly to the channel
            if interaction.channel:
                await interaction.channel.send(
                    f"{interaction.user.mention} An error occurred while continuing username reminders: {str(e)}"
                )
            logger.error(f"Failed to send error message via followup: {followup_error}")

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

# Execute the main function when the script is run directly
if __name__ == "__main__":
    asyncio.run(main())