"""Validated portable FLASK party files and compact sharing codes."""

import base64
import json
import re
import zlib

MAX_BUILD_BYTES = 128 * 1024


def integer(value, label, lo=0, hi=10000000):
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError(f"Invalid {label}.")
    return value


def array(value, label, limit):
    if not isinstance(value, list) or len(value) > limit:
        raise ValueError(f"Invalid {label} (maximum {limit}).")
    return value


def validate_build(raw):
    if (
        not isinstance(raw, dict)
        or raw.get("format") != "flask-build"
        or raw.get("schema") != 1
    ):
        raise ValueError(
            "Use a .flaskbuild.json file made by FLASK Build Exporter. Full game saves are not accepted."
        )
    version = raw.get("gameVersion", "unknown")
    if not isinstance(version, str) or not re.fullmatch(
        r"[A-Za-z0-9. _-]{1,40}", version
    ):
        raise ValueError("Invalid game version.")
    source = raw.get("build")
    if not isinstance(source, dict):
        raise ValueError("Missing build.")
    characters = []
    for character in array(source.get("characters"), "characters", 6):
        if not isinstance(character, dict):
            raise ValueError("Invalid character.")
        flasks = []
        for flask in array(character.get("flasks"), "flask slots", 12):
            if flask is None:
                flasks.append(None)
                continue
            if not isinstance(flask, dict):
                raise ValueError("Invalid flask.")
            flasks.append(
                dict(
                    id=integer(flask.get("id"), "flask ID"),
                    level=integer(flask.get("level"), "flask level", 1, 4),
                    infusers=[
                        integer(n, "infuser ID")
                        for n in array(flask.get("infusers", []), "infusers", 12)
                    ],
                )
            )
        characters.append(
            dict(
                id=integer(character.get("id"), "character ID"),
                hp=integer(character.get("hp"), "health", 1),
                mutation=integer(character.get("mutation", -1), "mutation", -1),
                snacks=[
                    integer(n, "snack ID")
                    for n in array(character.get("snacks", []), "snacks", 40)
                ],
                flasks=flasks,
            )
        )
    if not characters:
        raise ValueError("The build contains no characters.")
    tokens = []
    for t in array(source.get("elementTokens", []), "element tokens", 32):
        if not isinstance(t, dict):
            raise ValueError("Invalid element token.")
        tokens.append(
            dict(
                elementId=integer(t.get("elementId"), "element ID"),
                amount=integer(t.get("amount"), "element amount"),
            )
        )
    # Export only build fields; never propagate save metadata.
    return dict(
        format="flask-build",
        schema=1,
        gameVersion=version,
        build=dict(characters=characters, elementTokens=tokens),
    )


def decode_build(data):
    if len(data) > MAX_BUILD_BYTES:
        raise ValueError("Build files must be smaller than 128 KB.")
    try:
        return validate_build(json.loads(data.decode("utf-8-sig")))
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise ValueError("This is not a readable build JSON file.") from None


def encode_code(build):
    raw = json.dumps(validate_build(build), separators=(",", ":")).encode("utf8")
    code = "FB1." + base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode(
        "ascii"
    ).rstrip("=")
    if len("flask build " + code) > 2000:
        raise ValueError(
            "This build is too large for a pasted command. Use the exported JSON attachment instead."
        )
    return code


def decode_code(code):
    if not isinstance(code, str) or not re.fullmatch(
        r"FB1\.[A-Za-z0-9_-]{1,1985}", code
    ):
        raise ValueError("Invalid build code. Copy it again using FLASK Share Build.")
    try:
        encoded = code[4:]
        compressed = base64.b64decode(
            encoded + "=" * ((-len(encoded)) % 4), altchars=b"-_", validate=True
        )
        decoder = zlib.decompressobj()
        raw = decoder.decompress(compressed, MAX_BUILD_BYTES + 1)
        if (
            len(raw) > MAX_BUILD_BYTES
            or decoder.unconsumed_tail
            or not decoder.eof
            or decoder.unused_data
        ):
            raise ValueError("Invalid or oversized compressed build.")
        return decode_build(raw)
    except (zlib.error, ValueError) as exc:
        raise ValueError(
            "Invalid build code. Copy it again using FLASK Share Build."
        ) from exc
