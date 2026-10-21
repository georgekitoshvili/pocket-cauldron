"""Explainable setup recommendations; these rules do not simulate combat."""

import re
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Setup:
    status: str
    reason: str
    weight: int = 3


PAYOFFS = {
    "Wildfire": (Setup("self_burn", "Burn on you increases Wildfire's damage", 8),),
    "Kiln": (Setup("self_burn", "Burn on you increases D-Drone gained", 8),),
    "Furnace": (Setup("self_burn", "Burn contributes to Furnace's shield", 6),),
    "Cryoblade": (
        Setup("enemy_burn", "Burn on the target increases Cryoblade's damage", 8),
    ),
    "Flareup": (Setup("enemy_burn", "a burning target enables double damage", 8),),
    "Thermal Sink": (
        Setup("enemy_burn", "enemy Burn increases Thermal Sink's shield", 8),
    ),
    "Shadow Toxin": (
        Setup("enemy_poison", "Poison contributes to Shadow Toxin's damage", 8),
    ),
    "Toxic Boom": (
        Setup(
            "enemy_poison",
            "Toxic Boom consumes the target's Poison for its explosion",
            8,
        ),
    ),
    "Paralyze": (Setup("enemy_poison", "Paralyze needs enemy Poison to spend", 8),),
    "Shadow Blade": (
        Setup("self_stealth", "Stealth enables Shadow Blade's double damage", 8),
    ),
    "Biding Time": (
        Setup("self_stealth", "Stealth lets Biding Time repeat on allies", 8),
    ),
    "Unleashed": (Setup("self_kunai", "Kunai determines the Strength gained", 8),),
    "Maul": (Setup("self_strength", "Maul benefits from Strength four times", 8),),
    "Shield Slam": (
        Setup("self_shield", "your Shield determines Shield Slam's damage", 8),
    ),
    "Rend": (Setup("self_shield", "your Shield increases Rend's damage", 8),),
    "Anger": (Setup("self_shield", "your Shield determines the Strength gained", 8),),
    "Fireline": (Setup("self_armor", "your Armor increases Fireline's damage", 8),),
    "Icy Wrench": (Setup("self_armor", "your Armor increases S-Drone gained", 8),),
    "Surge": (Setup("self_d-drone", "D-Drone stacks increase Surge's damage", 8),),
    "Kickstart": (
        Setup("self_s-drone", "S-Drone stacks increase Kickstart's shield", 8),
    ),
    "Patch": (Setup("self_h-drone", "H-Drone stacks increase Patch's healing", 8),),
    "Bushcraft": (
        Setup("self_flourish", "Flourish increases the Damage added to bullets", 8),
    ),
    "Lead Berry": (
        Setup("self_flourish", "Flourish determines the Burn added to your bullet", 8),
    ),
    "Toxic Bloom": (Setup("self_flourish", "Flourish increases Poison applied", 8),),
    "Broken Mind": (Setup("self_focus", "Focus enables the extra activation", 7),),
    "Keen Edge": (Setup("self_focus", "Focus enables the extra activation", 7),),
}

STATUSES = (
    "Strength",
    "Armor",
    "Shield",
    "Burn",
    "Poison",
    "Stealth",
    "Kunai",
    "Flourish",
    "Luck",
    "Focus",
    "Burst",
    "Bolstering",
    "D-Drone",
    "S-Drone",
    "H-Drone",
)


def text_at(card, level=None):
    level = card["available_level"] if level is None else level
    return card["descriptions"].get(str(level))


def attacks(text):
    return bool(
        re.search(r"(?:^|[\n.])\s*(?:\d+|X)\s+damage\b|\bdamage equal to\b", text, re.I)
    )


@lru_cache(maxsize=4096)
def produces(text):
    """Recognize explicit effects before conditional/Opener sections only."""
    text = re.split(
        r"\b(?:opener|combo|chain|gamble|execute|if|when|whenever)\b",
        text,
        maxsplit=1,
        flags=re.I,
    )[0]
    found = set()
    for effect in re.finditer(r"\b(gain|gains|give|apply)\s+([^\n.!]+)", text, re.I):
        verb, clause = effect[1].lower(), effect[2]
        prefix = re.split(r"[\n.!]", text[: effect.start()])[-1]
        if (
            verb in ("gain", "gains")
            and re.search(r"\b(?:enemy|enemies|target)\b", prefix, re.I)
            and not re.search(r"\b(?:self|you|your team)\b", prefix, re.I)
        ):
            continue
        if verb == "give" and not re.search(
            r"\b(?:your team|yourself|you)\b", clause, re.I
        ):
            continue
        own = verb != "apply" or bool(re.search(r"\bto (?:self|you)\b", clause, re.I))
        enemy = verb == "apply" and (
            not own or bool(re.search(r"\benem(?:y|ies)\b", clause, re.I))
        )
        immediate = re.split(
            r"\b(?:equal|increased|for|at|to|then|remove|lose|increase|shoot|repeat)\b|,",
            clause,
            maxsplit=1,
            flags=re.I,
        )[0]
        for part in re.split(r"&|\band\b", immediate, flags=re.I):
            for status in STATUSES:
                name = re.escape(status).replace(r"\-", "[- ]?")
                if re.match(rf"\s*(?:(?:\d+|X)\s+)?{name}\b", part, re.I):
                    if own:
                        found.add("self_" + status.lower())
                    if enemy:
                        found.add("enemy_" + status.lower())
    if re.search(r"\bapply\s+(?:\d+\s+)?vulnerable\b", text, re.I):
        found.add("enemy_vulnerable")
    if re.search(r"\bapply\s+-\d+\s+armor\b", text, re.I):
        found.add("enemy_armor_loss")
    return found


def setups(card, level=None):
    text = text_at(card, level)
    if text is None:
        return ()
    requirements = list(PAYOFFS.get(card["name"], ()))
    if attacks(text):
        requirements.extend(
            (
                Setup("self_strength", "Strength adds damage to attacks", 2),
                Setup(
                    "enemy_vulnerable",
                    "Vulnerable increases damage taken; the attack must hit that target",
                    2,
                ),
                Setup(
                    "enemy_armor_loss",
                    "lower enemy Armor helps subsequent attacks on that target",
                    2,
                ),
            )
        )
    if re.search(r"\bgamble\b", text, re.I):
        requirements.append(Setup("self_luck", "Luck improves Gamble odds", 5))
    # One reason per resource, preferring the specific interaction.
    return tuple({rule.status: rule for rule in reversed(requirements)}.values())


def message_pages(lines, limit=1850):
    pages, current = [], ""
    for line in lines:
        # Split exceptionally long descriptions without dropping text.
        for part in [line[i : i + limit] for i in range(0, len(line), limit)] or [""]:
            if current and len(current) + len(part) + 1 > limit:
                pages.append(current)
                current = ""
            current += ("\n" if current else "") + part
    if current:
        pages.append(current)
    return pages or ["No suggestions."]


def pair_reasons(before, after, catalog):
    source = catalog.cards[before["id"]]
    target = catalog.cards[after["id"]]
    effects = produces(text_at(source, before["level"]))
    rules = [rule for rule in setups(target, after["level"]) if rule.status in effects]
    if 1261 in after["infusers"]:
        # Equalized replaces outgoing damage before target-side modifiers.
        rules = [
            rule
            for rule in rules
            if rule.status in ("enemy_vulnerable", "enemy_armor_loss")
        ]
    return rules
