"""Element artwork and consistent suffixes for flask descriptions."""

import json


def element_entries(catalog):
    path = catalog.root / "data/build-catalog.json"
    if not path.is_file():
        return []
    entries = json.loads(path.read_text("utf8"))
    used = {
        name for card in catalog.cards.values() for name in card.get("elements", [])
    }
    return [
        {"id": int(ident), "name": entry["name"], "thumbnail": entry["image"]}
        for ident, entry in entries.items()
        if entry.get("category") == "Element"
        and entry.get("name") in used
        and entry.get("image")
    ]


def with_elements(text, card, emojis=None):
    icons = emojis or {}
    suffix = " ".join(
        icons.get("element:" + name, f"[{name}]") for name in card.get("elements", [])
    )
    return text + (" " + suffix if suffix else "")
