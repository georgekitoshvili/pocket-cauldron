"""Read FLASK party data from local saves without modifying them."""

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from odin_reader import OdinReader, SaveError

ROOT = Path(__file__).resolve().parent


def export_bytes(data, refs):
    reader = OdinReader(data)
    root = reader.read()
    if not (root.get("$type") or "").startswith("SaveData,"):
        raise SaveError("Not a FLASK save.")
    player = reader.resolve(root.get("playerData"))
    if not isinstance(player, dict):
        raise SaveError("No saved player team.")

    def ident(value):
        value = reader.resolve(value)
        if value is None:
            return -1
        guid = value.get("$external") if isinstance(value, dict) else None
        if guid not in refs:
            raise SaveError(
                "An asset is missing from the build reference catalog. Update the catalog for this game version."
            )
        return refs[guid]["id"]

    characters = []
    # The game's PlayerBuildToJson also reverses characterList for team order.
    for value in reversed(reader.sequence(player.get("characterList"))):
        character = reader.resolve(value)
        flasks = []
        for value in reader.sequence(character.get("timeslotList")):
            flask = reader.resolve(value)
            if not flask or flask.get("flask_SA") is None:
                flasks.append(None)
                continue
            flasks.append(
                dict(
                    id=ident(flask["flask_SA"]),
                    level=flask["level"],
                    infusers=[
                        ident(v)
                        for v in reader.sequence(flask.get("infusers"))
                        if v is not None
                    ],
                )
            )
        characters.append(
            dict(
                id=ident(character.get("charSARef")),
                hp=character["maxHP"],
                mutation=ident(character.get("charMutation")),
                snacks=[
                    ident(v)
                    for v in reader.sequence(character.get("snackEffects"))
                    if v is not None
                ],
                flasks=flasks,
            )
        )
    if not characters:
        raise SaveError("This save has no team. Start a run and save it first.")
    tokens = []
    for value in reader.sequence(player.get("elementTokens")):
        entry = reader.resolve(value)
        tokens.append(dict(elementId=ident(entry["$k"]), amount=entry["$v"]))
    return dict(
        format="flask-build",
        schema=1,
        gameVersion=root.get("gameVersion", "unknown"),
        exportedAt=datetime.now(timezone.utc).isoformat(),
        build=dict(characters=characters, elementTokens=tokens),
    )


def save_export(source, output, refs):
    source = Path(source).resolve()
    output = Path(output).resolve()
    if source == output or output.suffix.lower() != ".json":
        raise SaveError("Export to a separate .json file, never the game save.")
    before = source.stat()
    raw = source.read_bytes()
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise SaveError("The game was saving. Wait a moment and try again.")
    result = export_bytes(raw, refs)
    from build_protocol import validate_build

    result = validate_build(result)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(".json.tmp")
    temp.write_text(json.dumps(result, indent=2), encoding="utf8")
    os.replace(temp, output)
    return result


def main():
    p = argparse.ArgumentParser(
        description="Export the team in a FLASK save for Discord."
    )
    p.add_argument(
        "--save",
        type=Path,
        help="Specific SavedGame.rbs; otherwise choose interactively.",
    )
    p.add_argument("--output", type=Path)
    p.add_argument(
        "--choose",
        action="store_true",
        help="Choose a different saved run; default uses the installed game account or newest save.",
    )
    p.add_argument(
        "--command-file",
        type=Path,
        help="Write the pasteable Discord command for the launcher.",
    )
    args = p.parse_args()
    from library_client import LibraryClient

    library_root = LibraryClient("exporter").ensure().root
    source = args.save
    if source is None:
        folder = (
            Path(os.getenv("USERPROFILE", str(Path.home())))
            / "AppData/LocalLow/Chop Chop Games/Flask/Saves"
        )
        saves = sorted(
            folder.rglob("SavedGame.rbs"),
            key=lambda f: f.stat().st_mtime_ns,
            reverse=True,
        )
        if not saves:
            raise SaveError(
                "No FLASK save found. Start a run and save/return to the tower first."
            )
        refs = json.loads((library_root / "data/build-refs.json").read_text("utf8"))
        if not args.choose:
            manifest = Path(
                r"C:\Program Files (x86)\Steam\steamapps\appmanifest_4891490.acf"
            )
            owner = (
                re.search(r'"LastOwner"\s+"(\d+)"', manifest.read_text("utf8"))
                if manifest.exists()
                else None
            )
            account_save = folder / owner[1] / "SavedGame.rbs" if owner else None
            source = (
                account_save if account_save and account_save.is_file() else saves[0]
            )
            print(
                "Using the installed game account save."
                if source == account_save
                else "Using the newest saved run."
            )
        else:
            print(
                "Choose the saved run to export (newest first). Your save is only read.\n"
            )
        for i, s in enumerate(saves if args.choose else [], 1):
            try:
                b = export_bytes(s.read_bytes(), refs)
                catalog = json.loads(
                    (library_root / "data/build-catalog.json").read_text("utf8")
                )
                names = [
                    catalog.get(str(c["id"]), {}).get("name", f"Character #{c['id']}")
                    for c in b["build"]["characters"]
                ]
                summary = " / ".join(names)
            except (ValueError, KeyError, TypeError):
                summary = "Unreadable or no team"
            stamp = datetime.fromtimestamp(s.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            print(f"{i}. {stamp} - {summary}")
        if args.choose:
            answer = input("\nSave number [1 = newest]: ").strip() or "1"
            if not answer.isdecimal() or not 1 <= int(answer) <= len(saves):
                raise SaveError("Invalid save number.")
            source = saves[int(answer) - 1]
    output = args.output or ROOT / "exports" / (
        "Build-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".flaskbuild.json"
    )
    refs = json.loads((library_root / "data/build-refs.json").read_text("utf8"))
    result = save_export(source, output, refs)
    print(
        f'\nExported {len(result["build"]["characters"])} characters to:\n{output.resolve()}'
    )
    catalog = json.loads((library_root / "data/build-catalog.json").read_text("utf8"))
    print(
        "Team: "
        + " / ".join(
            catalog.get(str(c["id"]), {}).get("name", f"Character #{c['id']}")
            for c in result["build"]["characters"]
        )
    )
    if args.command_file:
        from build_protocol import encode_code

        command = "flask party " + encode_code(result)
        args.command_file.parent.mkdir(parents=True, exist_ok=True)
        args.command_file.write_text(command, encoding="utf8")
    else:
        print(
            "\nAttach the exported JSON with flask build, or use Share Build.cmd to copy a pasteable command."
        )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, TypeError) as exc:
        raise SystemExit("EXPORT FAILED: " + str(exc))
