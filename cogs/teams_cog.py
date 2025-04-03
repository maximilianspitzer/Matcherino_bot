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
    
    @app_commands.command(name="remove-unmatched", description="Remove users who have no matches at all (neither exact nor loose name matches)")
    @app_commands.default_permissions(administrator=True)
    async def remove_unmatched_command(self, interaction: discord.Interaction):
        """Remove users who have no matches at all in Matcherino"""
        if not self.bot.TOURNAMENT_ID:
            await interaction.response.send_message("MATCHERINO_TOURNAMENT_ID is not set.", ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        
        try:
            logger.info("Starting remove-unmatched command execution")
            
            # Get all registered users with their Matcherino usernames
            db_users = await self.bot.db.get_all_matcherino_usernames()
            if not db_users:
                await interaction.followup.send("No users with Matcherino usernames found in database.", ephemeral=True)
                return

            logger.info(f"Found {len(db_users)} users in database with Matcherino usernames")
            for user in db_users:
                logger.debug(f"DB User - Discord: {user.get('username')}, Matcherino: {user.get('matcherino_username', '')}")

            # Get participants from Matcherino
            from matcherino_scraper import MatcherinoScraper
            async with MatcherinoScraper() as scraper:
                participants = await scraper.get_tournament_participants(self.bot.TOURNAMENT_ID)
                if not participants:
                    await interaction.followup.send("No participants found in the Matcherino tournament.", ephemeral=True)
                    return

            logger.info(f"Found {len(participants)} participants in Matcherino tournament")
            for participant in participants:
                logger.debug(f"Participant - Name: {participant.get('name', '')}, ID: {participant.get('user_id', '')}")

            # Get the Matcherino cog to use its matching function
            matcherino_cog = self.bot.get_cog("MatcherinoCog")
            if not matcherino_cog:
                await interaction.followup.send("MatcherinoCog not found.", ephemeral=True)
                return

            logger.info("Starting participant matching process...")
            # Use the exact same matching logic as match-free-agents
            (exact_matches, name_only_matches, ambiguous_matches,
             unmatched_participants, unmatched_db_users) = await matcherino_cog.match_participants_with_db_users(
                 participants, db_users
            )

            # Track all matched Discord IDs (both exact and name-only matches)
            matched_discord_ids = {match["discord_id"] for match in exact_matches}
            matched_discord_ids.update(match["discord_id"] for match in name_only_matches)

            logger.info(f"Found {len(matched_discord_ids)} total matched Discord IDs")
            logger.debug("Matched Discord IDs: " + ", ".join(str(id) for id in matched_discord_ids))

            # Users to remove are ONLY those who have no matches at all
            users_to_remove = []
            for user in db_users:
                user_id = user["user_id"]
                if user_id not in matched_discord_ids:
                    logger.info(f"User {user.get('username')} (ID: {user_id}) will be removed - no matches found")
                    logger.debug(f"Their Matcherino username was: {user.get('matcherino_username', '')}")
                    users_to_remove.append(user_id)
                else:
                    logger.debug(f"User {user.get('username')} (ID: {user_id}) is matched, keeping")

            if not users_to_remove:
                logger.info("No users found to remove")
                await interaction.followup.send("No completely unmatched users found to remove.", ephemeral=True)
                return

            # Log what we're about to do
            description = "Removing users who have no matches at all"
            logger.info(f"{description}. Found {len(users_to_remove)} users to remove.")

            # Remove users from database and update roles
            removed_count = 0
            guild = interaction.guild
            for user_id in users_to_remove:
                logger.info(f"Processing removal of user {user_id}")
                
                # Remove from database
                db_result = await self.bot.db.unregister_user(user_id)
                if db_result:
                    logger.info(f"Successfully unregistered user {user_id} from database")
                else:
                    logger.warning(f"Failed to unregister user {user_id} from database")
                
                # Remove roles from Discord user
                try:
                    member = await guild.fetch_member(user_id)
                    if member:
                        roles_to_remove = [role for role in member.roles 
                                         if role.name.lower() in ["registered", "team member"]]
                        if roles_to_remove:
                            role_names = [role.name for role in roles_to_remove]
                            logger.info(f"Removing roles {role_names} from user {member.name} ({user_id})")
                            await member.remove_roles(*roles_to_remove)
                            logger.info(f"Successfully removed roles from user {member.name} ({user_id})")
                        else:
                            logger.info(f"User {member.name} ({user_id}) had no roles to remove")
                    removed_count += 1
                except discord.NotFound:
                    logger.warning(f"User {user_id} not found in guild")
                except Exception as e:
                    logger.error(f"Error removing roles from user {user_id}: {e}")

            logger.info(f"Removal process complete. Removed {removed_count} out of {len(users_to_remove)} users")
            
            # Create detailed report of what happened
            report = [
                f"{description}",
                f"Total database users: {len(db_users)}",
                f"Total Matcherino participants: {len(participants)}",
                f"Exact matches found: {len(exact_matches)}",
                f"Name-only matches found: {len(name_only_matches)}",
                f"Users targeted for removal: {len(users_to_remove)}",
                f"Successfully removed: {removed_count}"
            ]
            
            await interaction.followup.send(
                "\n".join(report), 
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error in remove-unmatched command: {e}", exc_info=True)
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

async def setup(bot):
    await bot.add_cog(TeamsCog(bot))