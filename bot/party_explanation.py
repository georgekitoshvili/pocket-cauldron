"""Describe saved party effects and supported flask interactions."""

import re

from advice import attacks, message_pages, pair_reasons, produces, text_at
from build_protocol import validate_build
from discord.utils import escape_markdown
from element_icons import with_elements


def explain_pages(build, catalog, build_catalog, emojis):
    build = validate_build(build)
    lines = [
        "**Your party explained**",
        "Based on your exported snapshot and current flask descriptions. Listed effects are base values; battle outcomes and modified numbers are not simulated.",
        "",
    ]
    released_classes = {card.get("character") for card in catalog.cards.values()} - {
        None
    }
    tokens = []
    for token in build["build"]["elementTokens"]:
        entry = build_catalog.entries.get(str(token["elementId"]), {})
        if token["amount"] and entry.get("category") == "Element":
            tokens.append(f"{escape_markdown(entry['name'])} ×{token['amount']}")
    if tokens:
        lines.extend(
            (
                "**Element tokens:** " + ", ".join(tokens),
                "These are token counts, not calculated team tiers; flask elements also contribute.",
                "",
            )
        )
    team_flasks = []
    for number, character in enumerate(build["build"]["characters"], 1):
        name = build_catalog.name(character["id"])
        if name not in released_classes:
            lines.extend(
                (
                    f"**{number}. Unavailable character**",
                    "This character is not covered by the released catalog.",
                    "",
                )
            )
            continue
        lines.append(
            f"**{number}. {escape_markdown(name)} · {character['hp']} saved HP**"
        )
        organ = catalog.organs.get(character["mutation"])
        if organ:
            lines.append(
                f"**Organ: {escape_markdown(organ['name'])}** — {escape_markdown(organ['description'])}"
            )
            if name not in organ["classes"]:
                lines.append(
                    "This organ's class restriction does not match the character in the snapshot."
                )
        elif character["mutation"] != -1:
            lines.append("Organ effect unavailable in the current catalog.")
        snacks = []
        for ident in character["snacks"]:
            entry = build_catalog.entries.get(str(ident), {})
            if entry.get("category") == "Snack":
                snacks.append(escape_markdown(entry["name"]))
        if snacks:
            lines.append(
                "**Snacks:** "
                + ", ".join(snacks)
                + ". Their stat effects are not recalculated."
            )
        known = []
        for slot, flask in enumerate(character["flasks"], 1):
            if flask is None:
                lines.append(f"{slot}. Empty — contributes no flask effect.")
                continue
            card = catalog.cards.get(flask["id"])
            if card is None or text_at(card, flask["level"]) is None:
                lines.append(f"{slot}. Unavailable flask — effect not covered.")
                continue
            known.append((slot, flask, card))
            lines.append(
                f"{slot}. {emojis.get(card['id'], '🧪')} **{escape_markdown(card['name'])}** · Lv {flask['level']} — {with_elements(escape_markdown(' '.join(text_at(card, flask['level']).split())), card, emojis)}"
            )
            neutralized = any(
                catalog.infusers.get(ident, {}).get("name") == "Neutralized"
                for ident in flask["infusers"]
            )
            if card.get("character") not in (None, name) and not neutralized:
                lines.append(
                    "   Class restriction mismatch: this flask needs its own class or Neutralized."
                )
            for ident in flask["infusers"]:
                infuser = catalog.infusers.get(ident)
                if infuser:
                    lines.append(
                        f"   **{escape_markdown(infuser['name'])}:** {escape_markdown(infuser['description'])}"
                    )
                else:
                    lines.append(
                        "   Infuser effect unavailable in the current catalog."
                    )
        team_flasks.extend((number, flask, card) for _, flask, card in known)
        tools = set()
        for _, flask, card in known:
            text = text_at(card, flask["level"])
            if attacks(text):
                tools.add("direct attacks")
            if re.search(r"\bshoot\b", text, re.I):
                tools.add("bullet attacks")
            if re.search(r"\bsummon\b", text, re.I):
                tools.add("summons")
            effects = produces(text)
            for tag, label in {
                "self_shield": "Shield generation",
                "self_strength": "Strength setup",
                "self_armor": "Armor generation",
                "self_flourish": "Flourish healing",
                "enemy_poison": "Poison application",
                "enemy_burn": "Burn application",
            }.items():
                if tag in effects:
                    tools.add(label)
        if tools:
            lines.append("**Main tools:** " + ", ".join(sorted(tools)) + ".")
        interactions = []
        for slot, first, first_card in known:
            for other_slot, second, second_card in known:
                if slot == other_slot:
                    continue
                for rule in pair_reasons(first, second, catalog):
                    timing = (
                        "Earlier in slot order"
                        if slot < other_slot
                        else "Later in slot order; may support a later activation"
                    )
                    interactions.append(
                        (
                            rule.weight,
                            f"• {first_card['name']} → {second_card['name']}: {rule.reason}. {timing}.",
                        )
                    )
        if interactions:
            lines.append("**Recognized interactions:**")
            lines.extend(
                escape_markdown(line)
                for _, line in sorted(interactions, key=lambda row: -row[0])[:4]
            )
        else:
            lines.append(
                "No specific setup interaction is recognized by the current rules; this does not mean the flasks lack synergy."
            )
        texts = [text_at(card, flask["level"]) for _, flask, card in known]
        if any(card["name"] == "Explosion!" for _, _, card in known):
            lines.append("**Watch out:** Explosion also hits your own team.")
        if texts and not any(
            attacks(text) or re.search(r"\bshoot\b", text, re.I) for text in texts
        ):
            lines.append(
                "No direct attack is recognized in these slots. Damage may instead come from statuses, summons, organs or allies."
            )
        if any(
            re.search(
                r"\b(?:chain|echo|combo|opener|heat|frost|lock|spirit|bullet)\b",
                text,
                re.I,
            )
            for text in texts
        ):
            lines.append(
                "Special timing and state effects are present. Slot-order notes do not simulate their activations."
            )
        lines.append("")
    team_interactions = []
    for number, first, first_card in team_flasks:
        text = text_at(first_card, first["level"])
        for other_number, second, second_card in team_flasks:
            if number == other_number:
                continue
            for rule in pair_reasons(first, second, catalog):
                team_wide = (
                    re.search(r"\b(?:your team|all allies)\b", text, re.I)
                    if rule.status.startswith("self_")
                    else re.search(r"\ball enemies\b", text, re.I)
                )
                if team_wide:
                    team_interactions.append(
                        f"• Character {number}'s {first_card['name']} can support character {other_number}'s {second_card['name']}: {rule.reason}."
                    )
    if team_interactions:
        lines.extend(
            (
                "**Across the team:**",
                *[escape_markdown(line) for line in dict.fromkeys(team_interactions)][
                    :6
                ],
                "Actual activation order and target state still matter.",
                "",
            )
        )
    return message_pages(lines)
