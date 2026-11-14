"""Class, element and keyword filters with compact, plain-text card pages."""

import re
from dataclasses import dataclass, replace

from discord.utils import escape_markdown
from element_icons import with_elements
from lookup import normalize

KEYWORD_ALIASES = {
    "Strength": ("strength",),
    "Focus": ("focus",),
    "Burn": ("burn", "fire"),
    "Poison": ("poison",),
    "Control": ("control",),
    "Taunt": ("taunt",),
    "Spirit": ("spirit", "spirits"),
    "Beetle Spirit": ("beetle spirit", "beetle"),
    "Jaybird Spirit": ("jaybird spirit", "jaybird"),
    "Viper Spirit": ("viper spirit", "viper"),
    "Wolverine Spirit": ("wolverine spirit", "wolverine"),
    "Spikes": ("spikes", "spike", "thorns", "thorn"),
    "Stealth": ("stealth",),
    "Negative Strength": (
        "negative strength",
        "-strength",
        "minus strength",
        "strength reduction",
    ),
    "Chain": ("chain",),
    "Combo": ("combo",),
    "Echo": ("echo",),
    "Gamble": ("gamble", "gambling"),
    "Luck": ("luck",),
    "Kunai": ("kunai",),
    "Drone": ("drone", "drones"),
    "D-Drone": ("d-drone", "d-drones"),
    "S-Drone": ("s-drone", "s-drones"),
    "H-Drone": ("h-drone", "h-drones"),
    "R-Drone": ("r-drone", "r-drones"),
    "Heat": ("heat",),
    "Frost": ("frost", "cold"),
    "Totem": ("totem", "totems"),
    "Exhaust": ("exhaust",),
    "Armor": ("armor", "armour"),
    "Damage": ("damage", "strike", "strikes"),
    "Shield": ("shield", "shields"),
    "Health": ("health", "healing", "heal"),
    "Lifesteal": ("lifesteal", "life steal"),
    "Lock": ("lock", "locked"),
    "Eternal": ("eternal", "ethernal"),
    "Flourish": ("flourish", "regen", "regenerate", "regeneration"),
    "Regrowth": ("regrowth", "regrow"),
    "Burst": ("burst",),
    "Bolstering": ("bolstering", "bolster"),
}

KEYWORD_PATTERNS = {
    "Spirit": r"\bspirits?\b",
    "Taunt": r"\btaunts?\b",
    "Drone": r"\b(?:[DSHR][-\s–—‑]?drones?|drones?)\b",
    "D-Drone": r"\bD[-\s–—‑]?drones?\b",
    "S-Drone": r"\bS[-\s–—‑]?drones?\b",
    "H-Drone": r"\bH[-\s–—‑]?drones?\b",
    "R-Drone": r"\bR[-\s–—‑]?drones?\b",
    "Health": r"\b(?:health|heal(?:s|ed|ing)?)\b",
    "Totem": r"\btotems?\b",
    "Burn": r"\bburn(?:ed|s|ing)?\b",
    "Poison": r"\bpoison(?:ed|s|ing)?\b",
    "Spikes": r"\b(?:spikes?|thorns?)\b",
    "Chain": r"\bchain(?:ed|s)?\b",
    "Echo": r"\becho(?:ed|es)?\b",
    "Gamble": r"\bgambl(?:e[sd]?|ing)\b",
    "Exhaust": r"\bexhaust(?:ed|s|ing)?\b",
    "Armor": r"\barmou?r\b",
    "Shield": r"\bshields?\b",
    "Lifesteal": r"\blife[ -]?steal\b",
    "Lock": r"\b(?:un)?lock(?:ed|s|ing)?\b",
}


def filter_key(text):
    return normalize(
        re.sub(r"(?<!\w)[-−]\s*strength\b", "negative strength", text, flags=re.I)
    )


def resolve_keyword(text):
    needle = filter_key(text)
    for keyword, aliases in KEYWORD_ALIASES.items():
        if needle in {filter_key(alias) for alias in (keyword, *aliases)}:
            return keyword
    return None


def reduces_strength(text):
    return bool(
        re.search(
            r"[-−]\s*(?:\d+(?:\.\d+)?|X)\s*%?\s*strength\b"
            r"|\b(?:lose|loses|remove|removes|steal|steals)\s+(?:all\s+|\d+\s+|your\s+|their\s+)*strength\b"
            r"|\b(?:reduce|reduces|decrease|decreases)\s+(?:(?:all|your|their|enemy)\s+)*strength\b"
            r"|\bstrength\s+(?:is|gets)\s+(?:reduced|decreased)\b",
            text,
            re.I,
        )
    )


def matches_keyword(catalog, card, keyword, level):
    text = catalog.description(card, level)
    if keyword == "Negative Strength":
        return reduces_strength(text)
    if keyword == "Stealth" and reduces_strength(text):
        return True
    pattern = KEYWORD_PATTERNS.get(keyword, rf"\b{re.escape(keyword)}\b")
    return bool(re.search(pattern, text, re.I))


@dataclass(frozen=True)
class CardFilter:
    character: str | None = None
    element: str | None = None
    keyword: str | None = None
    starting_level: int | None = None

    @property
    def label(self):
        label = " · ".join(
            value for value in (self.character, self.element, self.keyword) if value
        )
        if self.starting_level is not None:
            return " · ".join(
                filter(None, (label, f"Starts at level {self.starting_level}"))
            )
        return label


def filter_names(catalog):
    classes = sorted(
        {card["character"] for card in catalog.cards.values() if card.get("character")}
        | {"Neutral"}
    )
    elements = sorted(
        {element for card in catalog.cards.values() for element in card["elements"]}
    )
    return classes, elements


def parse_filter(catalog, query):
    query = re.sub(r"\bflasks?\b", "", query, flags=re.I).strip()
    query = re.sub(r"\b(?:artifacter|artrifacter)\b", "Artificer", query, flags=re.I)
    starting = re.search(r"\bstarting\s+(?:level\s+)?(\d+)\b", query, re.I)
    if starting:
        number = int(starting[1])
        if number not in range(1, 5):
            raise ValueError("Starting levels are 1–4.")
        remainder = (query[: starting.start()] + " " + query[starting.end() :]).strip()
        selection = parse_filter(catalog, remainder) if remainder else CardFilter()
        if selection is not None:
            return replace(selection, starting_level=number)
        return None
    needle = filter_key(query)
    if not needle:
        return None
    classes, elements = filter_names(catalog)
    for character in classes:
        if needle == normalize(character):
            return CardFilter(character=character)
        for element in elements:
            if needle in (
                normalize(character + element),
                normalize(element + character),
            ):
                return CardFilter(character, element)
    for element in elements:
        if needle == normalize(element):
            return CardFilter(element=element)
    for keyword, aliases in KEYWORD_ALIASES.items():
        for alias in aliases:
            alias_key = filter_key(alias)
            if needle == alias_key:
                return CardFilter(keyword=keyword)
            if alias_key not in needle:
                continue
            remainder = needle.replace(alias_key, "", 1)
            for character in (None, *classes):
                for element in (None, *elements):
                    if (character or element) and remainder in (
                        normalize((character or "") + (element or "")),
                        normalize((element or "") + (character or "")),
                    ):
                        return CardFilter(character, element, keyword)
    return None


def filtered_cards(catalog, selection, level=None):
    if level is not None and level not in range(1, 5):
        raise ValueError("Flask levels are 1–4.")
    if selection.starting_level is not None and selection.starting_level not in range(
        1, 5
    ):
        raise ValueError("Starting levels are 1–4.")
    return sorted(
        (
            card
            for card in catalog.cards.values()
            if (
                selection.character is None
                or (selection.character == "Neutral" and not card.get("character"))
                or card.get("character") == selection.character
            )
            and (selection.element is None or selection.element in card["elements"])
            and (
                selection.starting_level is None
                or card["available_level"] == selection.starting_level
            )
            and (level is None or str(level) in card["descriptions"])
            and (
                selection.keyword is None
                or matches_keyword(
                    catalog,
                    card,
                    selection.keyword,
                    card["available_level"] if level is None else level,
                )
            )
        ),
        key=lambda card: (card["name"].casefold(), card["id"]),
    )


def card_pages(catalog, selection, emojis, level=None):
    cards = filtered_cards(catalog, selection, level)
    heading = f"**{selection.label} · {len(cards)} flasks**\n\n"
    if not cards:
        return [heading + "No matching flasks for these filters and display level."]
    pages = []
    rows = []
    row_limit = None if selection.keyword not in (None, "Damage", "Shield") else 30
    entries = [(None, card) for card in cards]
    if selection.character == "Neutral":
        entries = [
            (f"Biome {biome}", card)
            for biome in range(1, 6)
            for card in cards
            if any(source['biome'] == biome for source in card.get('obtain_sources', []))
        ]
        entries.extend(
            ("No direct reward or merchant source", card)
            for card in cards if not card.get('obtain_sources')
        )
    previous_group = None
    for group, card in entries:
        shown_level = card["available_level"] if level is None else level
        description = escape_markdown(
            " ".join(catalog.description(card, shown_level).split())
        )
        description = with_elements(description, card, emojis)
        character = (
            f" · {card.get('character') or 'Neutral / monster'}"
            if selection.character is None
            else ""
        )
        row = (
            f"{emojis.get(card['id'], '🧪')} **{escape_markdown(card['name'])}**"
            f" (Lv {shown_level}{character}) — {description}"
        )
        if group and group.startswith('Biome '):
            biome = int(group.split()[-1])
            sources = sorted({
                f"{source['name']} (Lv {source['level']})"
                for source in card['obtain_sources'] if source['biome'] == biome
            })
            row += " · " + "; ".join(escape_markdown(source) for source in sources)
        group_heading = f"\n## {group}\n\n" if group else ""
        if group != previous_group:
            row = group_heading + row
        if len(row) + len(heading) > 1940:
            raise ValueError(
                f"{card['name']} is too long for this list. Use !flask {card['name']}."
            )
        if rows and (
            (row_limit is not None and len(rows) >= row_limit)
            or len(heading) + sum(len(value) + 1 for value in [*rows, row]) > 1940
        ):
            pages.append(heading + "\n".join(rows))
            rows = []
        rows.append(row)
        previous_group = group
    pages.append(heading + "\n".join(rows))
    note = "Base levels" if level is None else f"Level {level}"
    return [
        page + f"\n\n{note} · Base values · Page {index}/{len(pages)}"
        for index, page in enumerate(pages, 1)
    ]
