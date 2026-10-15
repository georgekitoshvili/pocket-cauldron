# Pocket Cauldron

## Download

| Download | What you need |
| --- | --- |
| **[Bot only](https://pocket-cauldron-library.pages.dev/downloads/Pocket-Cauldron-Bot.zip)** | Python 3.11+ and your own Discord bot token. |
| **[Exporter only](https://pocket-cauldron-library.pages.dev/downloads/FLASK-Share-Build-Windows.zip)** | Windows. No Python or token needed. |
| **[Bot + exporter](https://pocket-cauldron-library.pages.dev/downloads/Pocket-Cauldron-Bot-and-Exporter.zip)** | Both in one ZIP. Python and a token are needed for the bot. |

A Discord bot for FLASK cards, infusers, monsters, events and shared parties.

## Commands

| Command | What it does |
| --- | --- |
| `flask help` | Show help and examples. |
| `flask info Acidburn` | Show a card and its description. |
| `flask info Acidburn level 3` | Show a specific card level. |
| `flask info infuser Shielding` | Show an infuser and its effect. |
| `flask info infuser` | List all infusers. |
| `flask monster Burning Witch` | Show a monster's cards. |
| `flask monsters` | List every monster. |
| `flask events` | List events. |
| `flask Witch Cauldron` | Show an event's effects and vendor artwork. |
| `flask info flasks` | Browse all flask cards. |
| `flask info monsters` / `flask info events` | Browse monsters or events. |
| `flask party FB1.…` | Show a shared party. |

Slash commands are also available under `/flask`.

## Share your party

1. **[Download the Windows build exporter](https://pocket-cauldron-library.pages.dev/downloads/FLASK-Share-Build-Windows.zip)** and extract the ZIP.
2. Save your run in FLASK, then open **FLASK Share Build.exe**.
3. Choose your saved run and click **Copy Build**.
4. Paste into a Discord channel with Pocket Cauldron and press Enter.

The bot shows your characters, flasks, levels, infusers, snacks, mutations and element tokens. The exporter reads your save without changing it. Players do not need Python or the bot's files. Internet is needed on the first run.

## Run your own bot

1. Install **[Python 3.11 or newer](https://www.python.org/downloads/)**.
2. Download **Bot only** or **Bot + exporter** above and extract the ZIP.
3. Create a bot in the **[Discord Developer Portal](https://discord.com/developers/applications)**. On its **Bot** page, enable **Message Content Intent** and copy its token.
4. Open the **bot** folder, run **Start Bot.cmd**, and paste the token when asked. Keep the window open.
5. In the Developer Portal, open **OAuth2 → URL Generator**, select `bot` and `applications.commands`, and enable **View Channels**, **Send Messages**, **Embed Links** and **Attach Files**. Add **Send Messages in Threads** if needed.
6. Open the generated invite link, choose your server, then try `flask help`.

The Windows launcher creates `.env` from `.env.example` and saves your token automatically. You don't need to edit either file. Keep your token private and never share `.env`.

On Linux or a hosting service, use the **bot** folder as the working directory, install `requirements.txt`, set `DISCORD_TOKEN`, and start with `python bot.py`.

## Run the exporter from source

With Python installed, open the **exporter** folder and run **Start Exporter.cmd** or `python share_app.py`.

Unofficial community project. FLASK content belongs to its respective creators.
