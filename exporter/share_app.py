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
from tkinter import filedialog, messagebox, ttk

from build_protocol import decode_code, encode_code, validate_build
from export_build import SavedRun, export_bytes, export_saved_runs
from library_client import LibraryClient
from personal_records import personal_records, records_html, records_text

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
        root.geometry("900x720")
        root.minsize(780, 640)
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
        style.configure("TButton", font=("Segoe UI", 12), padding=9, background="#30283e", foreground="#eee8df")
        style.map("TButton", background=[("active", "#493c5d")], foreground=[("disabled", "#8b8299")])
        style.configure("Copy.TButton", font=("Segoe UI", 15, "bold"), padding=13)
        style.configure("TNotebook", background="#191622", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(22, 12), font=("Segoe UI", 11, "bold"), background="#211c2c", foreground="#bdb5cb")
        style.map("TNotebook.Tab", background=[("selected", "#30283e")], foreground=[("selected", "#ebc890")])
        style.configure("Record.Treeview", background="#211c2c", fieldbackground="#211c2c", foreground="#eee8df", font=("Segoe UI", 10), rowheight=32, borderwidth=0)
        style.configure("Record.Treeview.Heading", font=("Segoe UI", 10, "bold"), background="#30283e", foreground="#ebc890")
        style.map("Record.Treeview", background=[("selected", "#493c5d")], foreground=[("selected", "#ffffff")])
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=12)
        frame = ttk.Frame(self.notebook, padding=24)
        self.notebook.add(frame, text="Share Build")
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
        self.create_records_tab()
        self.refresh_record_saves()
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
        self.refresh_record_saves()

    def create_records_tab(self):
        frame = ttk.Frame(self.notebook, padding=22)
        self.notebook.add(frame, text="Personal Records")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(5, weight=1)
        ttk.Label(frame, text="Your personal records", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text="Choose a save to see its best recorded moments.").grid(row=1, column=0, sticky="w", pady=(5, 14))
        picker = ttk.Frame(frame)
        picker.grid(row=2, column=0, sticky="ew")
        self.record_paths = []
        self.extra_record_paths = []
        self.record_selection = ttk.Combobox(picker, state="readonly", font=("Segoe UI", 10))
        self.record_selection.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.record_selection.bind("<<ComboboxSelected>>", self.show_records)
        ttk.Button(picker, text="Choose file…", command=self.choose_record_file).pack(side="right")
        self.record_coverage = tk.StringVar(value="Choose a FLASK save file.")
        ttk.Label(frame, textvariable=self.record_coverage, wraplength=700, font=("Segoe UI", 9)).grid(row=3, column=0, sticky="w", pady=(10, 12))
        highlights = ttk.Frame(frame)
        highlights.grid(row=4, column=0, sticky="ew", pady=(0, 14))
        self.record_highlights = {}
        for column, (metric, label) in enumerate((("highestDamage", "LARGEST HIT"), ("highestShield", "SHIELD GAIN"), ("highestHeal", "LARGEST HEAL"))):
            highlights.columnconfigure(column, weight=1)
            card = tk.Frame(highlights, bg="#30283e", padx=18, pady=12)
            card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0))
            tk.Label(card, text=label, bg="#30283e", fg="#bdb5cb", font=("Segoe UI", 9)).pack(anchor="w")
            value = tk.StringVar(value="—")
            tk.Label(card, textvariable=value, bg="#30283e", fg="#ebc890", font=("Segoe UI", 23, "bold")).pack(anchor="w")
            self.record_highlights[metric] = value
        table_frame = ttk.Frame(frame)
        table_frame.grid(row=5, column=0, sticky="nsew")
        self.records_table = ttk.Treeview(table_frame, columns=("value", "run"), show="tree headings", style="Record.Treeview", selectmode="browse")
        self.records_table.heading("#0", text="RECORD", anchor="w")
        self.records_table.heading("value", text="BEST", anchor="e")
        self.records_table.heading("run", text="SOURCE", anchor="w")
        self.records_table.column("#0", width=370, minwidth=260)
        self.records_table.column("value", width=110, minwidth=80, anchor="e", stretch=False)
        self.records_table.column("run", width=150, minwidth=110, stretch=False)
        self.records_table.tag_configure("section", foreground="#ebc890", background="#30283e", font=("Segoe UI", 10, "bold"))
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.records_table.yview)
        self.records_table.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.records_table.pack(side="left", fill="both", expand=True)
        self.records_table.bind("<<TreeviewSelect>>", self.record_selected)
        self.record_status = tk.StringVar(value="Status amounts are run totals, not peak stacks.")
        ttk.Label(frame, textvariable=self.record_status, wraplength=700, font=("Segoe UI", 9)).grid(row=6, column=0, sticky="w", pady=8)
        actions = ttk.Frame(frame)
        actions.grid(row=7, column=0, sticky="ew")
        self.copy_records_button = ttk.Button(actions, text="Copy Records", command=self.copy_records)
        self.copy_records_button.pack(side="left")
        self.save_records_button = ttk.Button(actions, text="Save Report…", command=self.save_records_report)
        self.save_records_button.pack(side="left", padx=8)
        ttk.Button(actions, text="Refresh saves", command=self.refresh_record_saves).pack(side="right")
        self.record_report = None
        self.record_rows = {}
        self.set_record_actions(False)

    def set_record_actions(self, enabled):
        for button in (self.copy_records_button, self.save_records_button):
            button.state(["!disabled" if enabled else "disabled"])

    def refresh_record_saves(self):
        index = self.record_selection.current()
        previous = self.record_paths[index] if 0 <= index < len(self.record_paths) else None
        paths = sorted(set(save_folder().rglob("SavedGame.rbs")) | set(self.extra_record_paths), key=lambda path: str(path))
        self.record_paths = paths
        labels = []
        for path in paths:
            try:
                report = personal_records(read_save_bytes(path))
                labels.append(f"{report.profile} · {report.history_count} saved runs · {path.parent.name}")
            except (ValueError, KeyError, TypeError, OSError):
                labels.append(f"Unreadable save · {path.parent.name}/{path.name}")
        self.record_selection["values"] = labels
        if paths:
            selected = previous if previous in paths else preferred_save(paths)
            self.record_selection.current(paths.index(selected))
            self.show_records()
        else:
            self.record_selection.set("No save found — use Choose file…")
            self.record_coverage.set("Choose a SavedGame.rbs file to view its records.")
            self.record_report = None
            self.set_record_actions(False)

    def choose_record_file(self):
        filename = filedialog.askopenfilename(parent=self.root, title="Choose a FLASK save", initialdir=str(save_folder()), filetypes=[("FLASK saves", "*.rbs *.bak"), ("All files", "*.*")])
        if filename:
            path = Path(filename)
            if path not in self.extra_record_paths:
                self.extra_record_paths.append(path)
            self.refresh_record_saves()
            self.record_selection.current(self.record_paths.index(path))
            self.show_records()

    def show_records(self, event=None):
        self.records_table.delete(*self.records_table.get_children())
        self.record_rows = {}
        self.record_report = None
        self.set_record_actions(False)
        for value in self.record_highlights.values():
            value.set("—")
        try:
            index = self.record_selection.current()
            if not 0 <= index < len(self.record_paths):
                raise ValueError("Choose a save file first.")
            report = personal_records(read_save_bytes(self.record_paths[index]), REFS, NAMES)
            self.record_report = report
            self.record_coverage.set(report.coverage)
            groups = {}
            for row in report.records:
                if row.group not in groups:
                    groups[row.group] = self.records_table.insert("", "end", text=row.group, open=True, tags=("section",))
                ident = self.records_table.insert(groups[row.group], "end", text=row.label, values=(f"{row.value:,}", row.run))
                self.record_rows[ident] = row
                if row.metric in self.record_highlights:
                    self.record_highlights[row.metric].set(f"{row.value:,}")
            self.record_status.set("Status amounts are run totals, not peak stacks. Select a record for its date.")
            self.set_record_actions(True)
            return report
        except (ValueError, KeyError, TypeError, OSError) as exc:
            self.record_coverage.set("Could not read records from this save.")
            self.record_status.set(str(exc))
            return None

    def record_selected(self, event=None):
        selected = self.records_table.selection()
        row = self.record_rows.get(selected[0]) if selected else None
        if row:
            self.record_status.set(f"{row.label}: {row.value:,} · {row.run} · {row.completed}")

    def copy_records(self):
        report = self.show_records()
        if report:
            self.root.clipboard_clear()
            self.root.clipboard_append(records_text(report))
            self.root.update()
            self.record_status.set("Records copied. Paste them into a message or document.")

    def save_records_report(self):
        report = self.show_records()
        if not report:
            return
        filename = filedialog.asksaveasfilename(parent=self.root, title="Save personal records report", initialfile="FLASK Personal Records.html", defaultextension=".html", filetypes=[("HTML report", "*.html")])
        if filename:
            try:
                Path(filename).write_text(records_html(report), encoding="utf8")
                self.record_status.set("Report saved. Open it in your browser to view or print it.")
            except OSError as exc:
                messagebox.showerror("Could not save report", str(exc), parent=self.root)

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
            command = "!flask party " + encode_code(build)
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
            command_length=len("!flask party " + code),
            save_unchanged=True,
        )
        copied = []
        window.clipboard_clear = lambda: None
        window.clipboard_append = lambda text: copied.append(text)
        app.copy_build()
        assert copied and copied[0].startswith("!flask party FB1.")
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
    assert len(app.notebook.tabs()) == 2
    result["tabs"] = 2
    if app.record_paths:
        app.notebook.select(1)
        selected_path = app.record_paths[app.record_selection.current()]
        before = hashlib.sha256(selected_path.read_bytes()).digest()
        report = app.show_records()
        assert report is not None and app.records_table.get_children()
        copied_records = []
        window.clipboard_append = lambda text: copied_records.append(text)
        app.copy_records()
        assert copied_records == [records_text(report)]
        assert hashlib.sha256(selected_path.read_bytes()).digest() == before
        preview = Path(output).with_suffix(".html")
        preview.write_text(records_html(report), encoding="utf8")
        result.update(records_tab_verified=True, records_copy_verified=True,
                      record_count=len(report.records), records_save_unchanged=True)
    window.destroy()
    Path(output).write_text(json.dumps(result, indent=2), encoding="utf8")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        self_test(sys.argv[2])
    else:
        root = tk.Tk()
        app = ShareApp(root)
        root.mainloop()
