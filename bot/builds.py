"""Build presentation for the bot; portable codes live in build_protocol.py."""

import io
import json
import textwrap
from pathlib import Path

from build_protocol import validate_build
from library_client import LibraryClient, LibraryError


class BuildCatalog:
    def __init__(self, root=None, snapshot=None):
        if snapshot is not None:
            self.library = snapshot
        elif root is None:
            self.library = LibraryClient("bot").ensure()
        else:
            self.library = None
        self.root = self.library.root if self.library else Path(root)
        self.entries = json.loads(
            (self.root / "data/build-catalog.json").read_text("utf8")
        )
        self.cards = {
            card["id"]: card
            for card in json.loads((self.root / "data/catalog.json").read_text("utf8"))[
                "cards"
            ]
        }

    def name(self, ident):
        return self.entries.get(str(ident), {}).get("name", f"Unknown #{ident}")

    def image(self, ident):
        rel = self.entries.get(str(ident), {}).get("image")
        if not rel:
            return None
        try:
            target = (
                self.library.file(rel) if self.library else self.root / rel
            ).resolve()
        except (OSError, LibraryError):
            return None
        if not target.is_relative_to((self.root / "assets").resolve()):
            raise ValueError("Invalid bundled image path.")
        return target if target.is_file() else None

    def summary(self, build):
        team = build["build"]
        lines = []
        tokens = ", ".join(
            f"{self.name(t['elementId'])} x{t['amount']}"
            for t in team["elementTokens"]
            if t["amount"]
        )
        if tokens:
            lines.append("Elements: " + tokens)
        lines.append(
            "A saved team snapshot. Flask descriptions use base values; infuser effects and battle buffs are not recalculated."
        )
        return "\n".join(lines)

    def character_text(self, character):
        lines = [f"HP: {character['hp']}"]
        if character["mutation"] != -1:
            lines.append("Mutation: " + self.name(character["mutation"]))
        if character["snacks"]:
            lines.append(
                "Snacks: " + ", ".join(self.name(n) for n in character["snacks"])
            )
        for slot, flask in enumerate(character["flasks"], 1):
            if flask is None:
                lines.append(f"{slot}. Empty")
                continue
            line = f"{slot}. {self.name(flask['id'])} - Lv {flask['level']}"
            if flask["infusers"]:
                line += " [" + ", ".join(self.name(n) for n in flask["infusers"]) + "]"
            lines.append(line)
        return "\n".join(lines)

    def render(self, build):
        from PIL import Image, ImageDraw, ImageFont

        build = validate_build(build)
        characters = build["build"]["characters"]
        width = 1200
        row_height = 365
        height = 130 + row_height * len(characters)
        canvas = Image.new("RGB", (width, height), "#15131d")
        draw = ImageDraw.Draw(canvas)
        font = ImageFont.load_default(size=18)
        small = ImageFont.load_default(size=14)
        heading = ImageFont.load_default(size=27)

        def text(x, y, value, text_font=font, color="#f0e8dc", columns=34, limit=3):
            lines = textwrap.wrap(value, width=columns, break_long_words=True) or [""]
            for i, line in enumerate(lines[:limit]):
                draw.text((x, y + i * 22), line, font=text_font, fill=color)

        def picture(ident, box):
            path = self.image(ident)
            if path:
                with Image.open(path) as im:
                    im = im.convert("RGBA")
                    im.thumbnail((box[2] - box[0], box[3] - box[1]))
                    canvas.paste(
                        im,
                        (
                            box[0] + (box[2] - box[0] - im.width) // 2,
                            box[1] + (box[3] - box[1] - im.height) // 2,
                        ),
                        im,
                    )

        draw.text(
            (24, 18), "Pocket Cauldron - exported build", font=heading, fill="#efd2a3"
        )
        tokens = " | ".join(
            f"{self.name(t['elementId'])} x{t['amount']}"
            for t in build["build"]["elementTokens"]
            if t["amount"]
        )
        text(24, 58, tokens, small, columns=150, limit=2)
        draw.text(
            (24, 105),
            "Saved snapshot | Slots left to right | Levels and infusers shown; base effects are not recalculated",
            font=small,
            fill="#bdb3cb",
        )
        for i, character in enumerate(characters):
            y = 130 + i * row_height
            draw.rounded_rectangle(
                (12, y + 5, 1188, y + row_height - 6), radius=12, fill="#282332"
            )
            picture(character["id"], (20, y + 45, 190, y + 235))
            text(24, y + 12, self.name(character["id"]), font, columns=18, limit=1)
            text(26, y + 240, f"HP {character['hp']}", font, columns=18, limit=1)
            extra = []
            if character["mutation"] != -1:
                extra.append("Mutation: " + self.name(character["mutation"]))
            if character["snacks"]:
                extra.append(
                    "Snacks: " + ", ".join(self.name(n) for n in character["snacks"])
                )
            text(26, y + 270, " / ".join(extra), small, columns=23, limit=3)
            slots = character["flasks"]
            slot_count = max(4, len(slots))
            cell = 965 / slot_count
            for j, flask in enumerate(slots):
                x = int(205 + j * cell)
                cell_width = int(cell - 10)
                draw.rounded_rectangle(
                    (x, y + 15, x + cell_width, y + row_height - 22),
                    radius=8,
                    fill="#1c1924",
                )
                draw.text((x + 8, y + 22), f"Slot {j+1}", font=small, fill="#bdb3cb")
                if flask is None:
                    draw.text((x + 8, y + 150), "Empty", font=font, fill="#bdb3cb")
                    continue
                picture(flask["id"], (x + 5, y + 50, x + cell_width - 5, y + 218))
                columns = max(7, int(cell_width / 10))
                text(
                    x + 8,
                    y + 220,
                    self.name(flask["id"]),
                    font,
                    columns=columns,
                    limit=2,
                )
                text(
                    x + 8,
                    y + 265,
                    f"Level {flask['level']}",
                    small,
                    columns=columns,
                    limit=1,
                )
                if flask["infusers"]:
                    text(
                        x + 8,
                        y + 289,
                        ", ".join(self.name(n) for n in flask["infusers"]),
                        small,
                        color="#c9acf0",
                        columns=columns,
                        limit=2,
                    )
        result = io.BytesIO()
        canvas.save(result, format="PNG")
        result.seek(0)
        return result
