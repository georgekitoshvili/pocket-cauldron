"""Offline lookup and presentation, shared by Discord commands and validation."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from library_client import LibraryClient

ROOT = Path(__file__).resolve().parent


def normalize(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text).casefold() if c.isalnum()
    )


@dataclass(frozen=True)
class Match:
    kind: str
    item: dict

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.item['id']}"

    @property
    def label(self) -> str:
        extra = (
            self.item.get("character")
            if self.kind == "card"
            else (
                self.item["variants"][0]["name"]
                if self.kind == "monster"
                and not self.item.get("encounter")
                and self.item["variants"]
                else ""
            )
        )
        return self.item["name"] + (
            f" · {extra}"
            if extra and normalize(extra) != normalize(self.item["name"])
            else ""
        )


class Catalog:
    def __init__(self, root: Path | None = None, snapshot=None):
        if snapshot is not None:
            self.library = snapshot
        elif root is None:
            self.library = LibraryClient("bot").ensure()
        else:
            self.library = None
        self.root = self.library.root if self.library else Path(root)
        raw = json.loads((self.root / "data/catalog.json").read_text("utf8"))
        self.version = raw["version"]
        self.cards = {c["id"]: c for c in raw["cards"]}
        self.monsters = {m["id"]: m for m in raw.get("encounters", raw["monsters"])}
        self.events = {event["id"]: event for event in raw.get("events", [])}
        self.infusers = {
            i["id"]: i
            for i in json.loads((self.root / "data/infusers.json").read_text("utf8"))
        }
        self.matches = (
            [Match("card", c) for c in self.cards.values()]
            + [Match("monster", m) for m in self.monsters.values()]
            + [Match("infuser", i) for i in self.infusers.values()]
            + [Match("event", event) for event in self.events.values()]
        )
        self.by_key = {m.key: m for m in self.matches}

    def image_path(self, rel):
        return self.library.file(rel) if self.library else self.root / rel

    def search(self, query: str) -> tuple[list[Match], bool]:
        query = query.strip()
        if query in self.by_key:
            return [self.by_key[query]], True
        kind = None
        typed = re.match(
            r"^(card|flask|monster|event|encounter|infuser|info)\s+(.+)$", query, re.I
        )
        if typed:
            kind = {"flask": "card", "encounter": "event"}.get(
                typed[1].lower(), typed[1].lower()
            )
            query = typed[2]
        candidates = [
            m
            for m in self.matches
            if kind is None
            or m.kind == kind
            or kind == "info"
            and m.kind in ("card", "infuser", "monster", "event")
        ]
        needle = normalize(query.lstrip("#"))
        if not needle:
            return [], False
        exact = [
            m
            for m in candidates
            if any(normalize(a) == needle for a in [m.item["name"], *m.item["aliases"]])
            or str(m.item["id"]) == needle
        ]
        if exact:
            return exact, True
        partial = [
            m
            for m in candidates
            if any(needle in normalize(a) for a in [m.item["name"], *m.item["aliases"]])
        ]
        if partial:
            return (
                sorted(
                    partial,
                    key=lambda m: (
                        len(normalize(m.item["name"])),
                        m.item["name"],
                        m.key,
                    ),
                ),
                False,
            )
        ranked = sorted(
            (
                (
                    max(
                        SequenceMatcher(None, needle, normalize(a)).ratio()
                        for a in [m.item["name"], *m.item["aliases"]]
                    ),
                    m,
                )
                for m in candidates
            ),
            key=lambda p: p[0],
            reverse=True,
        )
        return [m for score, m in ranked[:10] if score >= 0.55], False

    def description(self, card: dict, level: int) -> str:
        if str(level) not in card["descriptions"]:
            raise ValueError(
                f"{card['name']} is available at levels {card['available_level']}–4."
            )
        return card["descriptions"][str(level)]

    def pages(self, match: Match) -> int:
        if match.kind != "monster":
            return 1
        if match.item.get("encounter"):
            return len(self.encounter_pages(match.item))
        return (
            sum(
                max(1, (len(self.group_cards(v)) + 2) // 3)
                for v in match.item["variants"]
            )
            or 1
        )

    @staticmethod
    def group_cards(variant: dict) -> list[dict]:
        groups = OrderedDict()
        for card in variant["cards"]:
            key = (card["id"], card["level"], tuple(card.get("infusers", [])))
            if key not in groups:
                groups[key] = {**card, "slots": []}
            groups[key]["slots"].append(card["slot"])
        return list(groups.values())

    def page(
        self, match: Match, index: int = 0, level: int | None = None
    ) -> list[dict]:
        """Presentation objects; each becomes one embed and optional attachment."""
        if match.kind == "monster" and match.item.get("encounter"):
            if level is not None:
                raise ValueError("Fight flasks use their configured levels.")
            pages = self.encounter_pages(match.item)
            return pages[index % len(pages)]
        if match.kind == "event":
            if level is not None:
                raise ValueError("Levels apply to flask cards, not events.")
            event = match.item
            return [
                dict(
                    title=event["name"]
                    + (" · Special encounter" if event.get("biome") else " · Event"),
                    description=event["description"],
                    image=event.get("image"),
                    small=False,
                    fields=(
                        [("Where to encounter", event["location"])]
                        if event.get("location")
                        else []
                    )
                    + (
                        [("Availability", "Disabled in this game build")]
                        if event.get("disabled")
                        else []
                    ),
                    footer=f"FLASK Demo {self.version} · Event #{event['id']}",
                )
            ]
        if match.kind == "infuser":
            if level is not None:
                raise ValueError(
                    "Levels apply to flask cards; infusers have a fixed effect."
                )
            i = match.item
            return [
                dict(
                    title=i["name"] + " · Infuser",
                    description=i["description"],
                    image=i["image"],
                    small=True,
                    fields=[],
                    footer=f"FLASK Demo {self.version} · Infuser #{i['id']}",
                )
            ]
        if match.kind == "card":
            c = match.item
            level = c["available_level"] if level is None else level
            desc = self.description(c, level)
            details = [
                ("Class", c.get("character") or "Neutral / monster"),
                ("Elements", ", ".join(c["elements"]) or "None"),
            ]
            return [
                dict(
                    title=f"{c['name']} · Level {level}",
                    description=desc,
                    image=c["image"],
                    small=False,
                    fields=details,
                    footer=f"FLASK Demo {self.version} · Flask #{c['id']} · Base values",
                )
            ]
        total = self.pages(match)
        index %= total
        variants = match.item["variants"]
        for n, v in enumerate(variants):
            groups = self.group_cards(v)
            count = max(1, (len(groups) + 2) // 3)
            if index < count:
                break
            index -= count
        else:
            raise ValueError("No monster variants in the database.")
        health = ""
        if v["health"] is not None:
            h, var = v["health"], v["health_variance"]
            health = f"HP: {h-var}–{h+var}" if var else f"HP: {h}"
        note = "\n".join(
            x
            for x in [
                v["name"] if len(variants) > 1 else "",
                health,
                "Flask order is randomized." if v["random_order"] else "",
            ]
            if x
        )
        if v["source"] == "bestiary":
            note += "\nMonster-book card list."
        if not groups:
            note += "\nNo flask cards are configured for this monster in this demo."
        result = [
            dict(
                title=match.item["name"],
                description=note.strip(),
                image=match.item["image"],
                small=True,
                fields=[],
                footer=f"FLASK Demo {self.version} · Loadout {n+1}/{len(variants)} · {len(v['cards'])} flasks",
            )
        ]
        for group in groups[index * 3 : index * 3 + 3]:
            c = self.cards[group["id"]]
            desc = self.description(c, group["level"])
            slots = ", ".join(str(s) for s in group["slots"])
            details = f"{'Slots' if len(group['slots'])>1 else 'Slot'} {slots}"
            if group["infusers"]:
                details += (
                    " · Infuser: "
                    + ", ".join(group["infusers"])
                    + " (description shows base values)"
                )
            result.append(
                dict(
                    title=f"{c['name']} · Level {group['level']}"
                    + (f" ×{len(group['slots'])}" if len(group["slots"]) > 1 else ""),
                    description=desc,
                    image=c["thumbnail"],
                    small=True,
                    fields=[],
                    footer=details,
                )
            )
        return result

    def encounter_pages(self, encounter: dict) -> list[list[dict]]:
        pages = []
        for number, variant in enumerate(encounter["variants"], 1):
            fields = []
            details = []
            for member in variant["members"]:
                summaries = []
                for loadout in member["variants"]:
                    groups = self.group_cards(loadout)
                    names = [
                        f"{self.cards[group['id']]['name']} (Lv {group['level']})"
                        + (
                            f" ×{len(group['slots'])}"
                            if len(group["slots"]) > 1
                            else ""
                        )
                        for group in groups
                    ]
                    summaries.append(", ".join(names) or "No configured flasks")
                    health = loadout["health"]
                    variance = loadout["health_variance"]
                    notes = []
                    if health is not None:
                        notes.append(
                            f"HP: {health - variance}–{health + variance}"
                            if variance
                            else f"HP: {health}"
                        )
                    if len(member["variants"]) > 1:
                        notes.append(loadout["name"] + " · possible loadout")
                    if loadout["random_order"]:
                        notes.append("Flask order is randomized.")
                    if loadout["source"] == "bestiary":
                        notes.append("Monster-book card list.")
                    details.append(
                        dict(
                            title=f"{member['position']}. {member['name']}",
                            description="\n".join(notes),
                            image=member.get("image"),
                            small=True,
                            fields=[],
                            footer=encounter["name"],
                        )
                    )
                    for group in groups:
                        card = self.cards[group["id"]]
                        slots = ", ".join(map(str, group["slots"]))
                        footer = (
                            f"{member['position']}. {member['name']} · Slots {slots}"
                        )
                        if group.get("infusers"):
                            footer += (
                                " · Infusers: "
                                + ", ".join(group["infusers"])
                                + " · Base values"
                            )
                        details.append(
                            dict(
                                title=f"{card['name']} · Level {group['level']}"
                                + (
                                    f" ×{len(group['slots'])}"
                                    if len(group["slots"]) > 1
                                    else ""
                                ),
                                description=self.description(card, group["level"]),
                                image=card["thumbnail"],
                                small=True,
                                fields=[],
                                footer=footer,
                            )
                        )
                summary = "\n".join(
                    f"Loadout {index}: {text}" if len(summaries) > 1 else text
                    for index, text in enumerate(summaries, 1)
                )
                fields.append(
                    (f"{member['position']}. {member['name']}", summary[:1024])
                )
            header = dict(
                title=encounter["name"] + " · Monster fight",
                description="Full enemy lineup and flasks."
                + (
                    f" Encounter variant {number}/{len(encounter['variants'])}."
                    if len(encounter["variants"]) > 1
                    else ""
                ),
                image=None,
                small=True,
                fields=fields,
                footer=f"FLASK Demo {self.version}",
            )
            current = [header]
            for detail in details:
                if (
                    len(current) == 10
                    or sum(self.embed_size(row) for row in [*current, detail]) > 5900
                ):
                    pages.append(current)
                    current = [header]
                current.append(detail)
            pages.append(current)
        return pages

    @staticmethod
    def embed_size(row: dict) -> int:
        return sum(
            len(row.get(key, "")) for key in ("title", "description", "footer")
        ) + sum(len(name) + len(value) for name, value in row.get("fields", []))


def parse_message(content: str) -> tuple[str, int | None] | None:
    match = re.match(
        r"^\s*(?:flask|flash)\s+(show|info|monster|event|encounter)(?:\s+(.*))?\s*$",
        content,
        re.I,
    )
    if not match:
        direct = re.fullmatch(r"\s*(?:flask|flash)\s+(.+?)\s*", content, re.I)
        return (direct[1], None) if direct else None
    query = (match[2] or "").strip()
    level = None
    suffix = re.search(r"\s+(?:--level|level|lvl)\s*(\d+)\s*$", query, re.I)
    if suffix:
        level = int(suffix[1])
        query = query[: suffix.start()].strip()
    if query:
        if match[1].lower() in ("monster", "event", "encounter"):
            query = match[1].lower() + " " + query
        elif match[1].lower() == "info" and not re.match(
            r"^(?:infuser|card|flask|monster|event|encounter)\s+", query, re.I
        ):
            query = "info " + query
    return query, level
