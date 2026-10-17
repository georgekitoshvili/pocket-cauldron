"""Compact monster-fight pages with a separate section for every enemy."""

from discord.utils import escape_markdown


def monster_pages(catalog, monster, emojis, level=None):
    if level is not None:
        raise ValueError("Fight flasks use their configured levels.")
    variants = (
        monster["variants"]
        if monster.get("encounter")
        else [
            dict(
                members=[
                    dict(position=1, name=monster["name"], variants=monster["variants"])
                ]
            )
        ]
    )
    pages = []
    for number, variant in enumerate(variants, 1):
        title = f"**{escape_markdown(monster['name'])}**"
        if len(variants) > 1:
            title += f" · Variant {number}/{len(variants)}"
        current = title
        for member in variant["members"]:
            for loadout_number, loadout in enumerate(member["variants"], 1):
                heading = f"**{member['position']}. {escape_markdown(member['name'])}**"
                notes = []
                health = loadout.get("health")
                variance = loadout.get("health_variance", 0) or 0
                if health is not None:
                    notes.append(
                        f"HP {health - variance}–{health + variance}"
                        if variance
                        else f"HP {health}"
                    )
                if len(member["variants"]) > 1:
                    notes.append(
                        f"Possible loadout {loadout_number}/{len(member['variants'])}"
                    )
                if loadout.get("random_order"):
                    notes.append("Random flask order")
                if loadout.get("source") == "bestiary":
                    notes.append("Monster-book card list")
                if notes:
                    heading += "\n" + " · ".join(notes)
                groups = catalog.group_cards(loadout)
                rows = []
                for group in groups:
                    card = catalog.cards.get(group["id"])
                    if card is None:
                        rows.append(
                            "Unavailable flask — effect not covered by the released catalog."
                        )
                        continue
                    slots = ", ".join(map(str, group["slots"]))
                    copies = (
                        f" · ×{len(group['slots'])}" if len(group["slots"]) > 1 else ""
                    )
                    description = escape_markdown(
                        " ".join(catalog.description(card, group["level"]).split())
                    )
                    row = f"{emojis.get(card['id'], '🧪')} **{escape_markdown(card['name'])}** · Lv {group['level']}{copies} · Slots {slots} — {description}"
                    if group.get("infusers"):
                        row += (
                            "\nInfusers: "
                            + ", ".join(
                                escape_markdown(str(name)) for name in group["infusers"]
                            )
                            + " · Base values"
                        )
                    rows.append(row)
                if not rows:
                    rows = ["No configured flasks."]
                section = "\n\n" + heading
                if len(current) + len(section) + len(rows[0]) + 2 > 1850:
                    if current != title:
                        pages.append(current)
                    current = title
                current += section
                for row in rows:
                    # Keep every character's heading on continuation pages too.
                    for offset in range(0, len(row), 1400):
                        part = row[offset : offset + 1400]
                        if len(current) + len(part) + 2 > 1850:
                            pages.append(current)
                            current = title + "\n\n" + heading + " (continued)"
                        current += "\n\n" + part
        pages.append(current)
    return [page + "\n\nBase values" for page in pages]
