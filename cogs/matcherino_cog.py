import discord
from discord import app_commands
from discord.ext import commands
import logging
import io
import csv
import datetime
from matcherino_scraper import MatcherinoScraper

logger = logging.getLogger(__name__)

class MatcherinoCog(commands.Cog):
    """Matcherino API integration and participant matching functionality"""
    
    def __init__(self, bot):
        self.bot = bot
        self._remove_unmatched_users = {}  # Store users to remove per interaction ID
    
    @app_commands.command(name="match-free-agents", description="Match free agents from Matcherino with Discord users")
    @app_commands.default_permissions(administrator=True)
    async def match_free_agents_command(self, interaction: discord.Interaction):
        """Command to match Matcherino participants with Discord users using three-level matching approach."""
        if not self.bot.TOURNAMENT_ID:
            await interaction.response.send_message("MATCHERINO_TOURNAMENT_ID is not set. Please set it in the .env file.", ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        
        try:
            logger.info("Starting free agent matching process")
            
            # Step 1: Get database users with their Matcherino usernames
            db_users = await self.bot.db.get_all_matcherino_usernames()
            if not db_users:
                await interaction.followup.send("No users with Matcherino usernames found in database.", ephemeral=True)
                return
            
            logger.info(f"Found {len(db_users)} users with Matcherino usernames in database")
            
            # Step 2: Fetch all participants from Matcherino API
            async with MatcherinoScraper() as scraper:
                participants = await scraper.get_tournament_participants(self.bot.TOURNAMENT_ID)
                
                if not participants:
                    await interaction.followup.send("No participants found in the Matcherino tournament.", ephemeral=True)
                    return
                    
                logger.info(f"Found {len(participants)} participants from Matcherino")
            
            # Step 3: Match participants with database users
            (exact_matches, name_only_matches, ambiguous_matches,
             unmatched_participants, unmatched_db_users) = await self.match_participants_with_db_users(
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
            csv_file = await self.generate_match_results_csv(
                exact_matches, name_only_matches, ambiguous_matches,
                unmatched_participants, unmatched_db_users
            )
            
            await interaction.followup.send(embed=embed, file=csv_file, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error matching free agents: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred while matching free agents: {str(e)}", ephemeral=True)
    
    async def match_participants_with_db_users(self, participants, db_users):
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

        # Find our target user for debugging
        target_user = next((user for user in db_users if user.get('username') == '0cxld'), None)
        if target_user:
            logger.info("=== Target User Info ===")
            logger.info(f"Discord: {target_user.get('username')}")
            logger.info(f"Discord ID: {target_user.get('user_id')}")
            logger.info(f"Matcherino: {target_user.get('matcherino_username')}")
        
        logger.info(f"Starting matching process with {len(participants)} participants and {len(db_users)} database users")
        
        # Pre-process db_users into dictionaries for O(1) lookups
        # Dictionary mapping full lowercase matcherino username to user
        exact_match_dict = {}
        # Dictionary mapping lowercase name (without ID) to list of users
        name_match_dict = {}
        
        for user in db_users:
            matcherino_username = user.get('matcherino_username', '').strip().lower()
            if not matcherino_username:
                logger.warning(f"User {user.get('username')} has empty Matcherino username")
                continue
            
            # Extra logging for our target user
            if user.get('username') == '0cxld':
                logger.info("=== Processing Target User ===")
                logger.info(f"Original matcherino_username: {matcherino_username}")
            
            # Store full username for exact matches
            exact_match_dict[matcherino_username] = user
            
            # Store base name for name-only matches
            name_part = matcherino_username.split('#')[0].strip()
            if name_part not in name_match_dict:
                name_match_dict[name_part] = []
            name_match_dict[name_part].append(user)

            # More logging for target user
            if user.get('username') == '0cxld':
                logger.info(f"Stored in exact_match_dict with key: {matcherino_username}")
                logger.info(f"Stored in name_match_dict with key: {name_part}")
        
        logger.info(f"Built lookup dictionaries: {len(exact_match_dict)} exact usernames, {len(name_match_dict)} base names")
        
        # If we found our target user, check the dictionaries
        if target_user:
            target_matcherino = target_user.get('matcherino_username', '').lower()
            target_name_part = target_matcherino.split('#')[0].strip()
            logger.info("=== Checking Target User in Dictionaries ===")
            logger.info(f"Looking for exact match with: {target_matcherino}")
            logger.info(f"Looking for name match with: {target_name_part}")
            logger.info(f"Found in exact_match_dict: {target_matcherino in exact_match_dict}")
            logger.info(f"Found in name_match_dict: {target_name_part in name_match_dict}")
        
        # Process each participant once with O(1) lookups
        for participant in participants:
            participant_name = participant.get('name', '').strip().lower()
            game_username = participant.get('game_username', '').strip()
            
            if not participant_name:
                logger.warning("Found participant with empty name, skipping")
                continue
                
            if participant_name in processed_participants:
                logger.debug(f"Participant {participant_name} already processed, skipping")
                continue
                
            # Extra logging for participants that might match our target user
            if target_user:
                target_matcherino = target_user.get('matcherino_username', '').lower()
                target_name_part = target_matcherino.split('#')[0].strip()
                if (participant_name == target_matcherino):
                    logger.info("=== Found Potential Matching Participant ===")
                    logger.info(f"Participant name: {participant_name}")
                    logger.info(f"Game username: {game_username}")
                    logger.info(f"User ID: {participant.get('user_id', '')}")
            
            # Check for exact match with O(1) lookup using full username
            if participant_name in exact_match_dict:
                user = exact_match_dict[participant_name]
                if user['user_id'] not in matched_discord_ids:
                    # logger.info(f"Found exact match: '{user.get('matcherino_username', '')}' matches with '{participant_name}'")
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
                    processed_participants.add(participant_name)
                    continue
            
            # If no exact match, try name-only match
            name_part = participant_name.split('#')[0].strip()
            potential_matches = name_match_dict.get(name_part, [])
            
            # Filter out already matched users
            potential_matches = [user for user in potential_matches if user['user_id'] not in matched_discord_ids]
            
            # Add to appropriate match category
            if len(potential_matches) == 1:
                # Single name match found
                match = potential_matches[0]
                # logger.info(f"Found name-only match: '{match.get('matcherino_username', '')}' base name matches with '{participant_name}'")
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
                processed_participants.add(participant_name)
            elif len(potential_matches) > 1:
                # Multiple potential matches - ambiguous
                logger.info(f"Found ambiguous match: {participant_name} matches with multiple users")
                ambiguous_matches.append({
                    'participant': participant_name,
                    'participant_tag': game_username,
                    'potential_matches': [{
                        'discord_username': user['username'],
                        'discord_id': user['user_id'],
                        'matcherino_username': user.get('matcherino_username', '')
                    } for user in potential_matches]
                })
                processed_participants.add(participant_name)
        
        # After processing all participants, check if our target user was matched
        if target_user:
            target_id = target_user['user_id']
            logger.info("=== Final Match Status for Target User ===")
            logger.info(f"Target user matched: {target_id in matched_discord_ids}")
            if target_id in matched_discord_ids:
                if any(m['discord_id'] == target_id for m in exact_matches):
                    logger.info("Matched via exact match")
                elif any(m['discord_id'] == target_id for m in name_only_matches):
                    logger.info("Matched via name-only match")
            else:
                logger.info("User was not matched at all")
                logger.info("Checking processed participants...")
                target_matcherino = target_user.get('matcherino_username', '').lower()
                target_name_part = target_matcherino.split('#')[0].strip()
                logger.info(f"Target name processed: {target_matcherino in processed_participants}")
                logger.info(f"Target base name processed: {target_name_part in [p.split('#')[0].strip() for p in processed_participants]}")
        
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
        
        logger.info("=== Matching Results ===")
        logger.info(f"Exact matches: {len(exact_matches)}")
        logger.info(f"Name-only matches: {len(name_only_matches)}")
        logger.info(f"Ambiguous matches: {len(ambiguous_matches)}")
        logger.info(f"Unmatched participants: {len(unmatched_participants)}")
        logger.info(f"Unmatched DB users: {len(unmatched_db_users)}")
        logger.info(f"Total matched Discord IDs: {len(matched_discord_ids)}")
        
        return (
            exact_matches,
            name_only_matches,
            ambiguous_matches,
            unmatched_participants,
            unmatched_db_users
        )
    
    async def generate_match_results_csv(self, exact_matches, name_only_matches,
                                       ambiguous_matches, unmatched_participants, 
                                       unmatched_db_users):
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

    @app_commands.command(name="list-unmatched", description="List all unmatched Matcherino participants for cleanup")
    @app_commands.default_permissions(administrator=True)
    async def list_unmatched_command(self, interaction: discord.Interaction):
        """Admin command to list all Matcherino participants that aren't matched to Discord users."""
        if not self.bot.TOURNAMENT_ID:
            await interaction.response.send_message("MATCHERINO_TOURNAMENT_ID is not set. Please set it in the .env file.", ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        
        try:
            logger.info("Starting unmatched participant listing process")
            
            # Get all registered users with their Matcherino usernames
            db_users = await self.bot.db.get_all_matcherino_usernames()
            if not db_users:
                await interaction.followup.send("No users with Matcherino usernames found in database.", ephemeral=True)
                return
            
            # Fetch all participants from Matcherino
            async with MatcherinoScraper() as scraper:
                participants = await scraper.get_tournament_participants(self.bot.TOURNAMENT_ID)
                
                if not participants:
                    await interaction.followup.send("No participants found in the Matcherino tournament.", ephemeral=True)
                    return
            
            # Process participants to find unmatched ones
            (exact_matches, name_only_matches, ambiguous_matches,
             unmatched_participants, unmatched_db_users) = await self.match_participants_with_db_users(
                 participants, db_users
            )
            
            # Create a text file listing unmatched participants
            content = ["# Unmatched Matcherino Participants", ""]
            content.append("These participants are on Matcherino but not matched to any Discord user:\n")
            
            for participant in unmatched_participants:
                name = participant['name']
                matcherino_id = participant['matcherino_id']
                game_username = participant['game_username']
                
                line = f"- {name}"
                if matcherino_id:
                    line += f" (ID: {matcherino_id})"
                if game_username:
                    line += f" [Game: {game_username}]"
                content.append(line)
            
            content.append("\n# Ambiguous Matches")
            content.append("These participants have multiple potential Discord matches:\n")
            
            for match in ambiguous_matches:
                content.append(f"- {match['participant']}")
                if match.get('participant_tag'):
                    content.append(f"  Game username: {match['participant_tag']}")
                content.append("  Potential Discord matches:")
                for potential in match['potential_matches']:
                    content.append(f"  * Discord: {potential['discord_username']} (ID: {potential['discord_id']})")
                    if potential.get('matcherino_username'):
                        content.append(f"    Current Matcherino username: {potential['matcherino_username']}")
                content.append("")
            
            # Save as text file
            file_content = "\n".join(content)
            file = discord.File(
                io.BytesIO(file_content.encode('utf-8')),
                filename="unmatched_participants.txt"
            )
            
            # Send the file
            summary = f"Found {len(unmatched_participants)} unmatched participants and {len(ambiguous_matches)} ambiguous matches."
            await interaction.followup.send(summary, file=file, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error listing unmatched participants: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)

    @app_commands.command(name="remove-unmatched", description="Remove users from the registration database who aren't on Matcherino")
    @app_commands.default_permissions(administrator=True)
    async def remove_unmatched_command(self, interaction: discord.Interaction):
        """Remove users from the registration database who aren't found in the Matcherino tournament."""
        if not self.bot.TOURNAMENT_ID:
            await interaction.response.send_message("MATCHERINO_TOURNAMENT_ID is not set. Please set it in the .env file.", ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        
        try:
            logger.info("Starting unmatched user removal process")
            
            # Get all registered users with their Matcherino usernames
            db_users = await self.bot.db.get_all_matcherino_usernames()
            if not db_users:
                await interaction.followup.send("No users with Matcherino usernames found in database.", ephemeral=True)
                return
            
            # Fetch all participants from Matcherino
            async with MatcherinoScraper() as scraper:
                participants = await scraper.get_tournament_participants(self.bot.TOURNAMENT_ID)
                
                if not participants:
                    await interaction.followup.send("No participants found in the Matcherino tournament.", ephemeral=True)
                    return

            # Create sets for O(1) lookups
            matcherino_participants = {
                f"{p['name']}#{p['user_id']}".lower(): p 
                for p in participants 
                if p['name'] and p['user_id']
            }

            users_to_remove = []
            for user in db_users:
                matcherino_username = user.get('matcherino_username', '').strip().lower()
                if not matcherino_username:
                    continue
                
                if matcherino_username not in matcherino_participants:
                    users_to_remove.append(user)

            if not users_to_remove:
                await interaction.followup.send("No unmatched users found to remove.", ephemeral=True)
                return

            # Create preview file
            preview_content = ["Users that will be unregistered:", ""]
            for user in users_to_remove:
                preview_content.append(f"• {user['username']} (Discord ID: {user['user_id']}, Matcherino: {user['matcherino_username']})")

            preview_file = discord.File(
                io.BytesIO("\n".join(preview_content).encode("utf-8")),
                filename="users_to_remove.txt"
            )

            # Store users to remove for this interaction
            self._remove_unmatched_users[str(interaction.id)] = users_to_remove

            # Create confirm/cancel buttons
            confirm_button = discord.ui.Button(
                style=discord.ButtonStyle.danger,
                label=f"Confirm Remove ({len(users_to_remove)} users)",
                custom_id=f"remove_unmatched_confirm_{interaction.id}"
            )
            cancel_button = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="Cancel",
                custom_id=f"remove_unmatched_cancel_{interaction.id}"
            )

            view = discord.ui.View()
            view.add_item(confirm_button)
            view.add_item(cancel_button)

            await interaction.followup.send(
                f"Found {len(users_to_remove)} users to remove. Please review the attached file and confirm the action.",
                file=preview_file,
                view=view,
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error in remove-unmatched preview: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Handle button interactions for remove-unmatched command"""
        if not interaction.data or not isinstance(interaction.data, dict):
            return

        custom_id = interaction.data.get("custom_id", "")
        if not custom_id:
            return

        # Handle confirmation/cancellation
        if custom_id.startswith("remove_unmatched_"):
            await interaction.response.defer(ephemeral=True)
            original_interaction_id = custom_id.split("_")[-1]
            users_to_remove = self._remove_unmatched_users.get(original_interaction_id)

            if not users_to_remove:
                await interaction.followup.send("This confirmation has expired. Please run the command again.", ephemeral=True)
                return

            if custom_id.startswith("remove_unmatched_cancel_"):
                # Clean up stored data
                del self._remove_unmatched_users[original_interaction_id]
                await interaction.followup.send("Operation cancelled.", ephemeral=True)
                return

            if custom_id.startswith("remove_unmatched_confirm_"):
                try:
                    # Find the "Registered" role
                    guild = interaction.guild
                    registered_role = discord.utils.get(guild.roles, name="Registered")

                    # Remove unmatched users from database and remove their roles
                    roles_removed = 0
                    users_not_found = 0
                    role_errors = 0

                    for user in users_to_remove:
                        # Remove from database
                        await self.bot.db.unregister_user(user['user_id'])

                        # Remove the "Registered" role if it exists
                        if registered_role:
                            try:
                                member = await guild.fetch_member(user['user_id'])
                                if member and registered_role in member.roles:
                                    await member.remove_roles(registered_role)
                                    roles_removed += 1
                                    logger.info(f"Removed 'Registered' role from user {user['username']} ({user['user_id']})")
                            except discord.NotFound:
                                users_not_found += 1
                                logger.warning(f"User {user['username']} ({user['user_id']}) not found in guild")
                            except discord.Forbidden:
                                role_errors += 1
                                logger.error(f"Bot doesn't have permission to remove roles from {user['username']} ({user['user_id']})")
                            except Exception as e:
                                role_errors += 1
                                logger.error(f"Error removing role from {user['username']} ({user['user_id']}): {e}")

                    # Clean up stored data
                    del self._remove_unmatched_users[original_interaction_id]

                    # Create result message
                    status = []
                    status.append(f"Successfully removed {len(users_to_remove)} users from the registration database.")
                    if registered_role:
                        status.append(f"\nRole status:")
                        status.append(f"• Successfully removed 'Registered' role from {roles_removed} users")
                        if users_not_found > 0:
                            status.append(f"• {users_not_found} users were not found in the server")
                        if role_errors > 0:
                            status.append(f"• Failed to remove roles from {role_errors} users (see logs)")

                    await interaction.followup.send("\n".join(status), ephemeral=True)

                except Exception as e:
                    logger.error(f"Error removing unmatched users: {e}", exc_info=True)
                    await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)
                    # Clean up stored data even if there's an error
                    if original_interaction_id in self._remove_unmatched_users:
                        del self._remove_unmatched_users[original_interaction_id]

async def setup(bot):
    await bot.add_cog(MatcherinoCog(bot))