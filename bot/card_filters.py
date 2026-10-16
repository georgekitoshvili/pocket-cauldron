"""Class and element filters with compact, plain-text card pages."""

from dataclasses import dataclass

from discord.utils import escape_markdown
from lookup import normalize


@dataclass(frozen=True)
class CardFilter:
    character: str | None = None
    element: str | None = None

    @property
    def label(self):
        return " · ".join(value for value in (self.character, self.element) if value)


def filter_names(catalog):
    classes = sorted(
        {card["character"] for card in catalog.cards.values() if card.get("character")}
    )
    elements = sorted(
        {element for card in catalog.cards.values() for element in card["elements"]}
    )
    return classes, elements


def parse_filter(catalog, query):
    needle = normalize(query)
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
    return None


def filtered_cards(catalog, selection, level=None):
    if level is not None and level not in range(1, 5):
        raise ValueError("Flask levels are 1–4.")
    return sorted(
        (
            card
            for card in catalog.cards.values()
            if (
                selection.character is None
                or card.get("character") == selection.character
            )
            and (selection.element is None or selection.element in card["elements"])
            and (level is None or str(level) in card["descriptions"])
        ),
        key=lambda card: (card["name"].casefold(), card["id"]),
    )


def card_pages(catalog, selection, emojis, level=None):
    cards = filtered_cards(catalog, selection, level)
    heading = f"**{selection.label} · {len(cards)} flasks**\n\n"
    if not cards:
        return [heading + "No matching flasks at this level."]
    pages = []
    rows = []
    for card in cards:
        shown_level = card["available_level"] if level is None else level
        description = escape_markdown(
            " ".join(catalog.description(card, shown_level).split())
        )
        character = (
            f" · {card.get('character') or 'Neutral / monster'}"
            if selection.character is None
            else ""
        )
        row = (
            f"{emojis.get(card['id'], '🧪')} **{escape_markdown(card['name'])}**"
            f" (Lv {shown_level}{character}) — {description}"
        )
        if len(row) + len(heading) > 1900:
            raise ValueError(
                f"{card['name']} is too long for this list. Use flask info {card['name']}."
            )
        if rows and len(heading) + sum(len(value) + 1 for value in [*rows, row]) > 1900:
            pages.append(heading + "\n".join(rows))
            rows = []
        rows.append(row)
    pages.append(heading + "\n".join(rows))
    note = "Base levels" if level is None else f"Level {level}"
    return [
        page + f"\n\n{note} · Base values · Page {index}/{len(pages)}"
        for index, page in enumerate(pages, 1)
    ]
