"""Compact fight pages, including monster mutations and changing loadouts."""

from discord.utils import escape_markdown


def flask_row(catalog, group, emojis, location):
    card = catalog.cards.get(group["id"])
    if card is None:
        return "Unavailable flask — effect not covered by the released catalog."
    description = escape_markdown(
        " ".join(catalog.description(card, group["level"]).split())
    )
    row = f"{emojis.get(card['id'], '🧪')} **{escape_markdown(card['name'])}** · Lv {group['level']}{location} — {description}"
    if group.get("infusers"):
        row += (
            "\nInfusers: "
            + ", ".join(escape_markdown(str(name)) for name in group["infusers"])
            + " · Base values"
        )
    return row


def loadout_sections(catalog, member, emojis):
    for number, loadout in enumerate(member["variants"], 1):
        heading = f"**{member['position']}. {escape_markdown(member['name'])}**"
        notes = []
        health = loadout.get("health")
        variance = loadout.get("health_variance", 0) or 0
        if health is not None:
            notes.append(
                f"Base HP {health - variance}–{health + variance}"
                if variance
                else f"Base HP {health}"
            )
        if len(member["variants"]) > 1:
            notes.append(f"Possible loadout {number}/{len(member['variants'])}")
        if loadout.get("random_order"):
            notes.append("Random flask order")
        if loadout.get("source") == "bestiary":
            notes.append("Listed flasks; combat slots not confirmed")
        if notes:
            heading += "\n" + " · ".join(notes)
        rows = []
        mutation = loadout.get("mutation")
        if mutation:
            rows.append(
                f"**Mutation: {escape_markdown(mutation['name'])}** — {escape_markdown(mutation['description'])}"
            )
            if mutation.get("mechanics"):
                rows.append(escape_markdown(mutation["mechanics"]))
        elif "mutation" in loadout:
            rows.append("**Mutation:** None configured.")
        for status in loadout.get("starting_statuses", []):
            rows.append(
                f"Starts with {status['amount']} **{escape_markdown(status['name'])}** — {escape_markdown(status['description'])}"
            )
        for snack in loadout.get("snacks", []):
            rows.append(
                f"**Snack: {escape_markdown(snack['name'])}** — {escape_markdown(snack['description'])}"
            )
        dynamic = loadout.get("dynamic_flasks")
        if dynamic:
            rows.append(escape_markdown(dynamic["description"]))
        for group in catalog.group_cards(loadout):
            copies = f" · ×{len(group['slots'])}" if len(group["slots"]) > 1 else ""
            location = (
                ""
                if loadout.get("source") == "bestiary"
                else f" · Slots {', '.join(map(str, group['slots']))}"
            )
            rows.append(flask_row(catalog, group, emojis, copies + location))
        yield heading, rows or ["No configured flasks."], heading
        for phase in (dynamic or {}).get("phases", []):
            phase_heading = f"**{escape_markdown(phase['name'])}** — {escape_markdown(phase['trigger'])}"
            phase_rows = []
            for card in phase["cards"]:
                if phase["selection"] == "random_per_slot":
                    location = f" · 1/{len(phase['cards'])} chance per slot"
                else:
                    location = f" · All {phase['slots']} slots"
                phase_rows.append(flask_row(catalog, card, emojis, location))
            yield phase_heading, phase_rows, heading + "\n" + phase_heading


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
            for heading, rows, context in loadout_sections(catalog, member, emojis):
                if not rows:
                    continue
                section = "\n\n" + (context if current == title else heading)
                if len(current) + len(section) + len(rows[0]) + 2 > 1800:
                    if current != title:
                        pages.append(current)
                    current = title
                    section = "\n\n" + context
                current += section
                for row in rows:
                    # Repeat monster and phase context when a section spans pages.
                    width = min(1400, 1750 - len(title) - len(context))
                    if width < 100:
                        raise ValueError("Monster heading is too long to display.")
                    for offset in range(0, len(row), width):
                        part = row[offset : offset + width]
                        if len(current) + len(part) + 2 > 1800:
                            pages.append(current)
                            current = title + "\n\n" + context + " (continued)"
                        current += "\n\n" + part
        pages.append(current)
    return [
        page + "\n\nBase HP and flask values; difficulty may modify combat stats."
        for page in pages
    ]
