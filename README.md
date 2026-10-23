# Pocket Cauldron

## Download

| Download | What you need |
| --- | --- |
| **[Bot only](https://pocket-cauldron-library.pages.dev/downloads/Pocket-Cauldron-Bot.zip)** | Python 3.11+ and your own Discord bot token. |
| **[Exporter only](https://pocket-cauldron-library.pages.dev/downloads/FLASK-Share-Build-Windows.zip)** | Windows. No Python or token needed. |
| **[Bot + exporter](https://pocket-cauldron-library.pages.dev/downloads/Pocket-Cauldron-Bot-and-Exporter.zip)** | Both in one ZIP. Python and a token are needed for the bot. |

A Discord bot for FLASK cards, infusers, monster fights, special encounters and shared parties.

## Commands

| Command | What it does |
| --- | --- |
| `!flask help` | Show help and examples. |
| `!flask Acidburn` | Show a flask emoji and description; use Show full image for its artwork. |
| `!flask Acidburn level 3` | Show a specific card level. |
| `!flask ranger void` | List matching flasks with emoji and descriptions, one per line. |
| `!flask druid starting 4` | Only Druid flasks that start at level 4. Also available in the separate “Starts at level…” dropdown. |
| `!flask ranger strength` / `!flask rogue health` | Filter by class and keyword. Also works with `!flask poison` or `!flask ranger void luck`. |
| `!flask druid` / `!flask life` | Filter by any class or element. Use the controls for pages and levels. |
| `!flask artificer damage` / `!flask artificer armor` / `!flask artificer shield` | Filter a class by !flask effects. `artifacter` and `strike` also work as aliases. |
| `!flask infuser Shielding` | Show an infuser and its effect. |
| `!flask infusers` | List all infusers. |
| `!flask elements` | Browse element emojis and select an element to see its flasks. |
| `!flask organs` | List organ effects and team HP bonuses. |
| `!flask organ Sentinel` | Show its image, effect, team health bonus and class restriction. |
| `!flask monster Burning Witch` | Show each monster's mutation, base HP and !flask effects, including changing forms and random !flask pools. |
| `!flask monsters` | List every monster fight. |
| `!flask encounters` | List the two special encounters in each biome. |
| `!flask Witch Cauldron` | Show its biome, effects and vendor artwork. |
| `!flask info flasks` | Browse all !flask cards. |
| `!flask info monsters` / `!flask info encounters` | Browse monster fights or special encounters. |
| `!flask party FB1.…` | Show a shared party. |
| `!flask explain FB1.…` | Explain a party's flasks, organs, infusers, recognized interactions and cautions. JSON attachments also work. |

`!flask organs` lists organ effects. Use `!flask rogue organs` (or any class) to list every organ that character can receive. Use `!flask organ <name>` for its image and details.

Slash commands are also available under `/flask`.
Flask descriptions show their element icons at the end.
Flask search pages use up to three consecutive messages, with navigation and level controls on the last message.



Search with keywords directly: `!flask rogue kunai`, `!flask ranger health`, `!flask artificer drone`, `!flask artificer heat` or `!flask artificer frost`. Flourish is healing each turn; Bolstering increases shield gained. Fire means Burn. Spirit searches include `!flask druid spirits`, `!flask druid beetle`, `!flask druid jaybird`, `!flask druid viper` and `!flask druid wolverine`. Use `!flask warrior taunt` for Taunt. Thorns means Spikes, Gambling means Gamble, and `ethernal` also finds Eternal. Stealth includes Strength-reducing effects; use `-strength` to list those alone.

## Share your party

1. **[Download the Windows build exporter](https://pocket-cauldron-library.pages.dev/downloads/FLASK-Share-Build-Windows.zip)** and extract the ZIP.
2. Save your run in FLASK, then open **FLASK Share Build.exe**.
3. Choose **Current saved team** or a completed run from the list, then click **Copy Build**.
4. Paste into a Discord channel with Pocket Cauldron and press Enter.

The bot shows your characters, flasks, levels, infusers, snacks, mutations and element tokens. The exporter includes the current saved team and up to 10 completed runs retained in FLASK’s match history. It reads your save without changing it. Players do not need Python or the bot's files. Internet is needed on the first run.

## Run your own bot

1. Install **[Python 3.11 or newer](https://www.python.org/downloads/)**.
2. Download **Bot only** or **Bot + exporter** above and extract the ZIP.
3. Create a bot in the **[Discord Developer Portal](https://discord.com/developers/applications)**. On its **Bot** page, enable **Message Content Intent** and copy its token.
4. Open the **bot** folder, run **Start Bot.cmd**, and paste the token when asked. Keep the window open.
5. In the Developer Portal, open **OAuth2 → URL Generator**, select `bot` and `applications.commands`, and enable **View Channels**, **Send Messages**, **Embed Links** and **Attach Files**. Add **Send Messages in Threads** if needed.
6. Open the generated invite link, choose your server, then try `!flask help`.

The Windows launcher creates `.env` from `.env.example` and saves your token automatically. You don't need to edit either file. Keep your token private and never share `.env`.

On Linux or a hosting service, use the **bot** folder as the working directory, install `requirements.txt`, set `DISCORD_TOKEN`, and start with `python bot.py`.

## Run the exporter from source

With Python installed, open the **exporter** folder and run **Start Exporter.cmd** or `python share_app.py`.

Unofficial community project. FLASK content belongs to its respective creators.
