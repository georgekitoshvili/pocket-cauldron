"""Portable Windows build sharing with a shared reference library. No Discord token or bot files needed."""

import hashlib
import json
import os
import queue
import re
import sys
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, ttk

from build_protocol import decode_code, encode_code, validate_build
from export_build import SavedRun, export_bytes, export_saved_runs
from library_client import LibraryClient

ROOT = Path(__file__).resolve().parent
REFS = {}
NAMES = {}


def use_snapshot(snapshot):
    global REFS, NAMES
    refs = json.loads((snapshot.root / "data/build-refs.json").read_text("utf8"))
    names = json.loads((snapshot.root / "data/build-catalog.json").read_text("utf8"))
    REFS, NAMES = refs, names


def save_folder():
    return (
        Path(os.getenv("USERPROFILE", str(Path.home())))
        / "AppData/LocalLow/Chop Chop Games/Flask/Saves"
    )


@dataclass(frozen=True)
class SavedTeam:
    path: Path
    run: SavedRun


def read_save_bytes(path):
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("FLASK was saving. Wait a moment and try again.")
    return raw


def read_build(path):
    return validate_build(export_bytes(read_save_bytes(path), REFS))


def read_saved_runs(path):
    return export_saved_runs(read_save_bytes(path), REFS)


def team_name(build):
    return " / ".join(
        NAMES.get(str(c["id"]), {}).get("name", f"Character #{c['id']}")
        for c in build["build"]["characters"]
    )


def preferred_save(saves):
    if not saves:
        return None
    roots = [Path(r"C:\Program Files (x86)\Steam")]
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            roots.insert(0, Path(winreg.QueryValueEx(key, "SteamPath")[0]))
    except (OSError, ImportError):
        pass
    for root in roots:
        manifest = root / "steamapps/appmanifest_4891490.acf"
        if not manifest.exists():
            continue
        match = re.search(r'"LastOwner"\s+"(\d+)"', manifest.read_text("utf8"))
        if match:
            candidate = save_folder() / match[1] / "SavedGame.rbs"
            if candidate in saves:
                return candidate
    return max(saves, key=lambda p: p.stat().st_mtime_ns)


class ShareApp:
    def __init__(self, root, snapshot=None):
        self.root = root
        root.title("FLASK - Share Build")
        root.geometry("680x520")
        root.minsize(680, 520)
        root.configure(bg="#191622")
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#191622")
        style.configure(
            "TLabel", background="#191622", foreground="#eee8df", font=("Segoe UI", 11)
        )
        style.configure(
            "Title.TLabel", font=("Segoe UI", 22, "bold"), foreground="#ebc890"
        )
        style.configure("TButton", font=("Segoe UI", 12), padding=9)
        style.configure("Copy.TButton", font=("Segoe UI", 15, "bold"), padding=13)
        frame = ttk.Frame(root, padding=24)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Share your FLASK build", style="Title.TLabel").pack(
            anchor="w"
        )
        ttk.Label(
            frame,
            text="Choose your current team or a completed run, then copy into Discord.",
        ).pack(anchor="w", pady=(8, 18))
        self.selection = tk.StringVar()
        self.saves = []
        self.combo = ttk.Combobox(
            frame, textvariable=self.selection, state="readonly", font=("Segoe UI", 10)
        )
        self.combo.pack(fill="x")
        self.combo.bind("<<ComboboxSelected>>", self.selected)
        self.details = tk.StringVar(value="Looking for saved runs…")
        ttk.Label(frame, textvariable=self.details, wraplength=610).pack(
            anchor="w", pady=12
        )
        self.copy = ttk.Button(
            frame, text="Copy Build", style="Copy.TButton", command=self.copy_build
        )
        self.copy.pack(fill="x", pady=(0, 10))
        self.status = tk.StringVar(value="")
        ttk.Label(frame, textvariable=self.status, wraplength=610).pack(anchor="w")
        self.update_button = ttk.Button(
            frame, text="Refresh library & run history", command=self.update_library
        )
        self.update_button.pack(anchor="w", pady=(12, 0))
        ttk.Label(
            frame,
            text="Reads saves only. Includes up to 10 completed runs kept by FLASK. Nothing is uploaded.",
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(12, 0))
        self.loading = False
        self.results = queue.Queue()
        if snapshot:
            use_snapshot(snapshot)
            self.refresh()
        else:
            self.update_library()
        self.root.after(900000, self.periodic_update)

    def update_library(self):
        if self.loading:
            return
        self.loading = True
        self.copy.state(["disabled"])
        self.update_button.state(["disabled"])
        self.status.set("Checking the shared library for updates…")

        def download():
            try:
                self.results.put((LibraryClient("exporter").refresh(), None))
            except Exception as exc:
                self.results.put((None, str(exc)))

        threading.Thread(target=download, daemon=True).start()
        self.root.after(100, self.poll_update)

    def poll_update(self):
        try:
            snapshot, error = self.results.get_nowait()
        except queue.Empty:
            self.root.after(100, self.poll_update)
            return
        self.loading = False
        self.update_button.state(["!disabled"])
        if error:
            self.status.set(error)
            if REFS:
                self.refresh()
        else:
            use_snapshot(snapshot)
            self.refresh()

    def periodic_update(self):
        self.update_library()
        self.root.after(900000, self.periodic_update)

    def refresh(self):
        self.copy.state(["disabled"])
        self.saves = []
        labels = []
        paths = sorted(
            save_folder().rglob("SavedGame.rbs"),
            key=lambda p: p.stat().st_mtime_ns,
            reverse=True,
        )
        preferred = preferred_save(paths)
        preferred_index = None
        for path in paths:
            try:
                runs = read_saved_runs(path)
            except (ValueError, KeyError, TypeError, OSError):
                continue
            for run in runs:
                if path == preferred and preferred_index is None:
                    preferred_index = len(self.saves)
                self.saves.append(SavedTeam(path, run))
                name = (
                    team_name(run.build)
                    if run.build is not None
                    else "Unable to export"
                )
                labels.append(run.label + " — " + name)
        self.combo["values"] = labels
        if self.saves:
            self.combo.current(min(preferred_index or 0, len(self.saves) - 1))
            self.selected()
        else:
            self.selection.set("No saved team found")
            self.details.set(
                "Save a run in FLASK, then click Refresh library & run history."
            )
            self.status.set("")

    def selected_build(self, reread=False):
        index = self.combo.current()
        if not 0 <= index < len(self.saves):
            raise ValueError("Choose a saved team first.")
        selection = self.saves[index]
        run = selection.run
        if reread:
            run = next(
                (
                    item
                    for item in read_saved_runs(selection.path)
                    if item.key == run.key
                ),
                None,
            )
            if run is None:
                raise ValueError(
                    "This run is no longer in the game's saved history. Refresh the list and choose another run."
                )
        if run.error or run.build is None:
            raise ValueError(run.error or "This run has no exportable team.")
        return run.build

    def selected(self, event=None):
        try:
            build = self.selected_build()
            self.details.set(
                team_name(build)
                + "\n"
                + str(
                    sum(
                        f is not None
                        for c in build["build"]["characters"]
                        for f in c["flasks"]
                    )
                )
                + " equipped flasks | Game "
                + build["gameVersion"]
            )
            self.copy.state(["!disabled"])
            self.status.set(
                "Ready to copy. Choose your current team or a completed run above."
            )
        except (ValueError, KeyError, TypeError, OSError, IndexError) as exc:
            self.copy.state(["disabled"])
            self.status.set(str(exc))

    def copy_build(self):
        try:
            # Re-read on each click so an open helper does not keep sharing stale data.
            build = self.selected_build(reread=True)
            command = "flask party " + encode_code(build)
            self.root.clipboard_clear()
            self.root.clipboard_append(command)
            self.root.update()
            self.status.set("Copied! In your Discord channel press Ctrl+V, then Enter.")
            self.details.set(
                team_name(build)
                + "\n"
                + str(
                    sum(
                        f is not None
                        for c in build["build"]["characters"]
                        for f in c["flasks"]
                    )
                )
                + " equipped flasks | Game "
                + build["gameVersion"]
            )
        except (ValueError, KeyError, TypeError, OSError, IndexError) as exc:
            messagebox.showerror("Could not copy build", str(exc), parent=self.root)


def self_test(output):
    """Verify the packaged GUI and export path without displaying a window."""
    snapshot = LibraryClient("exporter").ensure()
    window = tk.Tk()
    window.withdraw()
    app = ShareApp(window, snapshot=snapshot)
    window.update_idletasks()
    patch = window.tk.call("info", "patchlevel")
    paths = list(save_folder().rglob("SavedGame.rbs"))
    path = preferred_save(paths)
    result = dict(
        gui_runtime=str(patch),
        reference_count=len(REFS),
        catalog_count=len(NAMES),
        available_saved_teams=len(app.saves),
    )
    if path and app.saves:
        before = hashlib.sha256(path.read_bytes()).digest()
        b = app.selected_build(reread=True)
        code = encode_code(b)
        assert decode_code(code) == b
        assert hashlib.sha256(path.read_bytes()).digest() == before
        result.update(
            characters=len(b["build"]["characters"]),
            equipped_flasks=sum(
                f is not None for c in b["build"]["characters"] for f in c["flasks"]
            ),
            command_length=len("flask party " + code),
            save_unchanged=True,
        )
        copied = []
        window.clipboard_clear = lambda: None
        window.clipboard_append = lambda text: copied.append(text)
        app.copy_build()
        assert copied and copied[0].startswith("flask party FB1.")
        assert decode_code(copied[0].split(" ", 2)[2]) == b
        assert app.status.get().startswith("Copied!")
        result["copy_button_verified"] = True
    historical = next(
        (
            index
            for index, team in enumerate(app.saves)
            if team.run.key[0] == "history" and team.run.build is not None
        ),
        None,
    )
    if historical is not None:
        app.combo.current(historical)
        app.selected()
        expected = app.selected_build(reread=True)
        copied_history = []
        window.clipboard_clear = lambda: None
        window.clipboard_append = lambda text: copied_history.append(text)
        before = hashlib.sha256(app.saves[historical].path.read_bytes()).digest()
        app.copy_build()
        assert decode_code(copied_history[0].split(" ", 2)[2]) == expected
        assert (
            hashlib.sha256(app.saves[historical].path.read_bytes()).digest() == before
        )
        result["history_copy_verified"] = True
        result["historical_teams"] = sum(
            team.run.key[0] == "history" for team in app.saves
        )
    window.destroy()
    Path(output).write_text(json.dumps(result, indent=2), encoding="utf8")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        self_test(sys.argv[2])
    else:
        root = tk.Tk()
        app = ShareApp(root)
        root.mainloop()
