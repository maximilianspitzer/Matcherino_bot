import discord
from discord import app_commands
from discord.ext import commands
import logging
import asyncio

logger = logging.getLogger(__name__)

class AdminCog(commands.Cog):
    """Admin-related commands and functionality"""
    
    def __init__(self, bot):
        self.bot = bot
        
    @commands.command(name="sync")
    async def sync_legacy(self, ctx):
        """Legacy command to sync slash commands to the guild (admin only)."""
        # Silent ignore if user doesn't have admin permissions
        if not ctx.author.guild_permissions.administrator:
            return
        
        # Log who used the command for auditing
        logger.info(f"Sync command used by admin {ctx.author.name} (ID: {ctx.author.id})")
        
        # Send initial message
        message = await ctx.reply("Syncing slash commands to this server... This may take a moment.")
        
        # Perform sync
        success, result = await self.bot.sync_commands()
        
        # Update message with result
        if success:
            await message.edit(content=f"✅ {result}")
        else:
            await message.edit(content=f"❌ Command sync failed: {result}")
    
    @app_commands.command(name="resync", description="Admin command to resync slash commands for this server")
    @app_commands.default_permissions(administrator=True)
    async def resync_slash(self, interaction: discord.Interaction):
        """Slash command to resync slash commands with improved error handling."""
        try:
            await interaction.response.send_message("Resyncing slash commands... This may take a moment.", ephemeral=True)
            
            # Use the dedicated sync function for consistency
            success, result = await self.bot.sync_commands()
            
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
    
    @app_commands.command(name="export", description="Admin command to export all registered users to a CSV file")
    @app_commands.default_permissions(administrator=True)
    async def export_slash(self, interaction: discord.Interaction):
        """Slash command to export all registered users."""
        try:
            # Defer the response since this might take some time
            await interaction.response.defer(ephemeral=True)
                
            # Get all registered users who are not banned
            registered_users = await self.bot.db.get_registered_users()
            active_users = [user for user in registered_users if not user['banned']]
            
            if not active_users:
                await interaction.followup.send("No users are currently registered for the tournament.", ephemeral=True)
                return
                
            # Create a CSV file in memory
            import io
            import csv
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
    
    @app_commands.command(name="help", description="Show available commands")
    async def help_slash(self, interaction: discord.Interaction):
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
            value="Check if your Matcherino username is properly formatted and matches with the site",
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
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="ping", description="Check bot latency")
    async def ping_slash(self, interaction: discord.Interaction):
        """Responds with the bot's latency."""
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"Pong! Latency: {latency}ms", ephemeral=True)
    
    @commands.command(name="job")
    @commands.cooldown(1, 20, commands.BucketType.default)  # Global cooldown of 20 seconds
    async def job(self, ctx):
        """Command to send a specific link and delete the invocation."""
        try:
            # Check if user has admin permissions
            if not ctx.author.guild_permissions.administrator:
                return  # Silently ignore if user doesn't have admin permissions
            
            # Send the link
            await ctx.send("https://media.discordapp.net/attachments/1118988563577577574/1150888584778371153/YiEtFVn.gif")
        except Exception as e:
            logger.error(f"Error in job command: {e}")
    
    @app_commands.command(name="close-signups", description="Admin command to toggle whether new signups are allowed")
    @app_commands.default_permissions(administrator=True)
    async def close_signups_command(self, interaction: discord.Interaction):
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

    @app_commands.command(name="verify-roles", description="Verify and restore 'Registered' role for all registered users")
    @app_commands.default_permissions(administrator=True)
    async def verify_roles_command(self, interaction: discord.Interaction):
        """Admin command to verify and restore the 'Registered' role for all users who are registered in the database."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get all registered users from database
            registered_users = await self.bot.db.get_registered_users()
            
            if not registered_users:
                await interaction.followup.send("No users are currently registered in the database.", ephemeral=True)
                return
            
            # Find the "Registered" role
            guild = interaction.guild
            registered_role = discord.utils.get(guild.roles, name="Registered")
            
            if not registered_role:
                await interaction.followup.send("Could not find the 'Registered' role in this server.", ephemeral=True)
                return
            
            # Track statistics
            total_users = len(registered_users)
            users_fixed = 0
            users_already_correct = 0
            users_not_found = 0
            errors = 0
            
            # Process each registered user
            for user in registered_users:
                try:
                    # Skip banned users
                    if user.get('banned', False):
                        continue
                        
                    user_id = user['user_id']
                    member = guild.get_member(user_id)
                    
                    if member is None:
                        users_not_found += 1
                        logger.warning(f"User {user.get('username', user_id)} not found in guild")
                        continue
                    
                    if registered_role not in member.roles:
                        try:
                            await member.add_roles(registered_role)
                            users_fixed += 1
                            logger.info(f"Added 'Registered' role to {member.name} ({user_id})")
                        except discord.Forbidden:
                            errors += 1
                            logger.error(f"Bot doesn't have permission to add roles to {member.name} ({user_id})")
                        except Exception as e:
                            errors += 1
                            logger.error(f"Error adding role to {member.name} ({user_id}): {e}")
                    else:
                        users_already_correct += 1
                        
                except Exception as e:
                    errors += 1
                    logger.error(f"Error processing user {user.get('username', user['user_id'])}: {e}")
            
            # Send summary
            summary = [
                f"Processed {total_users} registered users:",
                f"• {users_fixed} users had their 'Registered' role restored",
                f"• {users_already_correct} users already had correct roles",
                f"• {users_not_found} users were not found in the server",
            ]
            
            if errors > 0:
                summary.append(f"• {errors} errors occurred (check logs)")
                
            await interaction.followup.send("\n".join(summary), ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in verify-roles command: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(AdminCog(bot))