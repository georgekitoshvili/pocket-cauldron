"""Keep application-owned flask emojis in sync with the shared artwork."""

import asyncio
import hashlib
import logging
import re
from io import BytesIO

import discord
from PIL import Image

LOG = logging.getLogger("flask_emojis")
OWNED_NAME = re.compile(r"^flask_(\d+)_([a-f0-9]{10})$")


def emoji_name(catalog, card):
    relative = card["thumbnail"]
    if catalog.library:
        digest = catalog.library.files[relative]["sha256"]
    else:
        digest = hashlib.sha256(catalog.image_path(relative).read_bytes()).hexdigest()
    return f"flask_{card['id']}_{digest[:10]}"


def emoji_image(catalog, card):
    with Image.open(catalog.image_path(card["thumbnail"])) as source:
        art = source.convert("RGBA")
    bounds = art.getchannel("A").getbbox()
    if bounds:
        art = art.crop(bounds)
    art.thumbnail((128, 128), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (128, 128))
    canvas.alpha_composite(art, ((128 - art.width) // 2, (128 - art.height) // 2))
    output = BytesIO()
    canvas.save(output, format="PNG", optimize=True)
    return output.getvalue()


class CardEmojis:
    def __init__(self, client):
        self.client = client
        self.values = {}
        self.lock = asyncio.Lock()

    async def sync(self, catalog):
        async with self.lock:
            try:
                existing = await self.client.fetch_application_emojis()
                names = {emoji.name: emoji for emoji in existing}
                desired = [
                    (card, await asyncio.to_thread(emoji_name, catalog, card))
                    for card in catalog.cards.values()
                ]
                wanted = {name for _, name in desired}
                # Preserve old message emojis until application capacity needs space.
                obsolete = sorted(
                    (
                        emoji
                        for emoji in existing
                        if OWNED_NAME.fullmatch(emoji.name) and emoji.name not in wanted
                    ),
                    key=lambda emoji: emoji.id,
                )
                for card, name in desired:
                    if name in names:
                        self.values[card["id"]] = str(names[name])
                LOG.info(
                    "Flask emojis available: %d/%d. Uploading missing artwork.",
                    len(self.values),
                    len(desired),
                )
                count = len(existing)
                for card, name in desired:
                    if name in names:
                        continue
                    if count >= 1990:
                        while obsolete and count >= 1950:
                            await obsolete.pop(0).delete()
                            count -= 1
                    if count >= 2000:
                        LOG.warning(
                            "Application emoji capacity reached; remaining flasks use a placeholder."
                        )
                        break
                    image = await asyncio.to_thread(emoji_image, catalog, card)
                    emoji = await self.client.create_application_emoji(
                        name=name, image=image
                    )
                    self.values[card["id"]] = str(emoji)
                    count += 1
                    if len(self.values) % 50 == 0:
                        LOG.info(
                            "Flask emojis available: %d/%d.",
                            len(self.values),
                            len(desired),
                        )
                LOG.info(
                    "Flask emoji sync complete: %d/%d.", len(self.values), len(desired)
                )
            except (discord.HTTPException, OSError, ValueError):
                LOG.exception(
                    "Flask emoji sync failed; existing emoji and text lookups remain available."
                )
