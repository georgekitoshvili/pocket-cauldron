"""Compact snack and infuser lists for Discord."""

SNACK_FILTERS = (
    "All",
    "Strength",
    "Armor",
    "Health only",
    "Struggle",
    "Flourish",
    "Taunt",
    "Other effects",
)
BIOME_RARITIES = {1: (0, 1), 2: (1, 2), 3: (1, 2), 4: (2, 3), 5: (2, 3)}
RARITY_NAMES = ("Common", "Rare", "Epic", "Legendary")


def snack_matches(snack, selected):
    effects = {effect["name"] for effect in snack["effects"]}
    if selected == "All":
        return True
    if selected == "Health only":
        return snack["health_bonus"] > 0 and not effects
    if selected == "Other effects":
        return bool(effects - {"Strength", "Armor", "Struggle", "Flourish", "Taunt"})
    return selected in effects


def item_pages(catalog, kind, emojis, selected="All"):
    groups = []
    if kind == "snack":
        snacks = sorted(
            (
                snack
                for snack in catalog.snacks.values()
                if snack_matches(snack, selected)
            ),
            key=lambda snack: (snack["rarity"], snack["name"].casefold()),
        )
        for biome, rarities in BIOME_RARITIES.items():
            groups.append(
                (
                    f"Biome {biome}",
                    [
                        snack
                        for snack in snacks
                        if snack["normal"] and snack["rarity"] in rarities
                    ],
                )
            )
        groups.append(
            (
                "Event and monster rewards",
                [snack for snack in snacks if not snack["normal"]],
            )
        )
        title = "**Snacks**" + (f" · {selected}" if selected != "All" else "")
    else:
        groups = [
            (
                "",
                sorted(
                    catalog.infusers.values(), key=lambda item: item["name"].casefold()
                ),
            )
        ]
        title = f"**All {len(catalog.infusers)} infusers**"
    chunks = []
    body = title + "\n"
    for heading, items in groups:
        for index, item in enumerate(items):
            icon = emojis.get(f"{kind}:{item['id']}", "")
            rarity = (
                f" ({RARITY_NAMES[item['rarity']]})"
                if kind == "snack" and item["normal"]
                else ""
            )
            row = f"{icon} **{item['name']}**{rarity} — {item['description']}".strip()
            if index == 0 and heading:
                row = f"\n## {heading}\n" + row
            if len(body) + len(row) + 1 > 1850:
                chunks.append(body.rstrip())
                body = ""
            body += row + "\n"
    if body.strip() == title:
        body += "No matching snacks."
    if body.strip():
        chunks.append(body.rstrip())
    return [chunks[index : index + 3] for index in range(0, len(chunks), 3)]
