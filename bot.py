"""
NukeBot — A Discord server decommissioning bot.

Provides two admin-only slash commands:
  /nuke         - Delete every message on the server (with optional filters)
  /nukefinish   - Kick every member from the server
"""

import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

if not TOKEN:
    raise ValueError("DISCORD_TOKEN not found in .env — see .env.example")


# ---------------------------------------------------------------------------
# Bot setup
# ---------------------------------------------------------------------------
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    if GUILD_ID:
        guild = discord.Object(id=int(GUILD_ID))
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f"Synced {len(synced)} commands to guild {GUILD_ID}")
    else:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands globally (may take up to 1 hour)")
    print("NukeBot is ready. ☢️")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
KICK_REASON = (
    "This server is being decommissioned and deleted with NukeBot, "
    "please contact the server administrator for more details"
)


def admin_only():
    """Decorator that restricts a command to server administrators."""
    return app_commands.checks.has_permissions(administrator=True)


def make_embed(title: str, description: str, *, color: discord.Color = discord.Color.red()) -> discord.Embed:
    """Build a consistent embed for the bot's messages."""
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text="NukeBot ☢️")
    embed.timestamp = datetime.now(timezone.utc)
    return embed


# ---------------------------------------------------------------------------
# Confirmation views
# ---------------------------------------------------------------------------
class NukeConfirmView(discord.ui.View):
    """Confirmation view for /nuke with Confirm and Cancel buttons."""

    def __init__(
        self,
        author: discord.Member,
        channel_filter: Optional[discord.TextChannel],
        user_filter: Optional[discord.Member],
    ):
        super().__init__(timeout=60)
        self.author = author
        self.channel_filter = channel_filter
        self.user_filter = user_filter
        self.confirmed = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "Only the person who invoked the command can confirm.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="☢️ Confirm Nuke", style=discord.ButtonStyle.danger)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        self.stop()
        await interaction.response.edit_message(
            embed=make_embed("☢️ NUKE INITIATED", "Starting message purge…"),
            view=None,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        self.stop()
        await interaction.response.edit_message(
            embed=make_embed("Cancelled", "Nuke aborted. No messages were deleted.", color=discord.Color.green()),
            view=None,
        )

    async def on_timeout(self):
        self.confirmed = False


class KickConfirmView(discord.ui.View):
    """Confirmation view for /nukefinish with Confirm and Cancel buttons."""

    def __init__(self, author: discord.Member):
        super().__init__(timeout=60)
        self.author = author
        self.confirmed = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "Only the person who invoked the command can confirm.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="☢️ Confirm Kick All", style=discord.ButtonStyle.danger)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        self.stop()
        await interaction.response.edit_message(
            embed=make_embed("☢️ KICK INITIATED", "Starting to kick all members…"),
            view=None,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        self.stop()
        await interaction.response.edit_message(
            embed=make_embed("Cancelled", "No members were kicked.", color=discord.Color.green()),
            view=None,
        )

    async def on_timeout(self):
        self.confirmed = False


# ---------------------------------------------------------------------------
# /nuke command
# ---------------------------------------------------------------------------
@bot.tree.command(name="nuke", description="☢️ Delete every message on the server (irreversible!)")
@app_commands.describe(
    channel="Only nuke messages in this channel",
    user="Only nuke messages from this user",
)
@admin_only()
async def nuke(
    interaction: discord.Interaction,
    channel: Optional[discord.TextChannel] = None,
    user: Optional[discord.Member] = None,
):
    # Build warning message
    scope_parts: list[str] = []
    if channel:
        scope_parts.append(f"**Channel:** #{channel.name}")
    else:
        scope_parts.append("**Channel:** ALL text channels")
    if user:
        scope_parts.append(f"**User:** {user.mention}")
    else:
        scope_parts.append("**User:** ALL users")

    description = (
        "⚠️ **THIS ACTION IS IRREVERSIBLE** ⚠️\n\n"
        "This will **unpin** and **permanently delete** messages with the following scope:\n\n"
        + "\n".join(scope_parts)
        + "\n\n"
        "Messages older than 14 days will be deleted individually (slower due to Discord rate limits).\n\n"
        "Are you sure you want to proceed?"
    )

    view = NukeConfirmView(author=interaction.user, channel_filter=channel, user_filter=user)
    await interaction.response.send_message(
        embed=make_embed("☢️ NUKE WARNING", description, color=discord.Color.orange()),
        view=view,
    )

    # Wait for the user to confirm or cancel
    timed_out = await view.wait()
    if timed_out or not view.confirmed:
        if timed_out:
            await interaction.edit_original_response(
                embed=make_embed("Timed Out", "Confirmation not received within 60 seconds. Nuke aborted.",
                                 color=discord.Color.greyple()),
                view=None,
            )
        return

    # ----- Execute nuke -----
    guild = interaction.guild
    channels_to_nuke: list[discord.TextChannel] = [channel] if channel else [
        ch for ch in guild.text_channels if ch.permissions_for(guild.me).manage_messages
    ]

    total_deleted = 0
    total_unpinned = 0
    channels_done = 0
    total_channels = len(channels_to_nuke)

    # Send a persistent progress message that we'll keep updating
    progress_msg = await interaction.channel.send(
        embed=make_embed(
            "☢️ Nuke in Progress…",
            f"Processing **0** / **{total_channels}** channels\n"
            f"Messages deleted: **0**\nMessages unpinned: **0**",
            color=discord.Color.dark_orange(),
        )
    )
    last_progress_update = time.monotonic()

    async def update_progress(force: bool = False):
        nonlocal last_progress_update
        now = time.monotonic()
        # Update at most once per minute unless forced
        if not force and (now - last_progress_update) < 60:
            return
        last_progress_update = now
        try:
            await progress_msg.edit(
                embed=make_embed(
                    "☢️ Nuke in Progress…",
                    f"Processing **{channels_done}** / **{total_channels}** channels\n"
                    f"Messages deleted: **{total_deleted}**\n"
                    f"Messages unpinned: **{total_unpinned}**",
                    color=discord.Color.dark_orange(),
                )
            )
        except discord.HTTPException:
            pass

    for ch in channels_to_nuke:
        try:
            # 1. Unpin all pinned messages
            try:
                pins = await ch.pins()
                for pin in pins:
                    try:
                        if user and pin.author.id != user.id:
                            continue
                        await pin.unpin()
                        total_unpinned += 1
                    except discord.HTTPException as e:
                        print(f"  Failed to unpin message {pin.id}: {e}")
            except discord.HTTPException as e:
                print(f"  Could not fetch pins in #{ch.name}: {e}")

            # 2. Delete messages
            if user:
                # With user filter — use purge with a check
                def check_user(msg: discord.Message) -> bool:
                    return msg.author.id == user.id

                # purge handles the 14-day bulk delete split internally
                try:
                    deleted = await ch.purge(limit=None, check=check_user, oldest_first=False)
                    total_deleted += len(deleted)
                except discord.HTTPException:
                    pass

                await update_progress()

                # For messages older than 14 days that purge may miss,
                # iterate through full history
                cutoff = datetime.now(timezone.utc) - timedelta(days=14)
                async for msg in ch.history(limit=None, before=cutoff, oldest_first=True):
                    if msg.author.id != user.id:
                        continue
                    try:
                        await msg.delete()
                        total_deleted += 1
                    except discord.HTTPException as e:
                        print(f"  Failed to delete msg {msg.id}: {e}")
                    await update_progress()
            else:
                # No user filter — nuke everything
                # First: bulk purge (handles <14 day messages)
                try:
                    deleted = await ch.purge(limit=None, oldest_first=False)
                    total_deleted += len(deleted)
                except discord.HTTPException:
                    pass

                await update_progress()

                # Then: individually delete any remaining old messages
                async for msg in ch.history(limit=None, oldest_first=True):
                    try:
                        await msg.delete()
                        total_deleted += 1
                    except discord.HTTPException as e:
                        print(f"  Failed to delete msg {msg.id}: {e}")
                    await update_progress()

        except Exception as e:
            print(f"Error processing #{ch.name}: {e}")

        channels_done += 1
        await update_progress(force=True)

    # Final progress update — delete the progress message and send summary
    try:
        await progress_msg.delete()
    except discord.HTTPException:
        pass

    await interaction.channel.send(
        embed=make_embed(
            "☢️ Nuke Complete",
            f"**Channels processed:** {channels_done}/{total_channels}\n"
            f"**Messages deleted:** {total_deleted}\n"
            f"**Messages unpinned:** {total_unpinned}",
            color=discord.Color.dark_red(),
        )
    )


# ---------------------------------------------------------------------------
# /nukefinish command
# ---------------------------------------------------------------------------
@bot.tree.command(name="nukefinish", description="☢️ Kick every member from the server (irreversible!)")
@admin_only()
async def nukefinish(interaction: discord.Interaction):
    guild = interaction.guild

    # Collect members to kick (exclude invoker, bot itself, and owner)
    members_to_kick = [
        m for m in guild.members
        if m.id != interaction.user.id
        and m.id != bot.user.id
        and m.id != guild.owner_id
    ]

    description = (
        "⚠️ **THIS ACTION IS IRREVERSIBLE** ⚠️\n\n"
        f"This will **kick {len(members_to_kick)} members** from the server.\n\n"
        "Each member will receive the following message:\n"
        f"> *{KICK_REASON}*\n\n"
        f"The **server owner** ({guild.owner.mention}) cannot be kicked and will be skipped.\n"
        "The bot will **kick itself** at the very end.\n\n"
        "Are you sure you want to proceed?"
    )

    view = KickConfirmView(author=interaction.user)
    await interaction.response.send_message(
        embed=make_embed("☢️ KICK WARNING", description, color=discord.Color.orange()),
        view=view,
    )

    timed_out = await view.wait()
    if timed_out or not view.confirmed:
        if timed_out:
            await interaction.edit_original_response(
                embed=make_embed("Timed Out", "Confirmation not received within 60 seconds. Kick aborted.",
                                 color=discord.Color.greyple()),
                view=None,
            )
        return

    # ----- Execute kicks -----
    total = len(members_to_kick)
    kicked = 0
    failed = 0

    progress_msg = await interaction.channel.send(
        embed=make_embed(
            "☢️ Kicking Members…",
            f"Progress: **0** / **{total}** kicked\nFailed: **0**",
            color=discord.Color.dark_orange(),
        )
    )
    last_progress_update = time.monotonic()

    for member in members_to_kick:
        try:
            await member.kick(reason=KICK_REASON)
            kicked += 1
        except discord.Forbidden:
            print(f"  Cannot kick {member} — role hierarchy or permissions issue")
            failed += 1
        except discord.HTTPException as e:
            print(f"  Failed to kick {member}: {e}")
            failed += 1

        # Update progress every ~30 seconds
        now = time.monotonic()
        if (now - last_progress_update) >= 30:
            last_progress_update = now
            try:
                await progress_msg.edit(
                    embed=make_embed(
                        "☢️ Kicking Members…",
                        f"Progress: **{kicked}** / **{total}** kicked\nFailed: **{failed}**",
                        color=discord.Color.dark_orange(),
                    )
                )
            except discord.HTTPException:
                pass

    # Final summary
    try:
        await progress_msg.edit(
            embed=make_embed(
                "☢️ Kick Complete",
                f"**Kicked:** {kicked} / {total}\n"
                f"**Failed:** {failed}\n"
                f"**Skipped (owner):** {guild.owner.display_name}",
                color=discord.Color.dark_red(),
            )
        )
    except discord.HTTPException:
        pass

    # Kick the bot itself at the very end
    try:
        await guild.leave()
    except discord.HTTPException as e:
        print(f"Failed to leave the server: {e}")
        try:
            await interaction.channel.send(
                embed=make_embed(
                    "⚠️ Could Not Self-Remove",
                    "The bot was unable to leave the server automatically. Please remove it manually.",
                    color=discord.Color.orange(),
                )
            )
        except discord.HTTPException:
            pass


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            embed=make_embed(
                "🚫 Permission Denied",
                "You need **Administrator** permissions to use this command.",
                color=discord.Color.red(),
            ),
            ephemeral=True,
        )
    elif isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message(
            embed=make_embed(
                "🚫 Check Failed",
                "You do not have permission to use this command.",
                color=discord.Color.red(),
            ),
            ephemeral=True,
        )
    else:
        print(f"Unhandled command error: {error}")
        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    embed=make_embed("❌ Error", f"An unexpected error occurred:\n```{error}```"),
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    embed=make_embed("❌ Error", f"An unexpected error occurred:\n```{error}```"),
                    ephemeral=True,
                )
        except discord.HTTPException:
            pass


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    bot.run(TOKEN)
