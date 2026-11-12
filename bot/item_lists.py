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
INFUSER_RARITY_NAMES = ("Common", "Rare", "Epic", "Event", "Guaranteed")
INFUSER_CHANCES = ((100, 0, 0), (60, 40, 0), (30, 70, 0), (0, 80, 20), (0, 50, 50))


def snack_matches(snack, selected):
    effects = {effect["name"] for effect in snack["effects"]}
    if selected == "All":
        return True
    if selected == "Health only":
        return snack["health_bonus"] > 0 and not effects
    if selected == "Other effects":
        return bool(effects - {"Strength", "Armor", "Struggle", "Flourish", "Taunt"})
    return selected in effects


def item_pages(catalog, kind, emojis, selected="All", biome=False):
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
        for biome_number, rarities in BIOME_RARITIES.items():
            groups.append(
                (
                    f"Biome {biome_number}",
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
        sections = [
            (title + " · Biomes 1–3", groups[:3]),
            (title + " · Biomes 4–5 and rewards", groups[3:]),
        ]
        if not biome:
            sections = [(title, [("", snacks)])]
    else:
        infusers = sorted(
            catalog.infusers.values(),
            key=lambda item: (item.get("rarity", 0), item["name"].casefold()),
        )
        biome_groups = []
        for biome_number, chances in enumerate(INFUSER_CHANCES, 1):
            odds = " · ".join(
                f"{INFUSER_RARITY_NAMES[rarity]} {chance}%"
                for rarity, chance in enumerate(chances)
                if chance
            )
            items = [
                item
                for item in infusers
                if item.get("rarity", 0) < 3 and chances[item.get("rarity", 0)]
            ]
            groups = [(f"Biome {biome_number} · {odds}", items)]
            if biome_number == 5:
                groups.append(
                    (
                        "Special rewards · Not in normal random rolls",
                        [item for item in infusers if item.get("rarity", 0) >= 3],
                    )
                )
            biome_groups.extend(groups)
        sections = [
            ("**Infusers** · Biomes 1–3", biome_groups[:3]),
            ("**Infusers** · Biomes 4–5 and rewards", biome_groups[3:]),
        ]
        if not biome:
            sections = [("**Infusers**", [("", infusers)])]
    pages = []
    for title, section_groups in sections:
        chunks = []
        body = title + "\n"
        for heading, items in section_groups:
            for index, item in enumerate(items):
                icon = emojis.get(f"{kind}:{item['id']}", "")
                rarity = ""
                if kind == "infuser":
                    rarity = f" ({INFUSER_RARITY_NAMES[item.get('rarity', 0)]})"
                elif item["normal"]:
                    rarity = f" ({RARITY_NAMES[item['rarity']]})"
                else:
                    rarity = " (Special reward)"
                row = (
                    f"{icon} **{item['name']}**{rarity} — {item['description']}".strip()
                )
                if index == 0 and heading:
                    row = f"\n## {heading}\n" + row
                if len(body) + len(row) + 1 > 1850:
                    chunks.append(body.rstrip())
                    body = ""
                body += row + "\n"
        if body.strip() == title:
            body += f"No matching {kind}s on this page."
        chunks.append(body.rstrip())
        pages.extend(chunks[index : index + 3] for index in range(0, len(chunks), 3))
    return pages
