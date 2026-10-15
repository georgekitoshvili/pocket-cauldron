"""Standalone FLASK lookup bot with a shared, locally cached game library."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import time
from io import BytesIO

import discord
from build_protocol import MAX_BUILD_BYTES, decode_build, decode_code
from builds import BuildCatalog
from discord import app_commands
from dotenv import load_dotenv
from library_client import LibraryError
from lookup import ROOT, Catalog, Match, parse_message

LOG = logging.getLogger("flask_bot")
HELP = (
    "What can I do for you?\n\n"
    "```text\n"
    "help        Display help and examples.\n"
    "info        Show a flask, infuser, fight, or special encounter.\n"
    "monsters    List every monster fight.\n"
    "encounters  List special encounters by biome.\n"
    "party       Display a party from a FLASK build code.\n"
    "```\n"
    "**Browse:** `flask info flasks` · `flask info monsters` · `flask info encounters`\n\n"
    "**Try:**\n"
    "`flask info Acidburn`\n"
    "`flask info infuser Shielding`\n"
    "`flask monster Burning Witch`\n"
    "`flask Witch Cauldron`\n"
    "`flask party FB1.…` (paste a full code from FLASK Share Build)\n\n"
    "Start commands with `flask`. Slash versions are under `/flask`."
)


def help_text(topic=""):
    topic = topic.strip().lower()
    details = {
        "info": (
            "**info — look up game content**\n"
            "`flask info flasks` · `flask info monsters` · `flask info encounters`\n"
            "`flask info Acidburn`\n`flask info Acidburn level 3`\n"
            "`flask info infuser Shielding`\n"
            "`flask info infuser` lists every infuser. Card descriptions show base values."
        ),
        "infuser": (
            "**Infusers**\n`flask info infuser Shielding` shows its icon and effect.\n"
            "`flask info infuser` lists all infusers. Party results keep each infuser "
            "attached to its flask; base effects and infuser effects are shown separately."
        ),
        "party": (
            "**party — show a saved team**\nOpen FLASK Share Build, click Copy Build, "
            "then paste in Discord.\nThe command is `flask party FB1.…` with the complete code. "
            "You can also attach an exported JSON file with `flask party`.\n"
            "Party details include flask levels, multiple infusers, mutations, snacks, HP, and element tokens."
        ),
        "monster": (
            "**Monsters**\n`flask monsters` or `flask info monsters` lists every monster fight.\n"
            "`flask monster Burning Witch` shows every enemy and its flask cards.\n"
            "Select a name from the list to view it."
        ),
        "event": (
            "**Special encounters**\n`flask encounters` or `flask info encounters` lists the two encounters in each biome.\n"
            "`flask Witch Cauldron` or `flask info Witch Cauldron` shows where it appears, its effects and vendor artwork."
        ),
        "flasks": "**Flasks**\n`flask info flasks` lists every flask. Select a name to see its card and effects.",
        "help": HELP,
    }
    topic = {
        "monsters": "monster",
        "events": "event",
        "encounters": "event",
        "encounter": "event",
    }.get(topic, topic)
    return details.get(topic, HELP)


LIST_KINDS = {
    "flasks": "card",
    "cards": "card",
    "monsters": "monster",
    "events": "event",
    "encounters": "event",
}


async def list_response(catalog, kind, owner, send):
    matches = sorted(
        (match for match in catalog.matches if match.kind == kind),
        key=lambda match: (
            match.item.get("biome", 0),
            match.label.casefold(),
            match.item["id"],
        ),
    )
    title = {
        "card": "flasks",
        "monster": "monster fights",
        "event": "special encounters",
    }[kind]
    if not matches:
        await send(content=f"No {title} are available in the current library.")
        return
    view = ResultsView(catalog, matches, owner, list_title=title)
    await send(content=view.list_content(), view=view)


async def info_response(catalog, query, owner, send, level=None):
    query = query.strip()
    if query.lower() in LIST_KINDS:
        await list_response(catalog, LIST_KINDS[query.lower()], owner, send)
        return
    if query.lower() in ("infuser", "infusers"):
        names = " Â· ".join(
            i["name"]
            for i in sorted(catalog.infusers.values(), key=lambda i: i["name"])
        )
        await send(
            content=f"**All {len(catalog.infusers)} infusers**\n{names}\n\nExample: `flask info infuser Shielding`"
        )
        return
    if not query:
        await send(content=help_text("info"))
        return
    if query not in catalog.by_key and not re.match(
        r"^(?:infuser|card|flask|monster|event|encounter)\s+", query, re.I
    ):
        query = "info " + query
    await lookup_response(catalog, query, owner, send, level)


async def monster_response(catalog, query, owner, send):
    if not query.strip():
        await list_response(catalog, "monster", owner, send)
        return
    await lookup_response(catalog, "monster " + query.strip(), owner, send)


def payload(catalog: Catalog, match: Match, page=0, level=None):
    embeds = []
    files = []
    for i, row in enumerate(catalog.page(match, page, level)):
        embed = discord.Embed(
            title=row["title"], description=row["description"], colour=0x9569E8
        )
        for name, value in row["fields"]:
            embed.add_field(name=name, value=value, inline=True)
        embed.set_footer(text=row["footer"])
        if row["image"]:
            try:
                path = catalog.image_path(row["image"])
            except (OSError, LibraryError):
                embed.set_footer(
                    text=row["footer"] + " Â· Artwork temporarily unavailable"
                )
                embeds.append(embed)
                continue
            filename = f"lookup_{i}.png"
            files.append(discord.File(path, filename=filename))
            if row["small"]:
                embed.set_thumbnail(url="attachment://" + filename)
            else:
                embed.set_image(url="attachment://" + filename)
        embeds.append(embed)
    return embeds, files


class OwnedView(discord.ui.View):
    def __init__(self, owner: int):
        super().__init__(timeout=180)
        self.owner = owner

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await interaction.response.send_message(
                "Run your own `flask show` lookup to use its controls.", ephemeral=True
            )
            return False
        return True


class DetailView(OwnedView):
    def __init__(self, catalog: Catalog, match: Match, owner: int, level=None):
        super().__init__(owner)
        self.catalog = catalog
        self.match = match
        self.page_index = 0
        self.level = level
        if match.kind == "card":
            current = level if level is not None else match.item["available_level"]
            select = discord.ui.Select(
                placeholder="Flask level",
                options=[
                    discord.SelectOption(
                        label=f"Level {n}", value=str(n), default=n == current
                    )
                    for n in range(match.item["available_level"], 5)
                ],
            )

            async def change(interaction):
                self.level = int(select.values[0])
                for option in select.options:
                    option.default = int(option.value) == self.level
                await self.refresh(interaction)

            select.callback = change
            self.add_item(select)
        elif catalog.pages(match) > 1:
            self.previous = discord.ui.Button(
                label="Previous", style=discord.ButtonStyle.secondary
            )
            self.next = discord.ui.Button(
                label="Next", style=discord.ButtonStyle.secondary
            )
            self.counter = discord.ui.Button(
                label=f"1 / {catalog.pages(match)}", disabled=True
            )

            async def previous(interaction):
                self.page_index = (self.page_index - 1) % catalog.pages(match)
                await self.refresh(interaction)

            async def next_page(interaction):
                self.page_index = (self.page_index + 1) % catalog.pages(match)
                await self.refresh(interaction)

            self.previous.callback = previous
            self.next.callback = next_page
            for button in (self.previous, self.counter, self.next):
                self.add_item(button)

    async def refresh(self, interaction):
        await interaction.response.defer()
        if hasattr(self, "counter"):
            self.counter.label = (
                f"{self.page_index+1} / {self.catalog.pages(self.match)}"
            )
        embeds, files = await asyncio.to_thread(
            payload, self.catalog, self.match, self.page_index, self.level
        )
        try:
            await interaction.edit_original_response(
                embeds=embeds, attachments=files, view=self
            )
        finally:
            for file in files:
                file.close()


class ResultsView(OwnedView):
    def __init__(
        self,
        catalog: Catalog,
        matches: list[Match],
        owner: int,
        level=None,
        list_title=None,
    ):
        super().__init__(owner)
        self.catalog = catalog
        self.matches = matches
        self.list_title = list_title
        self.level = level
        self.index = 0
        kinds = {match.kind for match in matches}
        placeholder = (
            {
                "card": "Select a flask",
                "monster": "Select a monster fight",
                "infuser": "Select an infuser",
                "event": "Select an encounter",
            }.get(next(iter(kinds)), "Select a result")
            if len(kinds) == 1
            else "Select a result"
        )
        self.select = discord.ui.Select(placeholder=placeholder)
        self.select.callback = self.pick
        self.add_item(self.select)
        if len(matches) > 25:
            prev = discord.ui.Button(label="Previous results", row=1)
            nxt = discord.ui.Button(label="More results", row=1)

            async def backwards(interaction):
                self.index = (self.index - 1) % ((len(matches) + 24) // 25)
                self.options()
                await interaction.response.edit_message(
                    **({"content": self.list_content()} if self.list_title else {}),
                    view=self,
                )

            async def forwards(interaction):
                self.index = (self.index + 1) % ((len(matches) + 24) // 25)
                self.options()
                await interaction.response.edit_message(
                    **({"content": self.list_content()} if self.list_title else {}),
                    view=self,
                )

            prev.callback = backwards
            nxt.callback = forwards
            self.add_item(prev)
            self.add_item(nxt)
        self.options()

    def list_content(self):
        page_count = (len(self.matches) + 24) // 25
        lines = []
        previous_biome = None
        for match in self.matches[self.index * 25 : self.index * 25 + 25]:
            biome = match.item.get("biome")
            if biome is not None and biome != previous_biome:
                lines.append(f"\n**Biome {biome}**")
                previous_biome = biome
            lines.append(match.label)
        names = "\n".join(lines)
        return (
            f"**All {len(self.matches)} {self.list_title}** · Page {self.index + 1}/{page_count}\n"
            f"{names}\n\n{self.select.placeholder} below to view its details."
        )

    def options(self):
        self.select.options = [
            discord.SelectOption(
                label=m.label[:100],
                value=m.key,
            )
            for m in self.matches[self.index * 25 : self.index * 25 + 25]
        ]

    async def pick(self, interaction):
        match = self.catalog.by_key[self.select.values[0]]
        await interaction.response.defer()
        try:
            embeds, files = await asyncio.to_thread(
                payload, self.catalog, match, level=self.level
            )
        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        view = DetailView(self.catalog, match, self.owner, self.level)
        try:
            await interaction.edit_original_response(
                content=None, embeds=embeds, attachments=files, view=view
            )
            self.stop()
        finally:
            for file in files:
                file.close()


async def lookup_response(catalog, query, owner, send, level=None):
    query = query.strip()
    list_query = re.sub(r"^info\s+", "", query, flags=re.I).lower()
    if list_query in LIST_KINDS:
        await list_response(catalog, LIST_KINDS[list_query], owner, send)
        return
    if not query:
        await send(content=HELP)
        return
    if len(query) > 120:
        await send(content="Please use a name shorter than 120 characters.")
        return
    if level is not None and not 1 <= level <= 4:
        await send(content="Flask levels are 1â€“4.")
        return
    matches, exact = catalog.search(query)
    if not matches:
        await send(
            content="Exact match not found. No similar flasks, infusers, monsters, or events found. Try a shorter name."
        )
        return
    if exact and len(matches) == 1:
        try:
            embeds, files = await asyncio.to_thread(
                payload, catalog, matches[0], level=level
            )
        except ValueError as exc:
            await send(content=str(exc))
            return
        view = DetailView(catalog, matches[0], owner, level)
        try:
            await send(embeds=embeds, files=files, view=view)
        finally:
            for file in files:
                file.close()
    else:
        await send(
            content=(
                f"{len(matches)} exact matches. Choose one below:"
                if exact
                else f"Exact match not found. {len(matches)} similar results. Choose one below:"
            ),
            view=ResultsView(catalog, matches, owner, level),
        )


class BuildView(OwnedView):
    def __init__(self, catalog, build_catalog, build, owner):
        super().__init__(owner)
        self.catalog = catalog
        self.build_catalog = build_catalog
        self.build = build
        options = [discord.SelectOption(label="Team overview", value="overview")]
        for i, character in enumerate(build["build"]["characters"]):
            for start in range(0, max(1, len(character["flasks"])), 3):
                last_slot = min(start + 3, len(character["flasks"]))
                label = (
                    f"{i + 1}. {build_catalog.name(character['id'])}"
                    f" - slots {start + 1}-{last_slot}"
                )
                options.append(
                    discord.SelectOption(label=label[:100], value=f"{i}:{start}")
                )
        self.select = discord.ui.Select(
            placeholder="View a characterâ€™s flasks and effects", options=options
        )
        self.select.callback = self.pick
        self.add_item(self.select)
        self.overview_image = None

    def overview(self):
        embed = discord.Embed(
            title="FLASK - exported team",
            description=self.build_catalog.summary(self.build)[:1800],
            colour=0x9569E8,
        )
        for i, character in enumerate(self.build["build"]["characters"], 1):
            equipped_count = sum(flask is not None for flask in character["flasks"])
            value = f"{character['hp']} HP - {equipped_count} equipped flasks"
            if character["mutation"] != -1:
                value += "\nMutation: " + self.build_catalog.name(character["mutation"])
            if character["snacks"]:
                value += f"\n{len(character['snacks'])} snacks (select character for details)"
            embed.add_field(
                name=f"{i}. {self.build_catalog.name(character['id'])}",
                value=value[:400],
                inline=True,
            )
        embed.set_image(url="attachment://build.png")
        embed.set_footer(text="Saved build - game version " + self.build["gameVersion"])
        return embed

    async def pick(self, interaction):
        if self.select.values[0] == "overview":
            file = discord.File(BytesIO(self.overview_image), filename="build.png")
            try:
                await interaction.response.edit_message(
                    embeds=[self.overview()], attachments=[file], view=self
                )
            finally:
                file.close()
            return
        char_index, start = map(int, self.select.values[0].split(":"))
        await interaction.response.defer()
        character = self.build["build"]["characters"][char_index]
        header = discord.Embed(
            title=f"{char_index+1}. {self.build_catalog.name(character['id'])}",
            description=self.build_catalog.character_text(character)[:2200],
            colour=0x9569E8,
        )
        header.set_footer(
            text="Base effects; infuser numeric changes and battle buffs are not recalculated."
        )
        embeds = [header]
        files = []
        for slot, flask in enumerate(character["flasks"][start : start + 3], start + 1):
            if flask is None:
                continue
            card = self.catalog.cards.get(flask["id"])
            if card and str(flask["level"]) in card["descriptions"]:
                card_embeds, card_files = await asyncio.to_thread(
                    payload, self.catalog, Match("card", card), level=flask["level"]
                )
                embed = card_embeds[0]
                embed.title = f"Slot {slot}: " + embed.title
                embed.description = embed.description[:800]
                # Each card needs a distinct Discord attachment filename.
                for file in card_files:
                    file.filename = f"build_slot_{slot}.png"
                    embed.set_image(url=None)
                    embed.set_thumbnail(url="attachment://" + file.filename)
                if flask["infusers"]:
                    effects = self.infuser_effects(flask["infusers"])
                    embed.add_field(
                        name="Infusers â€” applied to this flask",
                        value=effects[:1024],
                        inline=False,
                    )
                embeds.append(embed)
                files.extend(card_files)
        # Bound the combined embed text to Discord's 6000 character limit.
        if sum(len(embed) for embed in embeds) > 6000:
            header.description = header.description[:800]
            for embed in embeds[1:]:
                embed.description = embed.description[:400]
        try:
            await interaction.edit_original_response(
                embeds=embeds, attachments=files, view=self
            )
        finally:
            for file in files:
                file.close()

    def infuser_effects(self, infuser_ids: list[int]) -> str:
        descriptions = []
        names = []
        for infuser_id in infuser_ids:
            name = self.build_catalog.name(infuser_id)
            effect = self.catalog.infusers.get(infuser_id, {}).get(
                "description", "Unknown effect"
            )
            names.append(name)
            descriptions.append(f"**{name}**: {effect}")

        effects = "\n".join(descriptions)
        # Leave room for the rest of the character's Discord embed.
        if len(effects) > 900:
            return ", ".join(names) + "\nUse flask info infuser <name> for each effect."
        return effects


async def build_response(catalog, build_catalog, attachment, owner, send, code=None):
    if attachment is None and not code:
        await send(
            content="Open FLASK Share Build, click Copy Build, then paste the copied command here. Or attach an exported .flaskbuild.json with `flask party`."
        )
        return
    if not code and (
        attachment.size > MAX_BUILD_BYTES
        or not attachment.filename.lower().endswith(".json")
    ):
        await send(
            content="Attach an exported build JSON file smaller than 128 KB. Full game saves are not accepted."
        )
        return
    try:
        build = decode_code(code) if code else decode_build(await attachment.read())
        image = await asyncio.to_thread(build_catalog.render, build)
    except (ValueError, OSError) as exc:
        await send(content=str(exc))
        return
    view = BuildView(catalog, build_catalog, build, owner)
    view.overview_image = image.getvalue()
    file = discord.File(image, filename="build.png")
    try:
        await send(embeds=[view.overview()], files=[file], view=view)
    finally:
        file.close()


class FlaskBot(discord.Client):
    def __init__(self, catalog: Catalog, text_commands=True, guild_id=None):
        intents = discord.Intents.default()
        intents.message_content = text_commands
        super().__init__(
            intents=intents, allowed_mentions=discord.AllowedMentions.none()
        )
        self.catalog = catalog
        self.text_commands = text_commands
        self.guild_id = guild_id
        self.build_catalog = BuildCatalog(root=catalog.root, snapshot=catalog.library)
        self.build_lock = asyncio.Lock()
        self.library_task = None
        self.tree = app_commands.CommandTree(self)
        self.last_lookup = {}
        group = app_commands.Group(
            name="flask", description="FLASK cards, infusers, monsters, and parties."
        )

        @group.command(
            name="show",
            description="Show a flask image and description, or a monsterâ€™s cards.",
        )
        @app_commands.describe(
            query="Flask or monster name",
            level="Optional flask level (otherwise its first available level)",
        )
        @app_commands.checks.cooldown(
            1, 2.0, key=lambda interaction: interaction.user.id
        )
        async def show(
            interaction: discord.Interaction,
            query: str,
            level: app_commands.Range[int, 1, 4] | None = None,
        ):
            await interaction.response.defer(thinking=True)
            await lookup_response(
                self.catalog,
                query,
                interaction.user.id,
                interaction.followup.send,
                level,
            )

        @show.autocomplete("query")
        async def autocomplete(interaction, current: str):
            if not current.strip():
                return []
            matches, _ = self.catalog.search(current)
            return [
                app_commands.Choice(
                    name=(("Card: " if m.kind == "card" else "Monster: ") + m.label)[
                        :100
                    ],
                    value=m.key,
                )
                for m in matches[:25]
            ]

        @group.command(
            name="build",
            description="Show the saved team in an exported FLASK build JSON file.",
        )
        @app_commands.describe(
            file="Optional exported JSON file",
            code="The FB1. build code copied by Share Build.cmd",
        )
        @app_commands.checks.cooldown(
            1, 5.0, key=lambda interaction: interaction.user.id
        )
        async def build(
            interaction: discord.Interaction,
            file: discord.Attachment | None = None,
            code: str | None = None,
        ):
            await interaction.response.defer(thinking=True)
            async with self.build_lock:
                await build_response(
                    self.catalog,
                    self.build_catalog,
                    file,
                    interaction.user.id,
                    interaction.followup.send,
                    code,
                )

        def add_commands(parent):
            @parent.command(name="help", description="Show commands and examples.")
            @app_commands.describe(
                command="Optional command to explain: info, infuser, party, monsters, encounters"
            )
            async def help_command(interaction: discord.Interaction, command: str = ""):
                await interaction.response.send_message(help_text(command))

            @parent.command(
                name="info",
                description="Look up a flask, infuser, monster, or event, or browse a list.",
            )
            @app_commands.describe(
                query="Name, infuser <name>, or flasks / monsters / encounters",
                level="Optional flask level",
            )
            @app_commands.checks.cooldown(
                1, 2.0, key=lambda interaction: interaction.user.id
            )
            async def info(
                interaction: discord.Interaction,
                query: str,
                level: app_commands.Range[int, 1, 4] | None = None,
            ):
                await interaction.response.defer(thinking=True)
                await info_response(
                    self.catalog,
                    query,
                    interaction.user.id,
                    interaction.followup.send,
                    level,
                )

            @info.autocomplete("query")
            async def info_autocomplete(interaction, current: str):
                if not current.strip():
                    return []
                query = (
                    current
                    if re.match(
                        r"^(?:infuser|card|flask|monster|event|encounter)\s+",
                        current,
                        re.I,
                    )
                    else "info " + current
                )
                matches, _ = self.catalog.search(query)
                return [
                    app_commands.Choice(
                        name=f"{m.kind.title()}: {m.label}"[:100],
                        value=m.key,
                    )
                    for m in matches[:25]
                ]

            @parent.command(
                name="monster",
                description="Show a monsterâ€™s flask cards and descriptions.",
            )
            @app_commands.checks.cooldown(
                1, 2.0, key=lambda interaction: interaction.user.id
            )
            async def monster(interaction: discord.Interaction, query: str = ""):
                await interaction.response.defer(thinking=True)
                await monster_response(
                    self.catalog, query, interaction.user.id, interaction.followup.send
                )

            @monster.autocomplete("query")
            async def monster_autocomplete(interaction, current: str):
                if not current.strip():
                    return []
                matches, _ = self.catalog.search("monster " + current)
                return [
                    app_commands.Choice(name=m.label[:100], value=str(m.item["id"]))
                    for m in matches[:25]
                ]

            @parent.command(name="monsters", description="List every monster fight.")
            async def monsters(interaction: discord.Interaction):
                await list_response(
                    self.catalog,
                    "monster",
                    interaction.user.id,
                    interaction.response.send_message,
                )

            @parent.command(
                name="encounters", description="List special encounters by biome."
            )
            async def encounters(interaction: discord.Interaction):
                await list_response(
                    self.catalog,
                    "event",
                    interaction.user.id,
                    interaction.response.send_message,
                )

            @parent.command(
                name="encounter",
                description="Show a special encounter, its biome and vendor artwork.",
            )
            async def event(interaction: discord.Interaction, query: str):
                await interaction.response.defer(thinking=True)
                await lookup_response(
                    self.catalog,
                    "event " + query,
                    interaction.user.id,
                    interaction.followup.send,
                )

            @parent.command(
                name="party",
                description="Display a saved party from a FLASK build code or exported JSON.",
            )
            @app_commands.describe(
                code="Full FB1. code from FLASK Share Build",
                file="Optional exported JSON instead of a code",
            )
            @app_commands.checks.cooldown(
                1, 5.0, key=lambda interaction: interaction.user.id
            )
            async def party(
                interaction: discord.Interaction,
                code: str | None = None,
                file: discord.Attachment | None = None,
            ):
                await interaction.response.defer(thinking=True)
                async with self.build_lock:
                    await build_response(
                        self.catalog,
                        self.build_catalog,
                        file,
                        interaction.user.id,
                        interaction.followup.send,
                        code,
                    )

        add_commands(group)
        self.tree.add_command(group)
        self.tree.on_error = self.command_error

    async def setup_hook(self):
        if self.catalog.library:
            self.library_task = asyncio.create_task(self.refresh_library())
        if self.guild_id:
            guild = discord.Object(id=self.guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def refresh_library(self):
        while True:
            await asyncio.sleep(900)
            try:
                old = self.catalog
                if not old.library:
                    continue
                snapshot = await asyncio.to_thread(old.library.client.refresh)
                if snapshot.revision == old.library.revision:
                    continue
                catalog = await asyncio.to_thread(Catalog, snapshot=snapshot)
                builds = BuildCatalog(root=catalog.root, snapshot=snapshot)
                async with self.build_lock:
                    self.catalog, self.build_catalog = catalog, builds
                LOG.info(
                    "Library updated to %s (%s).",
                    catalog.version,
                    snapshot.revision[:12],
                )
            except Exception:
                LOG.exception("Library refresh failed; keeping the current data.")

    async def close(self):
        if self.library_task:
            self.library_task.cancel()
            try:
                await self.library_task
            except asyncio.CancelledError:
                pass
        await super().close()

    async def on_ready(self):
        LOG.info(
            "Online as %s. Loaded %d cards, %d monster fights, %d infusers, and %d special encounters.",
            self.user,
            len(self.catalog.cards),
            len(self.catalog.monsters),
            len(self.catalog.infusers),
            len(self.catalog.events),
        )

    async def command_error(self, interaction, error):
        if isinstance(error, app_commands.CommandOnCooldown):
            message = "Please wait a couple of seconds before another lookup."
        else:
            LOG.error(
                "Slash command failed",
                exc_info=(type(error), error, error.__traceback__),
            )
            message = "The lookup failed. Check the bot console for details."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    async def on_message(self, message):
        if not self.text_commands or message.author.bot:
            return
        help_request = re.fullmatch(
            r"\s*(?:flask|flash)\s+help(?:\s+(.*))?\s*", message.content, re.I
        )
        if help_request:
            await message.channel.send(help_text(help_request[1] or ""))
            return
        short_request = re.fullmatch(
            r"\s*(?:flask|flash)\s+(info|monster)(?:\s+(.*))?\s*", message.content, re.I
        )
        if short_request and (
            not short_request[2]
            or short_request[2].strip().lower() in ("infuser", "infusers", *LIST_KINDS)
        ):
            if short_request[1].lower() == "info":
                await info_response(
                    self.catalog,
                    short_request[2] or "",
                    message.author.id,
                    message.channel.send,
                )
            else:
                await monster_response(
                    self.catalog,
                    short_request[2] or "",
                    message.author.id,
                    message.channel.send,
                )
            return
        build_request = re.fullmatch(
            r"\s*(?:flask|flash)\s+(?:party|build|deck)(?:\s+(\S+))?\s*",
            message.content,
            re.I,
        )
        if build_request:
            now = time.monotonic()
            if now - self.last_lookup.get(message.author.id, 0) < 5:
                return
            self.last_lookup[message.author.id] = now
            try:
                async with self.build_lock:
                    await build_response(
                        self.catalog,
                        self.build_catalog,
                        message.attachments[0] if message.attachments else None,
                        message.author.id,
                        message.channel.send,
                        build_request[1],
                    )
            except discord.Forbidden:
                LOG.warning("Cannot send build: check channel permissions.")
            return
        request = parse_message(message.content)
        if request is None:
            return
        now = time.monotonic()
        if now - self.last_lookup.get(message.author.id, 0) < 2:
            return
        self.last_lookup[message.author.id] = now
        if len(self.last_lookup) > 10000:
            self.last_lookup = {
                k: v for k, v in self.last_lookup.items() if now - v < 60
            }
        query, level = request
        try:
            await lookup_response(
                self.catalog, query, message.author.id, message.channel.send, level
            )
        except discord.Forbidden:
            LOG.warning(
                "Cannot send lookup in channel %s: check Send Messages, Embed Links, and Attach Files permissions.",
                message.channel.id,
            )


def main():
    parser = argparse.ArgumentParser(description="FLASK card and monster lookup bot")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate all catalog lookups without logging into Discord",
    )
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    catalog = Catalog()
    if args.check:
        for match in catalog.matches:
            for page in range(catalog.pages(match)):
                embeds, files = payload(catalog, match, page)
                assert len(embeds) <= 10 and sum(len(e) for e in embeds) <= 6000
                for file in files:
                    file.close()
        print(
            f"OK: {len(catalog.cards)} flask cards, {len(catalog.monsters)} monsters, and {len(catalog.infusers)} infusers. No Discord connection made."
        )
        return
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token or token == "paste_your_bot_token_here":
        raise SystemExit(
            "Add your Discord bot token to .env first. See README.md. Never share that file."
        )
    text = os.getenv("TEXT_COMMANDS", "true").lower() in ("true", "1", "yes")
    guild = os.getenv("DISCORD_GUILD_ID", "").strip()
    if guild and not guild.isdecimal():
        raise SystemExit("DISCORD_GUILD_ID must be a numeric server ID, or empty.")
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    client = FlaskBot(
        catalog, text_commands=text, guild_id=int(guild) if guild else None
    )
    try:
        client.run(token, log_handler=None)
    except discord.PrivilegedIntentsRequired:
        raise SystemExit(
            "Enable Message Content Intent in the Discord Developer Portal, or set TEXT_COMMANDS=false for slash commands only."
        )
    except discord.LoginFailure:
        raise SystemExit(
            "Discord rejected the bot token. Update DISCORD_TOKEN in .env."
        )


if __name__ == "__main__":
    main()
