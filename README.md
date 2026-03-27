# ☢️ NukeBot

A Discord bot for bulk deleting messages and kicking members. Used for decommissioning servers.

**WARNING**: This bot has been created with the help of AI coding tools. While effort has been made to ensure a lack of bugs or issues, it is possible for some bugs or issues to exist. Please use this bot at your own risk.

## Why does it exist?

Given the current controversies surrounding Discord, a lot of people are choosing to download their messages locally and delete them from Discord. This bot is meant to help with wiping out servers.

Note that the existence of this bot hinges on the suspicion that Discord is more likely to actually "delete" your messages on their backend if you manually force delete them as opposed to simply removing all members from the server (as evidenced by the fact that deleting older messages is rate limited due to a lack of indexing - deleting a server likely waits some time to delete the actual messages).

The bot also allows for deleting all messages in one channel, or deleting all messages from a specific user.

## Commands

| Command | Description |
|---------|-------------|
| `/nuke` | Delete every message on the server. Optional `channel` and `user` filters. Picking no filters wipes ALL channels. |
| `/nukefinish` | Kick every member from the server, then the bot leaves. |

## Setup Instructions

**COMING SOON**

Note that due to the long process of getting Discord's approval for public previleged intent bots, I am unable to provide a publicly accessible bot. You will need to create a bot account on the Discord Developer Portal and host the bot yourself. More details about this process will be added here soon.
