# Pocket Cauldron

A Discord companion for **FLASK**. Look up cards, infusers and monsters, or display a shared party.

| Command | What it does |
| --- | --- |
| `flask help` | Show help and examples. |
| `flask info Acidburn` | Show a card's artwork and description. |
| `flask info Acidburn level 3` | Show a specific level. |
| `flask info infuser Shielding` | Show an infuser and its effect. |
| `flask info infuser` | List infusers. |
| `flask monster Burning Witch` | Show a monster's flask cards. |
| `flask party FB1.…` | Display a shared party. |

Use `flask help info`, `flask help monster`, or `flask help party` for examples. Slash commands are under `/flask`; partial names offer a selection menu.

## Two projects, one library

- **This repository:** the Discord bot, run by the bot owner.
- **[FLASK Build Exporter](https://github.com/georgekitoshvili/flask-build-exporter):** the separate Windows helper players use to copy a saved party into Discord.
- **[Shared library](https://pocket-cauldron-library.pages.dev/):** centrally maintained game data and artwork, hosted outside both repositories on Cloudflare Pages.

The repositories contain source code and documentation. The bot downloads data at startup, checks for updates every 15 minutes, and downloads artwork as needed. Ordinary library updates need no new exporter download. Changes to app code or the game's save format can still require an app update.

The first run needs internet access. Later runs can use verified cached data during a library outage. Uncached artwork requires a connection.

## Run the bot

Requires Python **3.11+** and a Discord bot token. Steam and FLASK do not need to run on the bot's computer.

**Windows:** download and extract this repository, then run **Start Bot.cmd**. It installs dependencies and asks for your token privately. Keep the window open while the bot runs.

**Other systems or hosting:**

```sh
python -m venv .venv
# Activate the environment, then:
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env`, enter `DISCORD_TOKEN`, then run:

```sh
python bot.py
```

In the [Discord Developer Portal](https://discord.com/developers/applications), enable **Message Content Intent** for text commands. Invite with `bot` and `applications.commands` scopes and permissions **View Channels**, **Send Messages**, **Embed Links**, **Attach Files**, plus **Send Messages in Threads** if needed.

| Optional setting | Purpose |
| --- | --- |
| `DISCORD_GUILD_ID` | Register slash commands immediately in one test server. Leave empty for global commands. |
| `TEXT_COMMANDS=false` | Use slash commands only. |
| `FLASK_LIBRARY_URL` | Override the shared HTTPS manifest URL. |
| `FLASK_LIBRARY_CACHE` | Override the cache folder. |

Keep `.env` private; Git excludes it. Hosted deployments use the same settings and `python bot.py`. Use persistent storage if cached files should survive redeployments. The default cache is `%LOCALAPPDATA%/PocketCauldron/library` on Windows, or `$XDG_CACHE_HOME/pocket-cauldron/library` / `~/.cache/pocket-cauldron/library` elsewhere.

## Share a party

1. Get the Windows app from the [exporter project](https://github.com/georgekitoshvili/flask-build-exporter).
2. Save a run in FLASK and open **FLASK Share Build**.
3. Click **Copy Build**, then paste into a channel with this bot.

Players need no bot files, token or Python installation when using the packaged app. The helper reads saves without changing them. It copies a `flask party FB1.…` command containing team details, excluding account IDs, authentication data and the rest of the save. It does not upload saves.

Party views show characters, maximum HP, element tokens, mutations, snacks, flask levels, slot order and multiple infusers per flask. Base descriptions and infuser effects are shown separately; combat buffs and modified numbers are not recalculated. Exported `.flaskbuild.json` files are also accepted with `flask party`.

This is a community sharing format; the game does not currently generate these codes.

## Maintain the shared library

Game updates are published once by the maintainer. Clients automatically pick up the published version; they do not extract Steam files themselves.

Keep prepared `data/` and `assets/` in a separate master folder. The publisher expects `catalog.json`, `infusers.json`, `build-catalog.json` and `build-refs.json` under `data/`, plus referenced PNG artwork. Never commit the master folder or generated site.

```sh
python tools/publish_library.py --source /path/to/flask-library-master --output /path/to/flask-library-site
npx wrangler pages deploy /path/to/flask-library-site --project-name pocket-cauldron-library --branch main
```

Reuse the output folder so earlier immutable revisions remain available to open menus and cached clients. Changed data is verified before replacing the active snapshot. Publishing requires the maintainer's Cloudflare account; users need no Cloudflare credentials.

## Checks

```sh
python -m unittest discover -s tests -v
python bot.py --check
```

Unit tests generate synthetic data and run offline. `--check` validates the shared library without connecting to Discord and may download artwork.

FLASK artwork and game content belong to their respective creators. This is an unofficial community project.
