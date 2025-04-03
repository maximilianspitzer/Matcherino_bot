import discord
from discord import app_commands
from discord.ext import commands
import logging
import datetime
import asyncio

logger = logging.getLogger(__name__)

class TeamsCog(commands.Cog):
    """Team-related commands and functionality"""
    
    def __init__(self, bot):
        self.bot = bot
        self.voice_category_id = 1357422869528838236
    
    @app_commands.command(name="my-team", description="View your team and its members")
    async def my_team_command(self, interaction: discord.Interaction):
        """Command to view the user's team and its members."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            user_id = interaction.user.id
            
            # Check if user is banned
            is_banned = await self.bot.db.is_user_banned(user_id)
            if is_banned:
                await interaction.followup.send(
                    "You are banned from participating in this tournament. Please contact an administrator for assistance.",
                    ephemeral=True
                )
                return
            
            # Get the user's registered Matcherino username
            matcherino_username = await self.bot.db.get_matcherino_username(user_id)
            if not matcherino_username:
                await interaction.followup.send(
                    "You haven't registered your Matcherino username yet. Please use `/register <matcherino_username>` to set your username.",
                    ephemeral=True
                )
                return
                
            # Get user's team information
            team_info = await self.bot.db.get_user_team(user_id)
            
            if not team_info:
                await interaction.followup.send(
                    f"You are not currently assigned to any team. Your registered Matcherino username is **{matcherino_username}**.\n\n"
                    "Possible reasons:\n"
                    "1. You haven't joined a team on Matcherino yet\n"
                    "2. Your Matcherino username doesn't match what's in the database\n"
                    "3. Teams haven't been synced recently\n\n"
                    "Please verify your username with `/verify-username` or ask an admin to run `/sync-teams`.",
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
            
            # Add members to the embed with Discord mentions
            member_list = ""
            for member in team_info['members']:
                is_you = " (You)" if str(member.get('discord_user_id', "")) == str(user_id) else ""
                
                # Format the member info - use mention if discord_user_id exists
                if member.get('discord_user_id'):
                    discord_user = f" (<@{member['discord_user_id']}>)"
                elif member.get('discord_username'):
                    discord_user = f" (Discord: {member['discord_username']})"
                else:
                    discord_user = ""
                    
                member_list += f"• {member['member_name']}{discord_user}{is_you}\n"
                
            embed.add_field(
                name="Team Members",
                value=member_list if member_list else "No members found",
                inline=False
            )
            
            # Add footer with last sync time
            if 'last_updated' in team_info:
                embed.set_footer(text=f"Team data last updated: {team_info['last_updated'].strftime('%Y-%m-%d %H:%M:%S UTC')}")
                
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in my-team command: {e}")
            await interaction.followup.send(f"Error retrieving your team: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="user-team", description="Check which team a Discord user belongs to")
    async def user_team_command(self, interaction: discord.Interaction, user: discord.User):
        """Command to check which team a Discord user belongs to."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Check if the requesting user is banned
            requester_id = interaction.user.id
            is_banned = await self.bot.db.is_user_banned(requester_id)
            if is_banned:
                await interaction.followup.send(
                    "You are banned from participating in this tournament. Please contact an administrator for assistance.",
                    ephemeral=True
                )
                return
                
            team_info = await self.bot.db.get_user_team(user.id)
            
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
    
    @app_commands.command(name="sync-teams", description="Admin command to manually sync teams from Matcherino")
    @app_commands.default_permissions(administrator=True)
    async def sync_teams_command(self, interaction: discord.Interaction):
        """Admin command to manually trigger team synchronization from Matcherino."""
        if not self.bot.TOURNAMENT_ID:
            await interaction.response.send_message("MATCHERINO_TOURNAMENT_ID is not set. Please set it in the .env file.", ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        
        try:
            teams_data = await self.sync_matcherino_teams()
            
            if teams_data:
                await interaction.followup.send(f"Successfully synced {len(teams_data)} teams from Matcherino tournament.", ephemeral=True)
            else:
                await interaction.followup.send("No teams found in the tournament or sync failed.", ephemeral=True)
        
        except Exception as e:
            logger.error(f"Error in sync-teams command: {e}")
            await interaction.followup.send(f"Error syncing teams: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="debug-team-match", description="Debug team matching issues by showing how usernames are stored vs what's coming from the API")
    @app_commands.default_permissions(administrator=True)
    async def debug_team_match(self, interaction: discord.Interaction):
        """Admin command to debug team matching by showing current username mapping."""
        if not self.bot.TOURNAMENT_ID:
            await interaction.response.send_message("MATCHERINO_TOURNAMENT_ID is not set. Please set it in the .env file.", ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get all registered users with Matcherino usernames
            db_users = await self.bot.db.get_all_matcherino_usernames()
            
            if not db_users:
                await interaction.followup.send("No users with Matcherino usernames found in database.", ephemeral=True)
                return
                
            # Get participants from Matcherino
            from matcherino_scraper import MatcherinoScraper
            async with MatcherinoScraper() as scraper:
                # First get team data
                teams_data = await scraper.get_teams_data(self.bot.TOURNAMENT_ID)
                
                # Then get participant data
                participants = await scraper.get_tournament_participants(self.bot.TOURNAMENT_ID)
                
                if not teams_data and not participants:
                    await interaction.followup.send("No teams or participants found in the Matcherino tournament.", ephemeral=True)
                    return

            # Get the Matcherino cog to use its matching function
            matcherino_cog = self.bot.get_cog("MatcherinoCog")
            if not matcherino_cog:
                await interaction.followup.send("MatcherinoCog not found.", ephemeral=True)
                return

            # Use the same matching logic as match-free-agents
            (exact_matches, name_only_matches, ambiguous_matches,
             unmatched_participants, unmatched_db_users) = await matcherino_cog.match_participants_with_db_users(
                 participants, db_users
            )

            # Create embed with debugging information
            embed = discord.Embed(
                title="Team Matching Debug Info",
                description="Comparison of registered usernames vs API member names",
                color=discord.Color.blue()
            )
            
            # Add summary stats
            matched_users = exact_matches + name_only_matches
            embed.add_field(
                name="Summary",
                value=f"• **{len(db_users)}** users with Matcherino usernames in database\n"
                      f"• **{len(participants)}** participants from API\n"
                      f"• **{len(exact_matches)}** exact matches (with tag)\n"
                      f"• **{len(name_only_matches)}** name-only matches (without tag)\n"
                      f"• **{len(ambiguous_matches)}** ambiguous matches\n"
                      f"• **{len(unmatched_participants)}** unmatched participants\n"
                      f"• **{len(unmatched_db_users)}** unmatched database users",
                inline=False
            )
            
            # Add matched users (limited to avoid embed limits)
            if matched_users:
                matched_text = "\n".join([
                    f"• Discord: **{m['discord_username']}** → Matcherino: `{m['participant']}`" 
                    for m in (exact_matches + name_only_matches)[:10]
                ])
                if len(matched_users) > 10:
                    matched_text += f"\n... and {len(matched_users) - 10} more"
                    
                embed.add_field(
                    name=f"Matched Users ({len(matched_users)})",
                    value=matched_text,
                    inline=False
                )
                
            # Add unmatched users (limited to avoid embed limits)
            if unmatched_db_users:
                unmatched_text = "\n".join([
                    f"• Discord: **{u['discord_username']}** → Matcherino: `{u['matcherino_username']}`" 
                    for u in unmatched_db_users[:10]
                ])
                if len(unmatched_db_users) > 10:
                    unmatched_text += f"\n... and {len(unmatched_db_users) - 10} more"
                    
                embed.add_field(
                    name=f"Unmatched Users ({len(unmatched_db_users)})",
                    value=unmatched_text,
                    inline=False
                )
                
            # Add API participant names (limited to avoid embed limits)
            if unmatched_participants:
                api_text = "\n".join([f"• `{p['name']}`" for p in unmatched_participants[:15]])
                if len(unmatched_participants) > 15:
                    api_text += f"\n... and {len(unmatched_participants) - 15} more"
                    
                embed.add_field(
                    name=f"Unmatched Participants ({len(unmatched_participants)})",
                    value=api_text,
                    inline=False
                )
                
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in debug-team-match command: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)
    
    
    async def sync_matcherino_teams(self):
        """Fetch team data from Matcherino and sync it to the database."""
        if not self.bot.TOURNAMENT_ID:
            return
            
        try:
            # Fetch teams from Matcherino
            from matcherino_scraper import MatcherinoScraper
            async with MatcherinoScraper() as scraper:
                teams_data = await scraper.get_teams_data(self.bot.TOURNAMENT_ID)
                
                if not teams_data:
                    logger.warning("No teams found in the tournament. Nothing to sync.")
                    return
                
                logger.info(f"Found {len(teams_data)} teams with data to sync")
                
                # Update database with team data - this marks all teams as inactive first,
                # then marks the current teams as active
                await self.bot.db.update_matcherino_teams(teams_data)
                
                # Get all inactive teams (those no longer on Matcherino)
                inactive_teams = await self.bot.db.get_inactive_teams()
                    
                if inactive_teams:
                    logger.info(f"Found {len(inactive_teams)} teams that are no longer on Matcherino")
                    
                    # Delete all inactive teams
                    removed_count = 0
                    for team in inactive_teams:
                        team_id = team['team_id']
                        team_name = team['team_name']
                        logger.info(f"Removing inactive team: {team_name} (ID: {team_id})")
                        
                        # Use the Database.remove_team method to delete the team
                        success = await self.bot.db.remove_team(team_id)
                        if success:
                            removed_count += 1
                    
                    logger.info(f"Successfully removed {removed_count} inactive teams")
                
                logger.info(f"Team sync completed successfully - updated {len(teams_data)} teams")
                return teams_data
                
        except Exception as e:
            logger.error(f"Error during team sync: {e}")
            raise

    async def create_or_get_next_category(self, guild: discord.Guild, base_category: discord.CategoryChannel, category_number: int = 1) -> discord.CategoryChannel:
        """Create a new category or get an existing one with proper sequential numbering."""
        category_name = f"Team Channels #{category_number}"
        
        # First try to find an existing category
        category = discord.utils.get(guild.categories, name=category_name)
        if category:
            # If the category has less than 50 channels, return it
            if len(category.channels) < 50:
                return category
            # If it's full, recursively try the next number
            return await self.create_or_get_next_category(guild, base_category, category_number + 1)
            
        # Create new category with same permissions as base category
        return await guild.create_category(
            name=category_name,
            position=base_category.position + category_number,
            overwrites=base_category.overwrites
        )

    @app_commands.command(name="create-team-voice", description="Create private voice channels for all teams")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.cooldown(rate=1, per=300.0)  # Can only run once every 5 minutes
    async def create_team_voice_channels(self, interaction: discord.Interaction):
        """Admin command to create private voice channels for all teams."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            guild = interaction.guild
            base_category = guild.get_channel(self.voice_category_id)
            
            if not base_category:
                await interaction.followup.send(f"Could not find the base category with ID {self.voice_category_id}", ephemeral=True)
                return
                
            # Get all active teams using the correct method
            teams = await self.bot.db.get_matcherino_teams(active_only=True)
            if not teams:
                await interaction.followup.send("No active teams found.", ephemeral=True)
                return

            channels_created = 0
            categories_created = 1
            current_category = base_category

            for team in teams:
                # Check if current category is full (50 channels)
                if len(current_category.channels) >= 50:
                    # Get or create next category
                    categories_created += 1
                    await asyncio.sleep(2)  # Rate limit delay for category creation
                    current_category = await self.create_or_get_next_category(guild, base_category, categories_created)

                # Team members are already included in the team info
                team_members = [member for member in team['members'] if member.get('discord_user_id')]
                
                if not team_members:
                    continue

                # Create overwrites for the channel
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True)
                }
                
                # Get member objects and add overwrites
                discord_members = []
                for member in team_members:
                    discord_id = member['discord_user_id']
                    discord_member = guild.get_member(discord_id)
                    if discord_member:
                        discord_members.append(discord_member)
                        overwrites[discord_member] = discord.PermissionOverwrite(view_channel=True, connect=True, speak=True)

                if not discord_members:
                    continue

                # Create the voice channel
                channel_name = f"🎮 {team['team_name']}"
                try:
                    # Add delay between channel creations to avoid rate limits
                    # Discord rate limit is 30 channel operations per 5 minutes per guild
                    await asyncio.sleep(2)  # 2 second delay between channel creations
                    
                    channel = await guild.create_voice_channel(
                        name=channel_name,
                        category=current_category,
                        overwrites=overwrites
                    )
                    
                    # Add delay between sending messages to avoid rate limits
                    # Discord rate limit is 5 messages per 5 seconds per channel
                    await asyncio.sleep(1)  # 1 second delay before sending message
                    
                    # Send a notification message in the voice channel
                    mentions = " ".join(member.mention for member in discord_members)
                    await channel.send(
                        f"🎮 Welcome to your team voice channel! {mentions}\n"
                        "This is your private voice channel for team communication."
                    )
                    
                    channels_created += 1
                    
                    # If we've created 25 channels, take a longer break to avoid hitting guild-wide rate limits
                    if channels_created % 25 == 0:
                        await asyncio.sleep(5)  # 5 second break every 25 channels
                        
                except Exception as e:
                    logger.error(f"Error creating voice channel for team {team['team_name']}: {e}")
                    # If we hit a rate limit, take a longer break
                    if "rate limited" in str(e).lower():
                        await asyncio.sleep(10)  # 10 second break if rate limited
                    continue

            await interaction.followup.send(
                f"Created {channels_created} team voice channels across {categories_created} categories.",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error in create-team-voice command: {e}")
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Handle errors from application commands in this cog."""
        if isinstance(error, app_commands.CommandOnCooldown):
            minutes, seconds = divmod(error.retry_after, 60)
            await interaction.response.send_message(
                f"This command is on cooldown. Please try again in {int(minutes)} minutes and {int(seconds)} seconds.",
                ephemeral=True
            )
            return

async def setup(bot):
    await bot.add_cog(TeamsCog(bot))