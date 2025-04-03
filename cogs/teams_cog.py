import discord
from discord import app_commands
from discord.ext import commands
import logging
import datetime

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

    @app_commands.command(name="create-team-voice", description="Create private voice channels for all teams")
    @app_commands.default_permissions(administrator=True)
    async def create_team_voice_channels(self, interaction: discord.Interaction):
        """Admin command to create private voice channels for all teams."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            guild = interaction.guild
            category = guild.get_channel(self.voice_category_id)
            
            if not category:
                await interaction.followup.send(f"Could not find the category with ID {self.voice_category_id}", ephemeral=True)
                return
                
            # Get all active teams
            teams = await self.bot.db.get_active_teams()
            if not teams:
                await interaction.followup.send("No active teams found.", ephemeral=True)
                return

            channels_created = 0
            for team in teams:
                # Get team members' Discord IDs
                team_info = await self.bot.db.get_team_members(team['team_id'])
                member_ids = [int(member['discord_user_id']) for member in team_info['members'] if member.get('discord_user_id')]
                
                if not member_ids:
                    continue

                # Create overwrites for the channel
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True)
                }
                
                # Add overwrites for each team member
                for member_id in member_ids:
                    member = guild.get_member(member_id)
                    if member:
                        overwrites[member] = discord.PermissionOverwrite(view_channel=True, connect=True, speak=True)

                # Create the voice channel
                channel_name = f"🎮 {team['team_name']}"
                try:
                    await guild.create_voice_channel(
                        name=channel_name,
                        category=category,
                        overwrites=overwrites
                    )
                    channels_created += 1
                except Exception as e:
                    logger.error(f"Error creating voice channel for team {team['team_name']}: {e}")
                    continue

            await interaction.followup.send(
                f"Created {channels_created} team voice channels in category '{category.name}'.",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error in create-team-voice command: {e}")
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(TeamsCog(bot))