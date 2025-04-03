import discord
from discord import app_commands
from discord.ext import commands
import logging

logger = logging.getLogger(__name__)

class RegistrationCog(commands.Cog):
    """Registration-related commands and functionality"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="register", description="Register for the tournament")
    @app_commands.describe(matcherino_username="Your Matcherino username (required for team assignment)")
    async def register(self, interaction: discord.Interaction, matcherino_username: str):
        """Slash command to register a user for the tournament."""
        try:
            user_id = interaction.user.id
            username = str(interaction.user)
            
            # Check if the user is banned
            is_banned = await self.bot.db.is_user_banned(user_id)
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
            is_registered = await self.bot.db.is_user_registered(user_id)
            
            # Register the user or get existing join code
            success, join_code = await self.bot.db.register_user(user_id, username, matcherino_username)
            
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

    @app_commands.command(name="mycode", description="Get the tournament join code")
    async def mycode(self, interaction: discord.Interaction):
        """Slash command to retrieve the tournament join code."""
        try:
            user_id = interaction.user.id
            
            # Check if user is banned
            is_banned = await self.bot.db.is_user_banned(user_id)
            if is_banned:
                await interaction.response.send_message(
                    "You are banned from participating in this tournament. Please contact an administrator for assistance.",
                    ephemeral=True
                )
                return
            
            # Check if the user is registered
            is_registered = await self.bot.db.is_user_registered(user_id)
            
            if not is_registered:
                await interaction.response.send_message(
                    "You are not registered for the tournament. Please use `/register` first to get the join code.", 
                    ephemeral=True
                )
                return
            
            # Get the tournament join code
            join_code = await self.bot.db.get_user_join_code(user_id)
            
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

    @app_commands.command(name="check-code", description="Admin command to check if a user is registered")
    @app_commands.default_permissions(administrator=True)
    async def check_code_slash(self, interaction: discord.Interaction, user: discord.User):
        """Slash command to check if a user is registered for the tournament."""
        try:
            # Get the user's registration info
            user_id = user.id
            username = str(user)
            
            # Check if the user is registered
            is_registered = await self.bot.db.is_user_registered(user_id)
            
            if not is_registered:
                await interaction.response.send_message(f"User {username} is not registered for the tournament.", ephemeral=True)
                return
                
            # The join code is the same for everyone
            join_code = self.bot.TOURNAMENT_JOIN_CODE
            
            await interaction.response.send_message(
                f"User: {username} (ID: {user_id})\nStatus: Registered\nThe tournament join code is: **`{join_code}`**", 
                ephemeral=True
            )
                
        except Exception as e:
            logger.error(f"Error in check-code command: {e}")
            await interaction.response.send_message("An error occurred while checking the user's registration status.", ephemeral=True)
    
    @app_commands.command(name="leave", description="Remove your own tournament registration")
    async def leave_command(self, interaction: discord.Interaction):
        """Command for users to unregister themselves from the tournament."""
        try:
            user_id = interaction.user.id
            username = str(interaction.user)
            
            # Check if the user is registered first
            is_registered = await self.bot.db.is_user_registered(user_id)
            
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
            success = await self.bot.db.unregister_user(user_id)
            
            if success:
                await interaction.response.send_message("You have been unregistered from the tournament.", ephemeral=True)
            else:
                await interaction.response.send_message("Failed to unregister you from the tournament. There might have been a database error.", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error in leave command: {e}")
            await interaction.response.send_message("An error occurred while unregistering you from the tournament.", ephemeral=True)
    
    @app_commands.command(name="verify-username", description="Check if your Matcherino username is properly formatted and matches with the site")
    async def verify_username_command(self, interaction: discord.Interaction):
        """Command to verify if a user's Matcherino username is properly formatted and found on Matcherino."""
        if not self.bot.TOURNAMENT_ID:
            await interaction.response.send_message("MATCHERINO_TOURNAMENT_ID is not set. Please contact an administrator for assistance.", ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        
        try:
            user_id = interaction.user.id
            discord_username = str(interaction.user)
            
            # Check if user is banned
            is_banned = await self.bot.db.is_user_banned(user_id)
            if is_banned:
                await interaction.followup.send(
                    "You are banned from participating in this tournament. Please contact an administrator for assistance.",
                    ephemeral=True
                )
                return
            
            # Check if the user is registered
            is_registered = await self.bot.db.is_user_registered(user_id)
            
            if not is_registered:
                await interaction.followup.send(
                    "You are not registered for the tournament. Please use `/register` first with your Matcherino username.",
                    ephemeral=True
                )
                return
                
            # Get user's registered Matcherino username
            matcherino_username = await self.bot.db.get_matcherino_username(user_id)
            
            if not matcherino_username:
                await interaction.followup.send(
                    "You don't have a Matcherino username set. Please use `/register` to set your Matcherino username.",
                    ephemeral=True
                )
                return
                
            logger.info(f"Verifying Matcherino username for {discord_username} (ID: {user_id}): {matcherino_username}")
            
            # Fetch participants from Matcherino
            from matcherino_scraper import MatcherinoScraper
            async with MatcherinoScraper() as scraper:
                participants = await scraper.get_tournament_participants(self.bot.TOURNAMENT_ID)
                
                if not participants:
                    await interaction.followup.send(
                        "No participants found in the Matcherino tournament. Please try again later or contact an administrator.",
                        ephemeral=True
                    )
                    return
                    
                logger.info(f"Found {len(participants)} participants from Matcherino")
            
            # Check for username match using similar logic as match-free-agents
            # Initialize variables to track match status
            exact_match = None
            name_only_matches = []
            
            # Extract the base name (without tag) from user's Matcherino username
            user_base_name = matcherino_username.split('#')[0].strip().lower()
            
            # Check if this is a properly formatted username with a # tag
            has_tag = '#' in matcherino_username
            
            # Scan participants for potential matches
            for participant in participants:
                participant_name = participant.get('name', '').strip()
                participant_id = participant.get('user_id', '')
                
                if not participant_name:
                    continue
                    
                # Check for exact match (not case sensitive)
                expected_full_username = f"{participant_name}#{participant_id}"
                if matcherino_username.lower() == expected_full_username.lower():
                    exact_match = participant
                    break
                    
                # Check for name-only match (without the tag)
                participant_base_name = participant_name.lower()
                if user_base_name == participant_base_name:
                    name_only_matches.append(participant)
            
            # Create response based on match results
            import datetime
            embed = discord.Embed(
                timestamp=datetime.datetime.utcnow()
            )
            
            embed.add_field(
                name="Your registered Matcherino username",
                value=f"`{matcherino_username}`",
                inline=False
            )
            
            if exact_match:
                # Perfect match - username and ID both match
                embed.title = "✅ Your username is correctly formatted!"
                embed.description = "Your Matcherino username is properly formatted and matches exactly with what's on the Matcherino site."
                embed.color = discord.Color.green()
                
                embed.add_field(
                    name="Match details",
                    value=f"Matched with participant: **{exact_match['name']}** (ID: {exact_match['user_id']})",
                    inline=False
                )
                
            elif name_only_matches:
                # Name matches but not the tag
                embed.title = "⚠️ Username format needs correction"
                embed.description = "Your username base name was found, but the format is incorrect. Please update your username to include your Matcherino user ID."
                embed.color = discord.Color.gold()
                
                # Suggest the correct format
                if len(name_only_matches) == 1:
                    # We have a single match, so we can confidently suggest the correct format
                    participant = name_only_matches[0]
                    suggested_format = f"{participant['name']}#{participant['user_id']}"
                    
                    embed.add_field(
                        name="Suggested correct format",
                        value=f"`{suggested_format}`",
                        inline=False
                    )
                    
                    embed.add_field(
                        name="How to update",
                        value=f"Use `/register {suggested_format}` to update your username",
                        inline=False
                    )
                else:
                    # Multiple potential matches, can't determine which one is correct
                    embed.add_field(
                        name="Multiple matches found",
                        value="Multiple participants with similar usernames were found. Please check your Matcherino account to find your exact user ID.",
                        inline=False
                    )
                    
                    # List potential matches
                    matches_text = "\n".join([f"• {p['name']} (ID: {p['user_id']})" for p in name_only_matches[:5]])
                    if len(name_only_matches) > 5:
                        matches_text += f"\n... and {len(name_only_matches) - 5} more"
                    
                    embed.add_field(
                        name="Potential matches",
                        value=matches_text,
                        inline=False
                    )
                    
                    embed.add_field(
                        name="How to update",
                        value="Use `/register YourUsername#YourUserID` with the correct user ID from the list above",
                        inline=False
                    )
            else:
                # No matches found
                embed.title = "❌ Username not found"
                embed.description = "Your Matcherino username was not found among the tournament participants."
                embed.color = discord.Color.red()
                
                embed.add_field(
                    name="Next steps",
                    value="Please check that:\n"
                          "1. You've spelled your username correctly\n"
                          "2. You've registered on the Matcherino tournament site\n"
                          "3. You've joined the tournament using the join code",
                    inline=False
                )
                
                embed.add_field(
                    name="How to update",
                    value="Use `/register YourCorrectUsername#yourID` to update your username",
                    inline=False
                )
            
            # Add help text footer
            embed.set_footer(text="If you need help, please contact a tournament administrator")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in verify-username command: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred while verifying your username: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="unregister", description="Admin command to unregister a user from the tournament")
    @app_commands.default_permissions(administrator=True)
    async def unregister_command(self, interaction: discord.Interaction, user: discord.User):
        """Admin command to unregister a user from the tournament."""
        try:
            user_id = user.id
            username = str(user)
            
            # Check if the user is registered first
            is_registered = await self.bot.db.is_user_registered(user_id)
            
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
            success = await self.bot.db.unregister_user(user_id)
            
            if success:
                await interaction.response.send_message(f"User {username} has been unregistered from the tournament.", ephemeral=True)
            else:
                await interaction.response.send_message(f"Failed to unregister user {username}. There might have been a database error.", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error in unregister command: {e}")
            await interaction.response.send_message("An error occurred while unregistering the user.", ephemeral=True)
    
    @app_commands.command(name="ban", description="Admin command to ban a user from registering for the tournament")
    @app_commands.default_permissions(administrator=True)
    async def ban_command(self, interaction: discord.Interaction, user: discord.User):
        """Admin command to ban a user from registering for the tournament."""
        try:
            user_id = user.id
            username = str(user)
            
            # Check if user is registered and unregister them first
            is_registered = await self.bot.db.is_user_registered(user_id)
            if is_registered:
                await self.bot.db.unregister_user(user_id)
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
            success = await self.bot.db.ban_user(user_id, username)
            
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
    
    @app_commands.command(name="unban", description="Admin command to unban a user from the tournament")
    @app_commands.default_permissions(administrator=True)
    async def unban_command(self, interaction: discord.Interaction, user: discord.User):
        """Admin command to unban a user from tournament registration."""
        try:
            user_id = user.id
            username = str(user)
            
            # Check if user is banned first
            is_banned = await self.bot.db.is_user_banned(user_id)
            
            if not is_banned:
                await interaction.response.send_message(f"User {username} is not banned from the tournament.", ephemeral=True)
                return
            
            # Unban the user
            success = await self.bot.db.unban_user(user_id)
            
            if success:
                await interaction.response.send_message(f"User {username} has been unbanned and can now register for the tournament.", ephemeral=True)
            else:
                await interaction.response.send_message(f"Failed to unban user {username}.", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error in unban command: {e}")
            await interaction.response.send_message("An error occurred while unbanning the user.", ephemeral=True)
    
    @app_commands.command(name="matcherino-username", description="Admin command to get a user's Matcherino username")
    @app_commands.default_permissions(administrator=True)
    async def matcherino_username_command(self, interaction: discord.Interaction, user: discord.User):
        """Admin command to get a user's Matcherino username."""
        try:
            user_id = user.id
            username = str(user)
            
            # Get the user's Matcherino username
            matcherino_username = await self.bot.db.get_matcherino_username(user_id)
            await interaction.response.send_message(
                f"User: {username} (ID: {user_id})\nMatcherino Username: **{matcherino_username}**",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error in matcherino-username command: {e}")
            await interaction.response.send_message("An error occurred while retrieving the user's Matcherino username.", ephemeral=True)
            return

async def setup(bot):
    await bot.add_cog(RegistrationCog(bot))