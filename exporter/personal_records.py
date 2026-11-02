"""Personal bests recoverable from one save's retained runs. Data-only and read-only."""

from dataclasses import dataclass
from html import escape

from export_build import read_save


METRICS = {
    "Combat": {
        "highestDamage": "Largest hit",
        "highestShield": "Largest Shield gain",
        "highestHeal": "Largest heal",
        "totalDamage": "Total damage in a run",
        "totalShield": "Total Shield in a run",
        "totalHealing": "Total healing in a run",
        "damageNegated": "Damage negated in a run",
        "flasksExhausted": "Flasks exhausted in a run",
    },
    "Run totals": {
        "goblinsKilled": "Goblins killed",
        "totalBloodGained": "Bloodvials gained",
        "finalBlood": "Bloodvials at run end",
        "snacksConsumed": "Snacks consumed",
        "shopRefreshedTimes": "Shop rerolls",
    },
}
STATUS_NAMES = {
    "d_DDrone": "D-Drone", "d_SDrone": "S-Drone", "d_HDrone": "H-Drone",
    "d_RDrone": "R-Drone", "SpiritWolverine": "Wolverine Spirit",
    "SpiritBeetle": "Beetle Spirit", "SpiritViper": "Viper Spirit",
    "SpiritJaybird": "Jaybird Spirit",
}


def clean_text(value, fallback=""):
    if not isinstance(value, str):
        return fallback
    return " ".join(value.split())[:160] or fallback


@dataclass(frozen=True)
class Record:
    group: str
    metric: str
    label: str
    value: int
    run: str
    completed: str


@dataclass(frozen=True)
class PersonalRecords:
    profile: str
    version: str
    history_count: int
    includes_current: bool
    records: tuple[Record, ...]

    @property
    def coverage(self):
        text = f"Best values from {self.history_count} completed runs retained in this save"
        if self.includes_current:
            text += " and the current run"
        return text + ". Older runs are not retained, so these may not be lifetime bests."


def personal_records(data, refs=None, names=None):
    reader, root = read_save(data)
    meta = reader.resolve(root.get("metaProgressionData"))
    if not isinstance(meta, dict):
        raise ValueError("This save has no profile or run history.")
    history = [reader.resolve(item) for item in reader.sequence(meta.get("matchHistory"))]
    history = [item for item in history if isinstance(item, dict)]
    best = {}

    def add(group, metric, label, value, run, completed):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return
        previous = best.get(metric)
        if previous is None or value > previous.value:
            best[metric] = Record(group, metric, label, value, run, completed)

    def consume(entry, run, completed, current=False):
        stats = reader.resolve(entry.get("runStats")) or {}
        for group, metrics in METRICS.items():
            for metric, label in metrics.items():
                if current and metric == "finalBlood":
                    continue
                value = stats.get(metric) if metric in ("damageNegated", "flasksExhausted") else entry.get(metric)
                add(group, metric, label, value, run, completed)
        for field, group in (("buffsGiven", "Buffs gained · run totals"), ("debuffsGiven", "Debuffs applied · run totals")):
            for pair in reader.sequence(stats.get(field)):
                pair = reader.resolve(pair)
                reference = reader.resolve(pair.get("$k"))
                if not isinstance(reference, dict):
                    continue
                definition = (refs or {}).get(reference.get("$external"), {})
                name = (names or {}).get(str(definition.get("id")), {}).get("name") or definition.get("asset")
                if not name or name == "not_in_database":
                    continue
                label = STATUS_NAMES.get(name, clean_text(name))
                add(group, field + ":" + name, label, pair.get("$v"), run, completed)

    for index, entry in enumerate(history, 1):
        number = entry.get("runNumber")
        run = f"Run #{number}" if isinstance(number, int) else f"Saved run {index}"
        consume(entry, run, clean_text(entry.get("completedAt"), "Date unavailable"))
    player = reader.resolve(root.get("playerData"))
    includes_current = bool(meta.get("inRun")) and isinstance(player, dict)
    if includes_current:
        consume(player, "Current run", "In progress", current=True)
    add("Saved peak", "peakLadderStars", "Peak ladder stars", meta.get("peakLadderStars"), "Profile", "Lifetime saved peak")
    order = [*METRICS, "Buffs gained · run totals", "Debuffs applied · run totals", "Saved peak"]
    metric_order = {key: index for index, key in enumerate(key for group in METRICS.values() for key in group)}
    rows = sorted(best.values(), key=lambda row: (order.index(row.group), metric_order.get(row.metric, 100), row.label.casefold()))
    return PersonalRecords(clean_text(meta.get("companyName"), "Unnamed profile"), clean_text(root.get("gameVersion"), "Unknown"), len(history), includes_current, tuple(rows))


def records_text(report):
    lines = [f"FLASK PERSONAL RECORDS · {report.profile}", report.coverage,
             "Status amounts are totals across one run, not peak simultaneous stacks."]
    group = None
    for row in report.records:
        if row.group != group:
            lines.extend(["", row.group.upper()])
            group = row.group
        lines.append(f"• {row.label}: {row.value:,} — {row.run}")
    return "\n".join(lines)


def records_html(report):
    sections = []
    for group in dict.fromkeys(row.group for row in report.records):
        rows = "".join(f"<tr><td>{escape(row.label)}</td><td class='value'>{row.value:,}</td><td>{escape(row.run)}<small>{escape(row.completed)}</small></td></tr>" for row in report.records if row.group == group)
        sections.append(f"<section><h2>{escape(group)}</h2><table><thead><tr><th>Record</th><th>Best</th><th>Source</th></tr></thead><tbody>{rows}</tbody></table></section>")
    highlights = []
    for metric, label in (("highestDamage", "Largest hit"), ("highestShield", "Shield gain"), ("highestHeal", "Largest heal")):
        row = next((row for row in report.records if row.metric == metric), None)
        highlights.append(f"<div class='card'><span>{label}</span><strong>{f'{row.value:,}' if row else '—'}</strong></div>")
    return """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FLASK Personal Records</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#191622;color:#eee8df;font:16px 'Segoe UI',sans-serif;line-height:1.5}main{max-width:960px;margin:48px auto;padding:0 24px}header{border-top:3px solid #ebc890;padding-top:24px}.eyebrow{color:#ebc890;letter-spacing:.15em;font-size:12px}h1{font-size:38px;margin:8px 0}p{color:#bdb5cb;max-width:760px}.highlights{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:28px 0}.card{background:#252031;border:1px solid #3c334c;border-radius:12px;padding:20px}.card span{display:block;color:#bdb5cb}.card strong{display:block;font-size:32px;color:#ebc890;font-variant-numeric:tabular-nums}section{margin:30px 0}h2{font-size:20px}table{width:100%;border-collapse:collapse;background:#211c2c;border:1px solid #3c334c;border-radius:12px}th{text-align:left;color:#bdb5cb;font-size:12px;text-transform:uppercase;letter-spacing:.07em}th,td{padding:12px 16px;border-bottom:1px solid #3c334c}td.value{color:#ebc890;font-weight:700;font-variant-numeric:tabular-nums}small{display:block;color:#aaa1b8;font-size:12px}footer{padding:20px 0 40px;color:#aaa1b8;font-size:13px}@media(max-width:600px){main{padding:0 14px}.highlights{gap:6px}.card{padding:12px}.card strong{font-size:24px}th,td{padding:9px 8px}h1{font-size:30px}}@media print{:root{color-scheme:light}body{background:white;color:#222}p,small,footer,th{color:#555}.card,table{background:white}.card strong,td.value{color:#5d4521}main{margin:0}tr{break-inside:avoid}}
</style><main><header><div class="eyebrow">FLASK · PERSONAL RECORDS</div><h1>""" + escape(report.profile) + "</h1><p>" + escape(report.coverage) + "</p></header><div class='highlights'>" + "".join(highlights) + "</div>" + "".join(sections) + "<footer>Status amounts are cumulative run totals, not peak stacks held at once. Unidentified status assets are omitted.<br>Game " + escape(report.version) + " · Read from your local save. No save data was changed or uploaded.</footer></main></html>"
