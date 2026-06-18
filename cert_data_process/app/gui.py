"""Tkinter GUI for the Lib-Char-Certi console.

Single process: draws the window AND runs the pipeline (via the UI-agnostic
JobManager). No HTTP/port/localhost/host-matching — displays over X11/Exceed like
a terminal. Pure helpers are module-level (display-free, testable); the Tk window
is created only when CertiApp() is instantiated.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from ..runtime import runs
from ..runtime import summary as _summary
from ..runtime.executor import JobManager
from ..analysis import consolidate as _consolidate
from ..analysis import outliers as _outliers
from ..analysis import perarc as _perarc
from ..analysis import voltage_margin as _vm

# consolidate_pr color band -> PR_BG/PR_FG key
_COLOR2CLS = {"green": "hi", "amber": "mid", "red": "lo", "none": "na"}

# Pass-rate cell colors (B): green >=95, amber 90-<95, red <90, neutral unknown.
PR_BG = {"hi": "#d8f5e0", "mid": "#fdebc8", "lo": "#fad4d4", "na": "#eef2f7"}
PR_FG = {"hi": "#15803d", "mid": "#b45309", "lo": "#b91c1c", "na": "#8a94a6"}

TYPES = ["delay", "slew", "hold", "mpw"]
STAGES = [
    ("fmc_combine_data", "FMC Combine"),
    ("lib_join_sigma", "Lib Join"),
    ("build_pr_table", "Sigma PR"),
    ("get_pr_moments", "Moments PR"),
    ("generate_pr_web_app", "Dashboard"),
]
HEALTH_BG = {"OK": "#e8f6ec", "LOW_COVERAGE": "#fdf2e0", "NO_DATA": "#fdecec", "UNKNOWN": "#eef2f7"}
STATE_FG = {
    "passed": "#15803d", "ok": "#15803d", "running": "#2563eb",
    "partial": "#b45309", "queued": "#8a94a6", "pending": "#aab2c0",
    "skipped": "#8a94a6", "failed": "#b91c1c",
}


# ---------------- pure helpers (no Tk; unit-testable) ----------------
def pr_class(v: Optional[float]) -> str:
    if v is None:
        return "na"
    return "hi" if v >= 95 else "mid" if v >= 90 else "lo"


def fmt_pr(v: Optional[float]) -> str:
    return "—" if v is None else f"{v:.1f}%"


def short_corner(c: str) -> str:
    return str(c).replace("ssgnp_", "").replace("ssgng_", "").replace("_m40c", "")


def _fmc_corner_matchers(corner: str) -> list:
    """Substrings to find a corner's FMC file: the full corner, then its voltage token
    (e.g. '0p475v') which is the most reliable cross-naming match."""
    import re
    out = [corner] if corner else []
    m = re.search(r"\d+p\d+v", corner or "")
    if m and m.group(0) not in out:
        out.append(m.group(0))
    return out


def _find_fmc_file(fdir, corner, row_type):
    """Find the FMC golden file for a corner under `fdir` (recursive, data files only).

    Tries, in order: voltage-token/full-corner match WITH the group (cons/delay) →
    same match WITHOUT the group → any data file containing the corner token. Returns
    the path string, or None when nothing matches (caller keeps showing the dir)."""
    d = Path(fdir)
    if not d.is_dir():
        return None
    group = "cons" if row_type in ("hold", "mpw") else "delay"
    files = [p for p in d.rglob("*")
             if p.is_file() and p.suffix.lower() in (".csv", ".rpt", ".txt")]
    matchers = _fmc_corner_matchers(corner)
    for require_group in (True, False):
        for mt in matchers:
            for p in files:
                if mt not in p.name:
                    continue
                if require_group and not (group in p.name.lower() or row_type in p.name.lower()):
                    continue
                return str(p)
    return None


def _fmc_deck_for_arc(path, cell, i1, i2):
    """Best-effort: read an FMC golden CSV and return the per-arc DECK/log path.

    Column-agnostic: the deck column is any header containing 'deck' or 'log'; the
    arc/cell is matched by the cell name appearing anywhere in the row (handles both
    SCLD 'Cell'/'point' and DFDS 'Cell_Name'/'Arc'). Among the cell's rows, prefer
    the one whose fields contain BOTH table indices (i1, i2). Returns the deck string
    or None. Streamed; pure (no Tk) so it is unit-tested."""
    import csv as _csv
    import re as _re
    p = Path(path)
    if not p.is_file():
        return None
    cell_l = str(cell).strip().lower()
    want_pt = {str(i1).strip(), str(i2).strip()} - {""}
    try:
        with p.open(newline="", encoding="utf-8", errors="replace") as fh:
            reader = _csv.reader(fh)
            header = next(reader, [])
            low = [str(h).strip().lower() for h in header]
            deck_i = next((i for i, h in enumerate(low) if "deck" in h or "log" in h), None)
            if deck_i is None or not cell_l:
                return None
            best = None
            for r in reader:
                if deck_i >= len(r):
                    continue
                rowtext = " ".join(r).lower()
                if cell_l not in rowtext:
                    continue
                deck = str(r[deck_i]).strip()
                if best is None:
                    best = deck
                if want_pt:
                    toks = {t for t in _re.split(r"[;,:/_ ]", rowtext) if t.strip()}
                    if want_pt <= toks:
                        return deck   # exact table-point match wins
            return best
    except (OSError, StopIteration):
        return None


def _scan_file_region(path, needle, whole_cell, max_lines=8000):
    """Stream a (possibly huge) file for `needle`; return (numbered_lines, first_line).

    whole_cell=True: from the first match, capture the ENTIRE brace-balanced block
    (e.g. a full `cell (...) { ... }`). whole_cell=False: collect ALL lines containing
    `needle` (e.g. every FMC arc row for a cell). Capped at max_lines; never loads the
    whole file. Pure (no Tk) so it is unit-tested directly."""
    window, ln = [], 0
    with Path(path).open(encoding="utf-8", errors="replace") as fh:
        if whole_cell:
            started, seen_open, depth = False, False, 0
            for i, line in enumerate(fh, 1):
                if not started:
                    if needle not in line:
                        continue
                    started, ln = True, i
                window.append(f"{i}: {line.rstrip()}")
                opens, closes = line.count("{"), line.count("}")
                if opens:
                    seen_open = True
                depth += opens - closes
                if (seen_open and depth <= 0) or len(window) >= max_lines:
                    break
        else:
            nlow = needle.lower()
            for i, line in enumerate(fh, 1):
                if nlow in line.lower():            # case-insensitive (DFDS vs SCLD casing)
                    if not window:
                        ln = i
                    window.append(f"{i}: {line.rstrip()}")
                    if len(window) >= max_lines:
                        break
    return window, ln


def _parse_abs_tol(text: str, corners: list) -> dict:
    """Parse the Setup abs_tol entry into {corner: ps}.

    - "19.5"                  -> that value for every current corner
    - "c1=19.5, c2=20"        -> per-corner
    - blank                   -> {} (waiver_2 off)
    Non-numeric / <=0 entries are dropped (config also re-validates).
    """
    s = (text or "").strip()
    if not s:
        return {}
    if "=" not in s:
        try:
            v = float(s)
        except ValueError:
            return {}
        return {c: v for c in corners} if v > 0 else {}
    out = {}
    for part in s.replace(";", ",").split(","):
        if "=" not in part:
            continue
        k, _, val = part.partition("=")
        k = k.strip()
        try:
            v = float(val.strip())
        except ValueError:
            continue
        if k and v > 0:
            out[k] = v
    return out


def corner_suggestions(index: list) -> list:
    seen: list = []
    for row in index or []:
        for c in row.get("corners", []) or []:
            if c not in seen:
                seen.append(c)
    return sorted(seen)


def coverage_text(row: dict) -> str:
    total, covered = row.get("total"), row.get("covered")
    if not total:  # None (unknown / old table) or 0
        return "—" if total is None else "0/0"
    return f"{covered}/{total} ({covered / total * 100:.0f}%)"


# ---------------- Tk app ----------------
class CertiApp:
    # Voltage Margin (Analysis) tab — hidden for v1 (design still in flux).
    SHOW_ANALYSIS = False

    def __init__(self, runs_root: Any = None, batch_concurrency: int = 2, liberate_budget: int = 4):
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.runs_root = runs.resolve_runs_root(runs_root)
        self.manager = JobManager(self.runs_root, batch_concurrency, liberate_budget)
        self.active_job: Optional[str] = None
        self.corners: list = []
        self.type_vars: dict = {}

        self.root = tk.Tk()
        self.root.title("Lib-Char-Certi Console")
        self.root.geometry("1080x720")
        self._style()
        self._build()
        self.refresh_history()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---- styling ----
    def _style(self):
        st = self.ttk.Style()
        try:
            st.theme_use("clam")
        except Exception:
            pass
        BG, CARD, HEAD = "#eef1f5", "#ffffff", "#1e293b"
        INK, MUTE, ACCENT = "#0f172a", "#64748b", "#2563eb"
        LINE, TABBG, SEL = "#d7dde5", "#dde3ea", "#dbeafe"
        self.palette = dict(BG=BG, CARD=CARD, HEAD=HEAD, INK=INK, MUTE=MUTE, ACCENT=ACCENT, LINE=LINE)
        FONT = ("DejaVu Sans", 10)
        self.root.configure(bg=BG)
        self.root.option_add("*Font", "{DejaVu Sans} 10")

        st.configure(".", background=BG, foreground=INK, font=FONT, focuscolor=BG)
        st.configure("TFrame", background=BG)
        st.configure("Card.TFrame", background=CARD)
        st.configure("TLabel", background=BG, foreground=INK)
        st.configure("Muted.TLabel", background=BG, foreground=MUTE)
        st.configure("H1.TLabel", background=HEAD, foreground="#ffffff", font=("DejaVu Sans", 15, "bold"))
        st.configure("H1sub.TLabel", background=HEAD, foreground="#94a3b8", font=FONT)
        st.configure("Sec.TLabel", background=BG, foreground=INK, font=("DejaVu Sans", 11, "bold"))

        st.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(6, 6, 6, 0))
        st.configure("TNotebook.Tab", padding=(20, 9), background=TABBG, foreground=MUTE,
                     font=("DejaVu Sans", 10, "bold"), borderwidth=0)
        st.map("TNotebook.Tab", background=[("selected", CARD)], foreground=[("selected", ACCENT)])

        st.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=INK,
                     rowheight=27, borderwidth=1, relief="solid")
        st.configure("Treeview.Heading", background="#e2e8f0", foreground=MUTE,
                     font=("DejaVu Sans", 9, "bold"), relief="flat", padding=(6, 6))
        st.map("Treeview.Heading", background=[("active", "#d3dbe5")])
        st.map("Treeview", background=[("selected", SEL)], foreground=[("selected", INK)])

        st.configure("TButton", padding=(13, 7), background="#e6eaef", foreground=INK, borderwidth=0)
        st.map("TButton", background=[("active", "#d7dde5")])
        st.configure("Run.TButton", background=ACCENT, foreground="#ffffff",
                     font=("DejaVu Sans", 11, "bold"), padding=(18, 9))
        st.map("Run.TButton", background=[("active", "#1d4fd7")])
        st.configure("TEntry", fieldbackground=CARD, bordercolor=LINE, borderwidth=1, padding=4)
        st.configure("TCombobox", fieldbackground=CARD, padding=4)
        st.configure("TRadiobutton", background=BG)
        st.configure("TCheckbutton", background=BG)
        st.configure("TLabelframe", background=CARD, bordercolor=LINE, borderwidth=1, relief="solid")
        st.configure("TLabelframe.Label", background=CARD, foreground=MUTE, font=("DejaVu Sans", 10, "bold"))

    # ---- layout ----
    def _build(self):
        tk, ttk = self.tk, self.ttk
        HEAD = self.palette["HEAD"]
        head = tk.Frame(self.root, bg=HEAD)
        head.pack(fill="x")
        inner = tk.Frame(head, bg=HEAD)
        inner.pack(fill="x", padx=18, pady=13)
        tk.Label(inner, text="Lib-Char-Certi", bg=HEAD, fg="#ffffff",
                 font=("DejaVu Sans", 15, "bold")).pack(side="left")
        tk.Label(inner, text="   Certification Console", bg=HEAD, fg="#94a3b8",
                 font=("DejaVu Sans", 10)).pack(side="left")
        self.host_lbl = tk.Label(inner, text=f"runs: {self.runs_root}", bg=HEAD, fg="#94a3b8",
                                  font=("DejaVu Sans", 9))
        self.host_lbl.pack(side="right")

        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.tab_setup = ttk.Frame(self.nb, padding=16)
        self.tab_pipe = ttk.Frame(self.nb, padding=16)
        self.tab_res = ttk.Frame(self.nb, padding=12)
        self.tab_pr = ttk.Frame(self.nb, padding=12)
        self.tab_out = ttk.Frame(self.nb, padding=12)
        self.tab_common = ttk.Frame(self.nb, padding=12)
        self.tab_analysis = ttk.Frame(self.nb, padding=12)
        self.tab_hist = ttk.Frame(self.nb, padding=12)
        self.tab_cmp = ttk.Frame(self.nb, padding=12)
        tabs = [(self.tab_setup, "Setup"), (self.tab_pipe, "Pipeline"),
                (self.tab_res, "Results"), (self.tab_pr, "PR Status"),
                (self.tab_out, "Outliers"), (self.tab_common, "Common")]
        # Voltage Margin (Analysis) is hidden for v1 — its underlying design is still
        # in flux and would confuse users. Flip SHOW_ANALYSIS to re-enable; the tab and
        # its handlers (_build_analysis/_run_vm/_render_vm) are otherwise self-contained.
        if self.SHOW_ANALYSIS:
            tabs.append((self.tab_analysis, "Analysis"))
        tabs += [(self.tab_hist, "History"), (self.tab_cmp, "Compare")]
        for f, t in tabs:
            self.nb.add(f, text=t)
        self._build_setup()
        self._build_pipeline()
        self._build_results()
        self._build_pr_status()
        self._build_outliers()
        self._build_common()
        if self.SHOW_ANALYSIS:
            self._build_analysis()
        self._build_history()
        self._build_compare()

    def _build_setup(self):
        tk, ttk = self.tk, self.ttk
        f = self.tab_setup
        # vendor
        self.vendor = tk.StringVar(value="cdns")
        row = ttk.Frame(f); row.pack(fill="x", pady=4)
        ttk.Label(row, text="Vendor", width=16).pack(side="left")
        for v in ("cdns", "snps"):
            ttk.Radiobutton(row, text=v.upper(), value=v, variable=self.vendor,
                            command=self._on_vendor_change).pack(side="left", padx=6)

        self.e_name = self._field(f, "Batch / recipe name", "N2P v0.9 CDNS Best")
        self.e_proc = self._field(f, "Process", "n2p")
        self.e_ver = self._field(f, "Process version", "v0p9")

        # corners editor
        cf = ttk.LabelFrame(f, text="Corners", padding=10); cf.pack(fill="x", pady=8)
        top = ttk.Frame(cf); top.pack(fill="x")
        self.e_corner = ttk.Entry(top)
        self.e_corner.pack(side="left", fill="x", expand=True)
        self.e_corner.bind("<Return>", lambda e: self._add_corner())
        ttk.Button(top, text="Add", command=self._add_corner).pack(side="left", padx=4)
        ttk.Button(top, text="Remove selected", command=self._remove_corner).pack(side="left")
        self.lst_corner = tk.Listbox(cf, height=4, bg="#ffffff", fg=self.palette["INK"],
                                     relief="solid", borderwidth=1, highlightthickness=0,
                                     font=("DejaVu Sans", 10), activestyle="none",
                                     selectbackground="#dbeafe", selectforeground=self.palette["INK"])
        self.lst_corner.pack(fill="x", pady=(8, 4))
        sug = ttk.Frame(cf); sug.pack(fill="x")
        ttk.Label(sug, text="From history:").pack(side="left")
        self.cb_sug = ttk.Combobox(sug, state="readonly", width=34)
        self.cb_sug.pack(side="left", padx=6)
        ttk.Button(sug, text="+ Add", command=self._add_suggestion).pack(side="left")

        # types
        tf = ttk.Frame(f); tf.pack(fill="x", pady=8)
        ttk.Label(tf, text="Timing types", width=16).pack(side="left")
        for t in TYPES:
            var = tk.IntVar(value=1 if t in ("delay", "slew") else 0)
            self.type_vars[t] = var
            ttk.Checkbutton(tf, text=t, variable=var).pack(side="left", padx=6)

        # VT / RC type (editable: pick a preset or type a custom value)
        vrf = ttk.Frame(f); vrf.pack(fill="x", pady=4)
        ttk.Label(vrf, text="VT type", width=16).pack(side="left")
        self.cb_vt = ttk.Combobox(vrf, width=12, values=["", "svt", "elvt", "lvt", "ulvt"])
        self.cb_vt.pack(side="left", padx=(0, 12))
        ttk.Label(vrf, text="RC type", width=8).pack(side="left")
        self.cb_rc = ttk.Combobox(vrf, width=16, values=["", "cworst", "cbest", "typical", "rcworst", "rcbest"])
        self.cb_rc.pack(side="left")

        # Library structure (multi-bit cells nest pins in bundles; lookup is
        # always bundle-aware, so this is metadata/intent only)
        lrf = ttk.Frame(f); lrf.pack(fill="x", pady=4)
        ttk.Label(lrf, text="Library type", width=16).pack(side="left")
        self.cb_lib_type = ttk.Combobox(lrf, state="readonly", width=12, values=["auto", "base", "mb"])
        self.cb_lib_type.current(0)
        self.cb_lib_type.pack(side="left")

        # Input units — the tool converts Lib and FMC to ps internally. Defaults track
        # vendor/format (CDNS lib=ps, SNPS lib=ns, SCLD FMC=ns, DFDS FMC=ps); change if
        # your inputs differ. Skew is dimensionless and never converted.
        uf = ttk.Frame(f); uf.pack(fill="x", pady=4)
        ttk.Label(uf, text="FMC unit", width=16).pack(side="left")
        self.cb_fmc_unit = ttk.Combobox(uf, state="readonly", width=8, values=["ps", "ns", "us", "fs"])
        self.cb_fmc_unit.set("ps")
        self.cb_fmc_unit.pack(side="left", padx=(0, 12))
        ttk.Label(uf, text="Lib unit", width=8).pack(side="left")
        self.cb_lib_unit = ttk.Combobox(uf, state="readonly", width=8, values=["ps", "ns", "us", "fs"])
        self.cb_lib_unit.set("ps")
        self.cb_lib_unit.pack(side="left")

        # Waiver_2 abs_tol (ps) — hold Late_Sigma only. Either one value applied to all
        # corners, or per-corner "corner=val, corner2=val". User-provided; blank = off.
        af = ttk.Frame(f); af.pack(fill="x", pady=4)
        ttk.Label(af, text="abs_tol ps (hold)", width=16).pack(side="left")
        self.e_abs_tol = ttk.Entry(af)
        self.e_abs_tol.pack(side="left", fill="x", expand=True)
        ttk.Label(af, text="e.g. 19.5  or  c1=19.5, c2=20", style="Muted.TLabel").pack(side="left", padx=6)

        # FMC input mode
        mf = ttk.Frame(f); mf.pack(fill="x", pady=8)
        ttk.Label(mf, text="FMC input", width=16).pack(side="left")
        self.fmc_mode = tk.StringVar(value="decks")
        self._fmc_mode_labels = {"decks": "Decks (parse)", "parsed_dfds": "Parsed DFDS", "parsed_scld": "Parsed SCLD"}
        self.cb_mode = ttk.Combobox(mf, state="readonly", width=18,
                                    values=list(self._fmc_mode_labels.values()))
        self.cb_mode.current(0)
        self.cb_mode.pack(side="left")
        self.cb_mode.bind("<<ComboboxSelected>>", lambda e: self._on_mode_change())

        self.e_fmc = self._dir_field(f, "FMC dir (decks)",
                                     on_label=lambda lbl: setattr(self, "fmc_dir_label", lbl))
        self.e_lib = self._dir_field(f, "Lib dir")

        actions = ttk.Frame(f); actions.pack(fill="x", pady=(14, 0))
        ttk.Button(actions, text="▶  Run certification", style="Run.TButton",
                   command=self._submit).pack(side="left")
        self.setup_msg = ttk.Label(actions, text="Moments derive from FMC data — no Full-MC required.",
                                   style="Muted.TLabel")
        self.setup_msg.pack(side="left", padx=12)

    def _field(self, parent, label, default=""):
        ttk = self.ttk
        row = ttk.Frame(parent); row.pack(fill="x", pady=4)
        ttk.Label(row, text=label, width=16).pack(side="left")
        e = ttk.Entry(row); e.insert(0, default); e.pack(side="left", fill="x", expand=True)
        return e

    def _dir_field(self, parent, label, on_label=None):
        ttk = self.ttk
        from tkinter import filedialog
        row = ttk.Frame(parent); row.pack(fill="x", pady=4)
        lbl = ttk.Label(row, text=label, width=16); lbl.pack(side="left")
        if on_label is not None:
            on_label(lbl)
        e = ttk.Entry(row); e.pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Browse",
                   command=lambda: self._browse(e, filedialog)).pack(side="left", padx=4)
        return e

    def _browse(self, entry, filedialog):
        d = filedialog.askdirectory()
        if d:
            entry.delete(0, "end"); entry.insert(0, d)

    def _build_pipeline(self):
        tk, ttk = self.tk, self.ttk
        f = self.tab_pipe
        self.pipe_banner = ttk.Label(f, text="No run yet — configure one in Setup.",
                                     style="Sec.TLabel")
        self.pipe_banner.pack(anchor="w", pady=(0, 4))
        self.audit_banner = tk.Label(f, text="", anchor="w", padx=10, pady=4,
                                     font=("DejaVu Sans", 10, "bold"))
        self.audit_banner.pack(fill="x", pady=(0, 10))
        self.stage_lbls = {}
        grid = ttk.Frame(f); grid.pack(fill="x")
        for i, (key, name) in enumerate(STAGES):
            cell = ttk.LabelFrame(grid, text=name, padding=14)
            cell.grid(row=0, column=i, padx=5, sticky="nsew")
            grid.columnconfigure(i, weight=1)
            lbl = ttk.Label(cell, text="pending", style="Card.TLabel",
                            font=("DejaVu Sans", 11, "bold"), foreground=STATE_FG["pending"])
            lbl.pack()
            self.stage_lbls[key] = lbl
        # high-level live log (C) + full-audit-report access
        logbar = ttk.Frame(f); logbar.pack(fill="x", pady=(16, 4))
        ttk.Label(logbar, text="Log", style="Sec.TLabel").pack(side="left")
        ttk.Button(logbar, text="Open audit report", command=self._open_audit_report).pack(side="right")
        logwrap = ttk.Frame(f); logwrap.pack(fill="both", expand=True)
        self.log_text = tk.Text(logwrap, height=12, wrap="word", relief="solid", borderwidth=1,
                                bg="#0e1518", fg="#cfe6db", insertbackground="#cfe6db",
                                font=("DejaVu Sans Mono", 9), padx=8, pady=6)
        lsb = ttk.Scrollbar(logwrap, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=lsb.set, state="disabled")
        self.log_text.tag_configure("err", foreground="#ff8c8c")
        self.log_text.tag_configure("warn", foreground="#ffce80")
        self.log_text.tag_configure("ok", foreground="#7ee0a4")
        self.log_text.pack(side="left", fill="both", expand=True)
        lsb.pack(side="right", fill="y")
        self._logged_stage_state = {}

    def _log(self, msg, tag=None):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n", (tag,) if tag else ())
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _audit_report_path(self):
        """logs/audit_report.txt for the active run, else the loaded batch."""
        from pathlib import Path
        bid = self.active_job
        if not bid:
            rec = getattr(self, "loaded_rec", None)
            bid = rec.get("id") if rec else None
        if not bid:
            return None
        p = Path(runs.batch_dir(self.runs_root, bid)) / "logs" / "audit_report.txt"
        return p if p.is_file() else None

    def _open_audit_report(self):
        tk = self.tk
        from tkinter import messagebox
        p = self._audit_report_path()
        if not p:
            return messagebox.showinfo(
                "Audit report",
                "No audit_report.txt yet. Run a batch (or open one from History) first.\n"
                "The report is written to <run>/logs/audit_report.txt.")
        win = tk.Toplevel(self.root)
        win.title(f"Audit report — {p.parent.parent.name}")
        win.geometry("760x560")
        txt = tk.Text(win, wrap="word", font=("DejaVu Sans Mono", 9), padx=10, pady=8)
        sb = self.ttk.Scrollbar(win, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        txt.tag_configure("err", foreground="#b91c1c")
        txt.tag_configure("warn", foreground="#b45309")
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            tag = "err" if line.startswith("[ERROR]") else "warn" if line.startswith("[WARN]") else None
            txt.insert("end", line + "\n", (tag,) if tag else ())
        txt.configure(state="disabled")
        txt.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def _build_results(self):
        tk, ttk = self.tk, self.ttk
        f = self.tab_res
        self.basis = getattr(self, "basis", "base")
        bar = ttk.Frame(f); bar.pack(fill="x", pady=(0, 6))
        self.res_title = ttk.Label(bar, text="No batch loaded.", style="Sec.TLabel")
        self.res_title.pack(side="left")
        self.btn_rerun = ttk.Button(bar, text="Rerun config", command=self._rerun_loaded)
        self.btn_rerun.pack(side="right")
        self.btn_export = ttk.Button(bar, text="Export CSV", command=self._export_csv)
        self.btn_export.pack(side="right", padx=6)
        # Base / +Waiver1 toggle
        self.basis_var = tk.StringVar(value=self.basis)
        seg = ttk.Frame(bar); seg.pack(side="right", padx=10)
        ttk.Label(seg, text="PR:", style="Muted.TLabel").pack(side="left")
        for key, txt in (("base", "Base"), ("w1", "+Waiver1"), ("w2", "+Waiver2")):
            ttk.Radiobutton(seg, text=txt, value=key, variable=self.basis_var,
                            command=self._on_basis_change).pack(side="left")
        # verdict banner
        self.verdict_lbl = tk.Label(f, text="", anchor="w", padx=14, pady=10,
                                    font=("DejaVu Sans", 13, "bold"))
        self.verdict_lbl.pack(fill="x", pady=(0, 8))
        # scrollable body for per-type sections
        wrap = ttk.Frame(f); wrap.pack(fill="both", expand=True)
        self.res_canvas = tk.Canvas(wrap, highlightthickness=0, bg=self.palette["BG"])
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.res_canvas.yview)
        self.res_body = ttk.Frame(self.res_canvas)
        self.res_body.bind("<Configure>",
                           lambda e: self.res_canvas.configure(scrollregion=self.res_canvas.bbox("all")))
        self.res_canvas.create_window((0, 0), window=self.res_body, anchor="nw")
        self.res_canvas.configure(yscrollcommand=sb.set)
        self.res_canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def _on_basis_change(self):
        self.basis = self.basis_var.get()
        self._render_results()

    def _make_table(self, parent, cols):
        ttk = self.ttk
        tv = ttk.Treeview(parent, columns=cols, show="headings", height=7, selectmode="browse")
        for c in cols:
            tv.heading(c, text=c)
            tv.column(c, width=110, anchor="center")
        tv.column(cols[0], width=160, anchor="w")
        tv.pack(fill="x", pady=(2, 6))
        for h, bg in HEALTH_BG.items():
            tv.tag_configure(h, background=bg)
        return tv

    # ---- PR Status (consolidated Table 1) ----
    def _pr_records(self) -> list:
        """Records to consolidate: History CHECKED rows, else every batch."""
        checked = getattr(self, "_hist_checked", set())
        index_ids = [row["id"] for row in runs.read_index(self.runs_root)]
        ids = [i for i in index_ids if i in checked] if checked else index_ids
        recs = [runs.read_run_record(self.runs_root, i) for i in ids]
        return [r for r in recs if r]

    def _build_pr_status(self):
        tk, ttk = self.tk, self.ttk
        f = self.tab_pr
        self.pr_basis = getattr(self, "pr_basis", "w1")
        bar = ttk.Frame(f); bar.pack(fill="x", pady=(0, 6))
        ttk.Label(bar, text="Consolidated PR — all batches (or select rows in History first)",
                  style="Sec.TLabel").pack(side="left")
        ttk.Button(bar, text="Build", command=self._render_pr_status).pack(side="right")
        ttk.Button(bar, text="Export CSV", command=self._export_pr_csv).pack(side="right", padx=6)
        self.pr_basis_var = tk.StringVar(value=self.pr_basis)
        seg = ttk.Frame(bar); seg.pack(side="right", padx=10)
        ttk.Label(seg, text="PR:", style="Muted.TLabel").pack(side="left")
        for key, txt in (("base", "Base"), ("w1", "+Waiver1"), ("w2", "+Waiver2")):
            ttk.Radiobutton(seg, text=txt, value=key, variable=self.pr_basis_var,
                            command=self._on_pr_basis).pack(side="left")
        wrap = ttk.Frame(f); wrap.pack(fill="both", expand=True)
        self.pr_canvas = tk.Canvas(wrap, highlightthickness=0, bg=self.palette["BG"])
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.pr_canvas.yview)
        self.pr_body = ttk.Frame(self.pr_canvas)
        self.pr_body.bind("<Configure>",
                          lambda e: self.pr_canvas.configure(scrollregion=self.pr_canvas.bbox("all")))
        self.pr_canvas.create_window((0, 0), window=self.pr_body, anchor="nw")
        self.pr_canvas.configure(yscrollcommand=sb.set)
        self.pr_canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def _on_pr_basis(self):
        self.pr_basis = self.pr_basis_var.get()
        self._render_pr_status()

    def _render_pr_status(self):
        tk = self.tk
        for w in self.pr_body.winfo_children():
            w.destroy()
        records = self._pr_records()
        if not records:
            tk.Label(self.pr_body, text="No batches yet. Run one in Setup (or select rows in History), then Build.",
                     bg=self.palette["BG"], fg=self.palette["MUTE"]).grid(row=0, column=0, sticky="w")
            return
        piv = _consolidate.consolidate_pr(records, basis=self.pr_basis)
        cols, rows, cells = piv["columns"], piv["rows"], piv["cells"]
        HEAD, INK, CARD = self.palette["HEAD"], self.palette["INK"], self.palette["CARD"]
        tk.Label(self.pr_body, text="Data_Type", bg=HEAD, fg="#ffffff", anchor="w",
                 font=("DejaVu Sans", 10, "bold"), padx=10, pady=6).grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
        for ci, col in enumerate(cols):
            hdr = f"{col['batch_id']}\n{col['vt']}·{col['libtype']} · {short_corner(col['corner'])}"
            tk.Label(self.pr_body, text=hdr, bg=HEAD, fg="#ffffff",
                     font=("DejaVu Sans", 8, "bold"), padx=6, pady=4).grid(row=0, column=ci + 1, sticky="nsew", padx=1, pady=1)
        r, last_cls = 1, None
        for row in rows:
            if row["cls"] != last_cls:
                sec = "CONS · hold arcs" if row["cls"] == "cons" else "NON_CONS · delay·slew arcs"
                tk.Label(self.pr_body, text=sec, bg="#dde5ee", fg=INK, anchor="w",
                         font=("DejaVu Sans", 9, "bold"), padx=10, pady=3).grid(
                    row=r, column=0, columnspan=len(cols) + 1, sticky="nsew", padx=1, pady=1)
                r += 1; last_cls = row["cls"]
            tk.Label(self.pr_body, text=row["label"], bg=CARD, fg=INK, anchor="w",
                     padx=10, pady=4).grid(row=r, column=0, sticky="nsew", padx=1, pady=1)
            for ci in range(len(cols)):
                cell = cells[(row["label"], ci)]
                cls = _COLOR2CLS.get(cell["color"], "na")
                tk.Label(self.pr_body, text=fmt_pr(cell["pr"]), bg=PR_BG[cls], fg=PR_FG[cls],
                         font=("DejaVu Sans", 10, "bold"), padx=8, pady=4).grid(
                    row=r, column=ci + 1, sticky="nsew", padx=1, pady=1)
            r += 1

    def _export_pr_csv(self):
        from tkinter import filedialog, messagebox
        import csv as _csv
        records = self._pr_records()
        if not records:
            return messagebox.showinfo("Export", "No batches to export.")
        piv = _consolidate.consolidate_pr(records, basis=getattr(self, "pr_basis", "w1"))
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="pr_status.csv")
        if not path:
            return
        cols = piv["columns"]
        with open(path, "w", newline="") as fh:
            w = _csv.writer(fh)
            w.writerow(["Data_Type", "Class"] +
                       [f"{c['batch_id']}|{c['vt']}|{c['libtype']}|{c['corner']}" for c in cols])
            for row in piv["rows"]:
                line = [row["label"], row["cls"]]
                for ci in range(len(cols)):
                    pr = piv["cells"][(row["label"], ci)]["pr"]
                    line.append("" if pr is None else f"{pr:.1f}")
                w.writerow(line)
        messagebox.showinfo("Export", f"Wrote {path}")

    # ---- Outliers (Table 2) + scatter drill-down ----
    def _build_outliers(self):
        ttk = self.ttk
        f = self.tab_out
        bar = ttk.Frame(f); bar.pack(fill="x", pady=(0, 6))
        ttk.Label(bar, text="Sub-95% points — double-click a row for the outlier scatter",
                  style="Sec.TLabel").pack(side="left")
        ttk.Button(bar, text="Build", command=self._render_outliers).pack(side="right")
        cols = ["Metric", "Class", "Batch · Corner", "PR%", "#cells", "#opt", "#pess",
                "Polarity", "WorstErr(ps)", "RelErr%"]
        self.tv_out = ttk.Treeview(f, columns=cols, show="headings", selectmode="browse")
        for c in cols:
            self.tv_out.heading(c, text=c)
            self.tv_out.column(c, width=104, anchor="center")
        self.tv_out.column("Metric", width=150, anchor="w")
        self.tv_out.column("Batch · Corner", width=210, anchor="w")
        self.tv_out.pack(fill="both", expand=True)
        self.tv_out.bind("<Double-1>", self._open_scatter_selected)
        self.out_hint = ttk.Label(
            f, style="Muted.TLabel",
            text="Click Build to list sub-95% points.  “?” = per-arc detail unavailable "
                 "(combined/sigma CSV not found for that corner/type).")
        self.out_hint.pack(anchor="w", pady=(4, 0))
        self._out_meta: dict = {}

    def _render_outliers(self):
        self.tv_out.delete(*self.tv_out.get_children())
        self._out_meta = {}
        basis = getattr(self, "pr_basis", "w1")
        for rec in self._pr_records():
            rid = rec.get("id")
            bid = rec.get("batch_id") or rec.get("name", "?")
            bdir = runs.batch_dir(self.runs_root, rid) if rid else None
            sig = {(s["corner"], s["type"]): s for s in rec.get("sigma", [])}
            mom = {(m["corner"], m["type"]): m for m in rec.get("moments", [])}
            for prow in _consolidate.PR_ROWS:
                corners = sorted({c for (c, t) in list(sig) + list(mom) if t == prow["type"]})
                for corner in corners:
                    s, m = sig.get((corner, prow["type"])), mom.get((corner, prow["type"]))
                    pr = _consolidate._value(prow["metric"], basis, s, m)
                    if pr is None or pr >= _consolidate.GREEN_LOW:
                        continue
                    br = {"n_outlier_cells": "?", "n_optimistic": "?", "n_pessimistic": "?",
                          "polarity": "?", "worst_err_ps": None, "worst_rel_pct": None}
                    if bdir is not None:
                        csvp = _perarc.find_per_arc_csv(bdir, corner, prow["type"], prow["metric"])
                        if csvp:
                            br = _outliers.outlier_breakdown(_perarc.load_rows(csvp), prow["metric"])
                    iid = self.tv_out.insert("", "end", values=(
                        prow["label"], prow["cls"], f"{bid} · {short_corner(corner)}", f"{pr:.1f}",
                        br.get("n_outlier_cells", "?"), br.get("n_optimistic", "?"),
                        br.get("n_pessimistic", "?"), br.get("polarity", "?"),
                        "" if br.get("worst_err_ps") is None else f"{br['worst_err_ps']:.2f}",
                        "" if br.get("worst_rel_pct") is None else f"{br['worst_rel_pct']:.1f}"))
                    self._out_meta[iid] = (rid, corner, prow["type"], prow["metric"],
                                           f"{prow['label']} — {bid} · {short_corner(corner)}")
        if not self.tv_out.get_children():
            self.out_hint.configure(
                text="No sub-95% points found — every metric passes, or no batch is loaded "
                     "(open/select a batch in History first).")
        else:
            self.out_hint.configure(
                text="Double-click a row for the outlier scatter.  “?” = per-arc detail "
                     "unavailable (combined/sigma CSV not found for that corner/type).")

    # ---- Common offenders (cross-corner / cross-batch) ----
    def _build_common(self):
        ttk = self.ttk
        f = self.tab_common
        bar = ttk.Frame(f); bar.pack(fill="x", pady=(0, 6))
        ttk.Label(bar, text="Common offenders — cells/arcs failing across corners & batches "
                            "(select batches in History, or all)", style="Sec.TLabel").pack(side="left")
        ctl = ttk.Frame(f); ctl.pack(fill="x", pady=(0, 6))
        ttk.Label(ctl, text="Metric row:").pack(side="left")
        self.cb_common_row = ttk.Combobox(ctl, state="readonly", width=18,
                                          values=[r["label"] for r in _consolidate.PR_ROWS])
        self.cb_common_row.current(0)
        self.cb_common_row.pack(side="left", padx=6)
        ttk.Label(ctl, text="Group by:").pack(side="left", padx=(10, 0))
        self.common_key = self.tk.StringVar(value="cell")
        for key, txt in (("cell", "cell"), ("cell_arc", "cell+arc"),
                         ("cell_table_point", "cell+table point")):
            ttk.Radiobutton(ctl, text=txt, value=key, variable=self.common_key).pack(side="left")
        ttk.Button(ctl, text="Build", command=self._render_common).pack(side="right")
        cols = ["Offender", "#contexts", "#fails", "Worst rel%", "WorstErr(ps)", "Polarity"]
        self.tv_common = ttk.Treeview(f, columns=cols, show="headings", selectmode="browse")
        for c in cols:
            self.tv_common.heading(c, text=c)
            self.tv_common.column(c, width=100, anchor="center")
        self.tv_common.column("Offender", width=280, anchor="w")
        self.tv_common.pack(fill="both", expand=True)
        self.tv_common.bind("<Double-1>", self._show_common_contexts)
        self.common_hint = ttk.Label(
            f, style="Muted.TLabel",
            text="Pick a metric row and click Build to find offenders shared across contexts.")
        self.common_hint.pack(anchor="w", pady=(4, 0))
        self._common_meta: dict = {}

    def _render_common(self):
        from ..analysis import common as _common
        self.tv_common.delete(*self.tv_common.get_children())
        self._common_meta = {}
        label = self.cb_common_row.get()
        prow = next((r for r in _consolidate.PR_ROWS if r["label"] == label), None)
        if not prow:
            return
        per_ctx: dict = {}
        for rec in self._pr_records():
            rid = rec.get("id")
            bid = rec.get("batch_id") or rec.get("name", "?")
            bdir = runs.batch_dir(self.runs_root, rid) if rid else None
            if bdir is None:
                continue
            corners = sorted({s["corner"] for s in rec.get("sigma", []) if s["type"] == prow["type"]}
                             | {m["corner"] for m in rec.get("moments", []) if m["type"] == prow["type"]})
            for corner in corners:
                csvp = _perarc.find_per_arc_csv(bdir, corner, prow["type"], prow["metric"])
                if csvp:
                    per_ctx[(bid, corner)] = _perarc.load_rows(csvp)
        offenders = _common.common_offenders(per_ctx, prow["metric"], key=self.common_key.get())
        # Stash so the detail popup can re-scan WHERE each offender fails.
        self._common_per_ctx = per_ctx
        self._common_metric = prow["metric"]
        self._common_key = self.common_key.get()
        for d in offenders:
            iid = self.tv_common.insert("", "end", values=(
                d["key"], d["n_contexts"], d["n_fail_total"], f"{d['worst_rel_pct']:.1f}",
                f"{d['worst_err_ps']:.2f}", d["polarity"]))
            self._common_meta[iid] = d
        if not offenders:
            self.common_hint.configure(
                text="No common offenders found for this metric — no per-arc failures shared "
                     "across the loaded/selected batches (load batches in History first).")
        else:
            self.common_hint.configure(
                text=f"{len(offenders)} offender(s) — double-click one to see where it fails.")

    def _offender_matches(self, arc: str, d: dict) -> bool:
        """Does a failing arc belong to this offender, given the active group key?"""
        from ..analysis import outliers as _o
        key = getattr(self, "_common_key", "cell")
        if key == "cell_arc":
            return arc == d["arc"]
        if key == "cell_table_point":
            return _o._cell_of(arc) == d["cell"] and _o.arc_indices(arc) == (d["index1"], d["index2"])
        return _o._cell_of(arc) == d["cell"]

    def _show_common_contexts(self, _evt=None):
        tk, ttk = self.tk, self.ttk
        from ..analysis import outliers as _o
        sel = self.tv_common.selection()
        if not sel:
            return
        d = self._common_meta.get(sel[0])
        if not d:
            return
        metric = getattr(self, "_common_metric", "Late_Sigma")
        per_ctx = getattr(self, "_common_per_ctx", {})
        win = tk.Toplevel(self.root)
        win.title(f"Where it fails — {d['key']}")
        win.geometry("820x460")
        ttk.Label(win, text=f"{d['key']}  —  fails in {d['n_contexts']} context(s), "
                            f"{d['n_fail_total']} arc-fails, polarity={d['polarity']}",
                  style="Sec.TLabel").pack(anchor="w", padx=8, pady=(8, 4))
        cols = ["Batch · Corner", "Arc", "idx1", "idx2", "MC", "Lib", "SignedErr", "Rel%", "Dir"]
        wrap = ttk.Frame(win); wrap.pack(fill="both", expand=True, padx=8, pady=4)
        tv = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="browse")
        sb = ttk.Scrollbar(wrap, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        for c in cols:
            tv.heading(c, text=c)
            tv.column(c, width=70, anchor="center")
        tv.column("Batch · Corner", width=170, anchor="w")
        tv.column("Arc", width=230, anchor="w")
        # Re-scan each context for THIS offender's failing arcs (the "where").
        for (bid, corner) in d["contexts"]:
            for r, mc, lib, ae, rel in _o._failing(per_ctx.get((bid, corner), []), metric):
                arc = r.get("Arc", "")
                if not self._offender_matches(arc, d):
                    continue
                i1, i2 = _o.arc_indices(arc)
                tv.insert("", "end", values=(
                    f"{bid} · {short_corner(corner)}", arc, i1, i2,
                    round(mc, 3), round(lib, 3), round(lib - mc, 3),
                    f"{rel:.2f}", "opt" if lib < mc else "pess"))
        tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def _open_scatter_selected(self, _evt=None):
        sel = self.tv_out.selection()
        if not sel:
            return
        meta = self._out_meta.get(sel[0])
        if meta:
            self._open_scatter(*meta)

    def _open_scatter(self, rid, corner, row_type, metric, label):
        """Open the enriched outlier drill-down panel (matplotlib + rankings).
        Falls back to the Canvas scatter if matplotlib is unavailable."""
        tk = self.tk
        from tkinter import messagebox
        if not rid:
            return messagebox.showinfo("Scatter", "No batch directory for this point.")
        csvp = _perarc.find_per_arc_csv(runs.batch_dir(self.runs_root, rid), corner, row_type, metric)
        if not csvp:
            return messagebox.showinfo("Scatter", "Per-arc data not found for this point.")
        rows = _perarc.load_rows(csvp)
        pts = _perarc.scatter_points(rows, metric)
        if not pts:
            return messagebox.showinfo("Scatter", "No covered arcs to plot.")
        # Remember context so the arc-detail popup can trace back to the source files.
        self._scatter_ctx = (rid, corner, row_type)
        try:
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
            from ..analysis import plots as _plots
        except ImportError:
            # Only fall back when matplotlib is genuinely absent — a narrow except so real
            # bugs in the enriched panel surface instead of silently degrading to Canvas.
            return self._open_scatter_canvas(pts, label, metric)
        self._open_scatter_mpl(label, metric, rows, pts, FigureCanvasTkAgg, NavigationToolbar2Tk, _plots)

    def _open_scatter_mpl(self, label, metric, rows, pts, FigureCanvasTkAgg, NavToolbar, plots):
        """Enriched panel: matplotlib scatter + ranked lists, in a draggable split.

        The figure/canvas/toolbar are built ONCE; selections and mode/filter changes
        only clear+redraw the same figure (canvas.draw_idle), so interaction is fast
        even with thousands of points (the old per-point, rebuild-everything path
        took minutes over X11)."""
        tk, ttk = self.tk, self.ttk
        from ..analysis import outliers as _o
        win = tk.Toplevel(self.root)
        win.title(f"Outlier analysis — {label}")
        win.geometry("1100x640")
        # Default the rel-error scale to log only when the spread is wide; the user
        # can switch Normal/Log freely below (only affects the Abs·Rel err mode).
        auto_log = plots.auto_log_recommended(pts, "abs_vs_rel")
        state = {"mode": "lib_vs_mc", "highlight": set(), "polarity": "all",
                 "scale": "symlog" if auto_log else "linear"}

        # Draggable horizontal split: plot (left, weight 3) | rankings (right, weight 1)
        pw = ttk.PanedWindow(win, orient="horizontal")
        pw.pack(fill="both", expand=True)
        left = ttk.Frame(pw)
        right = ttk.Frame(pw, padding=6)
        pw.add(left, weight=3)
        pw.add(right, weight=1)

        bar = ttk.Frame(left); bar.pack(fill="x")
        mode_var = tk.StringVar(value="lib_vs_mc")
        pol_var = tk.StringVar(value="all")
        scale_var = tk.StringVar(value=state["scale"])

        fig = plots.build_scatter_figure(pts, metric, mode="lib_vs_mc", rel_threshold=0.03)
        canvas = FigureCanvasTkAgg(fig, master=left)
        toolbar = NavToolbar(canvas, left)
        toolbar.update()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        holder = {"fig": fig}

        def redraw():
            plots.build_scatter_figure(
                pts, metric, mode=state["mode"], highlight=state["highlight"],
                rel_threshold=0.03, polarity=state["polarity"],
                scale=state["scale"], fig=holder["fig"])
            canvas.draw_idle()

        def set_mode():
            state["mode"] = mode_var.get(); redraw()

        def set_polarity():
            # Polarity filters BOTH the scatter and the ranking tables.
            state["polarity"] = pol_var.get(); state["highlight"] = set()
            rebuild_tables(); redraw()

        def set_scale():
            state["scale"] = scale_var.get(); redraw()

        for key, txt in (("lib_vs_mc", "Lib vs MC"), ("abs_vs_rel", "Abs·Rel err")):
            ttk.Radiobutton(bar, text=txt, value=key, variable=mode_var,
                            command=set_mode).pack(side="left", padx=4)
        ttk.Label(bar, text="Show:").pack(side="left", padx=(10, 0))
        for key, txt in (("all", "All"), ("opt", "Optimistic"), ("pess", "Pessimistic")):
            ttk.Radiobutton(bar, text=txt, value=key, variable=pol_var,
                            command=set_polarity).pack(side="left")
        ttk.Label(bar, text="Scale:").pack(side="left", padx=(10, 0))
        for key, txt in (("linear", "Normal"), ("symlog", "Log")):
            ttk.Radiobutton(bar, text=txt, value=key, variable=scale_var,
                            command=set_scale).pack(side="left")

        def save_png():
            from tkinter import filedialog
            p = filedialog.asksaveasfilename(defaultextension=".png", initialfile="outliers.png")
            if p:
                plots.save_figure(holder["fig"], p, dpi=200)

        ttk.Button(bar, text="Save PNG", command=save_png).pack(side="right", padx=4)

        tbl_holder = ttk.Frame(right); tbl_holder.pack(fill="both", expand=True)

        def add_table(title, cols, data, arcs_for, detail=False):
            ttk.Label(tbl_holder, text=title, style="Sec.TLabel").pack(anchor="w", pady=(6, 0))
            wrap = ttk.Frame(tbl_holder); wrap.pack(fill="both", expand=True)
            tv = ttk.Treeview(wrap, columns=cols, show="headings", height=7, selectmode="browse")
            sb = ttk.Scrollbar(wrap, orient="vertical", command=tv.yview)
            tv.configure(yscrollcommand=sb.set)
            for c in cols:
                tv.heading(c, text=c)
                tv.column(c, width=120 if c == "cell" else 70, anchor="w" if c == "cell" else "center")
            for d in data:
                tv.insert("", "end", values=tuple(_fmt_cell(d.get(c, "")) for c in cols))
            tv.pack(side="left", fill="both", expand=True)
            sb.pack(side="right", fill="y")
            def on_sel(_e, _tv=tv, _data=data, _af=arcs_for):
                sel = _tv.selection()
                if sel:
                    state["highlight"] = _af(_data[_tv.index(sel[0])])
                    redraw()
            tv.bind("<<TreeviewSelect>>", on_sel)
            if detail:
                def on_dbl(_e, _tv=tv, _data=data):
                    sel = _tv.selection()
                    if sel:
                        self._show_arc_detail(_data[_tv.index(sel[0])], metric)
                tv.bind("<Double-1>", on_dbl)

        def _fmt_cell(v):
            return f"{v:.1f}" if isinstance(v, float) else v

        arcset = lambda pred: {p[3] for p in pts if pred(p[3])}

        def rebuild_tables():
            # Re-rank with the active polarity filter (All / Optimistic / Pessimistic).
            for w in tbl_holder.winfo_children():
                w.destroy()
            pol = state["polarity"]
            cells = _o.rank_by_cell(rows, metric, polarity=pol)
            tps = _o.rank_by_table_point(rows, metric, polarity=pol)
            worst = _o.worst_arcs(rows, metric, top=30, polarity=pol)
            add_table("Top cells (n_fail · opt/pess · worst%)",
                      ["cell", "n_fail", "n_opt", "n_pess", "worst_rel_pct"], cells,
                      lambda d: arcset(lambda a: _o._cell_of(a) == d["cell"]))
            add_table("Top table points",
                      ["index1", "index2", "n_fail", "worst_rel_pct"], tps,
                      lambda d: arcset(lambda a: _o.arc_indices(a) == (d["index1"], d["index2"])))
            add_table("Worst arcs (double-click for MC/Lib detail)",
                      ["cell", "rel_pct", "abs_err_ps", "direction"], worst,
                      lambda d: {d["arc"]}, detail=True)

        rebuild_tables()

    def _resolve_input_paths(self, rid, corner, row_type):
        """From the run manifest, find the .lib file (lib-join) and FMC input file
        (FMC stage) used for this (corner, type). Returns (lib_path, fmc_path)."""
        lib_path = fmc_path = None
        if not rid:
            return None, None
        man = Path(runs.batch_dir(self.runs_root, rid)) / "run_manifest.json"
        try:
            data = json.loads(man.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        for st in data.get("stage_execution", []):
            if st.get("stage") == "lib_join_sigma":
                for p in st.get("processed", []):
                    name = Path(str(p.get("csv", ""))).name
                    if f"_{corner}_" in name and row_type in name:
                        lib_path = p.get("lib"); break
            elif st.get("stage") == "fmc_combine_data":
                group = "cons" if row_type in ("hold", "mpw") else "delay"
                for p in st.get("processed", []):
                    src_name = Path(str(p.get("src", ""))).name
                    exact = p.get("corner") == corner and p.get("type") == row_type
                    by_name = any(mt in src_name for mt in _fmc_corner_matchers(corner)) and \
                        (group in src_name.lower() or row_type in src_name.lower())
                    if (exact or by_name) and p.get("src"):
                        fmc_path = p.get("src"); break
        # Config for THIS outlier's batch (not whatever was last opened in Results).
        rec = runs.read_run_record(self.runs_root, rid) or {}
        cfg = rec.get("config", {})
        if not fmc_path:
            # No per-file src in the manifest (decks mode / older run): search the FMC
            # input dir (recursively, data files only) for the corner's golden file.
            fdir = cfg.get("fmc_input_dir") or cfg.get("fmc_golden_dir")
            if fdir:
                fmc_path = fdir          # at least show the directory we were given
                got = _find_fmc_file(fdir, corner, row_type)
                if got:
                    fmc_path = got       # upgrade to the specific corner file
        return lib_path, fmc_path

    def _peek_file(self, path, needle, title, whole_cell=False, max_lines=8000):
        """Stream a (possibly huge) file and show the relevant region for `needle`.

        whole_cell=True (lib): from the matching `cell (...)` line, capture the ENTIRE
        brace-balanced block (tracks { } depth). whole_cell=False (FMC): collect ALL
        lines containing the cell (every arc row for that cell). Streamed, never loads
        the whole file."""
        tk = self.tk
        from tkinter import messagebox
        if not path:
            return messagebox.showinfo("Peek", "No path.")
        if Path(path).is_dir():
            # Diagnostic: we only resolved to the directory — list its data files so the
            # exact corner file can be identified (and the matcher fixed if needed).
            try:
                names = sorted(p.name for p in Path(path).rglob("*")
                               if p.is_file() and p.suffix.lower() in (".csv", ".rpt", ".txt"))
            except OSError as exc:
                return messagebox.showinfo("Peek", f"Read error: {exc}")
            window = [f"(directory — could not match a specific corner file for '{needle}')",
                      f"{len(names)} data file(s) in {path}:", ""] + names
            ln = 0
            return self._peek_window(path, needle, window, ln, "Directory listing", False)
        if not Path(path).is_file():
            return messagebox.showinfo("Peek", f"File not found:\n{path}")
        try:
            window, ln = _scan_file_region(path, needle, whole_cell, max_lines)
        except OSError as exc:
            return messagebox.showinfo("Peek", f"Read error: {exc}")
        if not window:
            return messagebox.showinfo("Peek", f"'{needle}' not found in\n{path}")
        kind = "cell block" if whole_cell else "matching rows"
        self._peek_window(path, needle, window, ln, kind, whole_cell)

    def _peek_window(self, path, needle, window, ln, kind, whole_cell):
        tk = self.tk
        win = tk.Toplevel(self.root)
        win.title(f"{kind} — {len(window)} line(s) from {Path(path).name}")
        win.geometry("960x600")
        t = tk.Text(win, wrap="none", font=("DejaVu Sans Mono", 9), padx=8, pady=6)
        sb = self.ttk.Scrollbar(win, orient="vertical", command=t.yview)
        sbx = self.ttk.Scrollbar(win, orient="horizontal", command=t.xview)
        t.configure(yscrollcommand=sb.set, xscrollcommand=sbx.set)
        t.insert("end", f"# {path}\n# {kind} for '{needle}' (first at line {ln})\n\n" + "\n".join(window))
        t.configure(state="disabled")
        sb.pack(side="right", fill="y"); sbx.pack(side="bottom", fill="x")
        t.pack(side="left", fill="both", expand=True)

    def _copy_path(self, path):
        from tkinter import messagebox
        try:
            self.root.clipboard_clear(); self.root.clipboard_append(str(path))
        except Exception as exc:
            # Don't claim success when the clipboard is unavailable (common over X11);
            # show the path so the user can copy it by hand.
            return messagebox.showwarning(
                "Copy failed",
                f"Could not access the clipboard ({exc}).\nCopy this path manually:\n\n{path}")
        messagebox.showinfo("Copied", f"Path copied to clipboard:\n{path}")

    def _show_arc_detail(self, d, metric):
        """Popup with the full numbers for one outlier arc + links back to the
        source .lib and FMC input files (copy path / peek the cell or arc)."""
        tk, ttk = self.tk, self.ttk
        from ..analysis.plots import metric_unit
        unit = metric_unit(metric) or "ps"
        rid, corner, row_type = getattr(self, "_scatter_ctx", (None, None, None))
        lib_path, fmc_path = self._resolve_input_paths(rid, corner, row_type)
        cell = d.get("cell", "")
        win = tk.Toplevel(self.root)
        win.title(f"Arc detail — {cell}")
        win.geometry("760x420")
        txt = tk.Text(win, height=12, font=("DejaVu Sans Mono", 9), padx=10, pady=8)
        mc, lib = d.get("mc"), d.get("lib")
        signed = (lib - mc) if (mc is not None and lib is not None) else None
        ae = d.get("abs_err_ps", 0.0)
        rel = d.get("rel_pct", 0.0)
        denom = (ae / (rel / 100.0)) if rel else None
        lines = [
            f"Arc        : {d.get('arc', '')}",
            f"Cell       : {cell}",
            f"Table point: index1={d.get('index1', '')}  index2={d.get('index2', '')}",
            "",
            f"{metric}:",
            f"  MC value   : {mc} {unit}",
            f"  Lib value  : {lib} {unit}",
            f"  Signed err : {signed if signed is None else round(signed, 4)} {unit}  (Lib - MC)",
            f"  Abs err    : {round(ae, 4)} {unit}",
            f"  Rel err    : {round(rel, 3)} %   (engine denominator = max(|Nominal|,|MC|))",
            f"  Denominator: {round(denom, 3) if denom else 'n/a'} {unit}",
            f"  Direction  : {d.get('direction', '')}"
            + ("   (optimistic = Lib<MC, library claims better than MC)"
               if d.get("direction") == "optimistic" else ""),
        ]
        txt.insert("end", "\n".join(lines))
        txt.configure(state="disabled")
        txt.pack(fill="x")

        # Source-file trace-back: copy the path, or peek the cell/arc inside the file.
        src = ttk.LabelFrame(win, text="Trace back to source", padding=8)
        src.pack(fill="x", padx=8, pady=8)
        def row(label, path, peek_needle, peek_title, whole):
            r = ttk.Frame(src); r.pack(fill="x", pady=2)
            ttk.Label(r, text=label, width=10).pack(side="left")
            shown = (str(path)[:70] + "…") if path and len(str(path)) > 70 else (path or "(not found)")
            ttk.Label(r, text=shown, style="Muted.TLabel").pack(side="left", fill="x", expand=True)
            if path:
                ttk.Button(r, text="Copy", width=6,
                           command=lambda p=path: self._copy_path(p)).pack(side="right", padx=2)
                ttk.Button(r, text="Peek", width=6,
                           command=lambda p=path, n=peek_needle, t=peek_title, wc=whole:
                           self._peek_file(p, n, t, whole_cell=wc)).pack(side="right", padx=2)
        # Lib: whole cell block (brace-balanced). FMC: all arc rows for the cell.
        row("Lib file", lib_path, f"cell ({cell})", f"Lib cell {cell}", True)
        row("FMC input", fmc_path, cell, f"FMC rows for {cell}", False)
        # The exact per-arc deck/log path, pulled from the FMC golden's 'deck' column.
        deck = _fmc_deck_for_arc(fmc_path, cell, d.get("index1", ""), d.get("index2", "")) \
            if fmc_path and Path(str(fmc_path)).is_file() else None
        if deck:
            r = ttk.Frame(src); r.pack(fill="x", pady=2)
            ttk.Label(r, text="FMC deck", width=10).pack(side="left")
            shown = (deck[:70] + "…") if len(deck) > 70 else deck
            ttk.Label(r, text=shown, style="Muted.TLabel").pack(side="left", fill="x", expand=True)
            ttk.Button(r, text="Copy", width=6,
                       command=lambda p=deck: self._copy_path(p)).pack(side="right", padx=2)

    def _open_scatter_canvas(self, pts, label, metric):
        """Fallback Canvas scatter when matplotlib is unavailable."""
        tk = self.tk
        W, H, pad = 580, 480, 60
        win = tk.Toplevel(self.root)
        win.title(f"Outlier scatter — {label}")
        cv = tk.Canvas(win, width=W, height=H, bg="#ffffff", highlightthickness=0)
        cv.pack(fill="both", expand=True)
        xs = [p[0] for p in pts] + [p[1] for p in pts]
        lo, hi = min(xs), max(xs)
        if hi <= lo:
            hi = lo + 1.0
        sx = lambda v: pad + (v - lo) / (hi - lo) * (W - 2 * pad)
        sy = lambda v: H - pad - (v - lo) / (hi - lo) * (H - 2 * pad)
        cv.create_line(pad, H - pad, W - pad, H - pad, fill="#888")
        cv.create_line(pad, H - pad, pad, pad, fill="#888")
        cv.create_line(sx(lo), sy(lo), sx(hi), sy(hi), fill="#9ec5fe", dash=(4, 3))
        from ..analysis.plots import metric_unit as _mu
        unit = _mu(metric)
        cv.create_text(W // 2, H - 20, text=f"MC {metric}" + (f" ({unit})" if unit else ""), fill="#444")
        cv.create_text(W // 2, 18, text=f"{label}   (n={len(pts)}, red = outlier)",
                       fill="#222", font=("DejaVu Sans", 10, "bold"))
        info = cv.create_text(W // 2, 38, text="click a point for its arc", fill="#777",
                              font=("DejaVu Sans", 8))
        for p in pts:
            mc, lib, is_out, arc = p[0], p[1], p[2], p[3]
            x, y, rr = sx(mc), sy(lib), 3
            oid = cv.create_oval(x - rr, y - rr, x + rr, y + rr,
                                 fill=("#dc2626" if is_out else "#94a3b8"), outline="")
            cv.tag_bind(oid, "<Button-1>", lambda e, a=arc: cv.itemconfigure(info, text=a))

    # ---- Analysis: Voltage Margin (Phase A) ----
    def _build_analysis(self):
        tk, ttk = self.tk, self.ttk
        f = self.tab_analysis
        bar = ttk.Frame(f); bar.pack(fill="x", pady=(0, 6))
        ttk.Label(bar, text="Voltage Margin — runs the VM tool on the loaded batch's sigma rpts "
                            "(needs corners spanning ≤15 mV gaps; open a batch in History first).",
                  style="Sec.TLabel").pack(side="left")
        self.btn_vm = ttk.Button(bar, text="▶ Run Voltage Margin", command=self._run_vm)
        self.btn_vm.pack(side="right")
        self.vm_status = ttk.Label(f, text="No run yet.", style="Muted.TLabel")
        self.vm_status.pack(anchor="w", pady=(0, 6))
        self.vm_body = ttk.Frame(f); self.vm_body.pack(fill="both", expand=True)

    def _csv_table(self, parent, title, header, rows, max_rows=200):
        ttk = self.ttk
        if not header:
            return
        ttk.Label(parent, text=f"{title}  ({len(rows)} rows)", style="Sec.TLabel").pack(anchor="w", pady=(8, 2))
        wrap = ttk.Frame(parent); wrap.pack(fill="both", expand=True)
        tv = ttk.Treeview(wrap, columns=header, show="headings", height=8, selectmode="browse")
        sb = ttk.Scrollbar(wrap, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        for c in header:
            tv.heading(c, text=c)
            tv.column(c, width=110, anchor="center")
        for r in rows[:max_rows]:
            tv.insert("", "end", values=r)
        tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def _run_vm(self):
        from tkinter import messagebox
        rec = getattr(self, "loaded_rec", None)
        if not rec or not rec.get("id"):
            return messagebox.showinfo("Voltage Margin", "Open a batch in History/Results first.")
        cfg = rec.get("config", {})
        bdir = runs.batch_dir(self.runs_root, rec["id"])
        self.vm_status.configure(text="Running Voltage Margin… (this can take a moment)")
        self.btn_vm.configure(state="disabled")
        self.root.update_idletasks()
        try:
            res = _vm.run_voltage_margin(bdir, cfg.get("corners", []), cfg.get("types", []))
        finally:
            self.btn_vm.configure(state="normal")
        self._render_vm(res)

    def _render_vm(self, res):
        for w in self.vm_body.winfo_children():
            w.destroy()
        if not res.get("ok"):
            self.vm_status.configure(text=f"Voltage Margin failed: {res.get('reason', 'unknown')}  "
                                          f"(see {res.get('out_dir', '')})")
            tail = res.get("stderr_tail") or res.get("stdout_tail") or ""
            if tail:
                t = self.tk.Text(self.vm_body, height=10, wrap="word", font=("DejaVu Sans Mono", 8))
                t.insert("end", tail); t.configure(state="disabled"); t.pack(fill="both", expand=True)
            return
        warns = res.get("sensitivity_warnings", {}).get("rows", [])
        n_gap = sum(1 for r in warns if "gap" in " ".join(r).lower())
        self.vm_status.configure(
            text=f"Voltage Margin OK → {res['out_dir']}   |   "
                 f"sensitivity skips: {len(warns)} (≥15 mV gap or <2 points: {n_gap})")
        summ = res.get("summary", {})
        per = res.get("per_object", {})
        opt = res.get("optimistic_per_object", {})
        self._csv_table(self.vm_body, "Margin summary (all errors)", summ.get("header", []), summ.get("rows", []))
        self._csv_table(self.vm_body, "Per-object margin — optimistic only (risk)",
                        opt.get("header", []), opt.get("rows", []))
        self._csv_table(self.vm_body, "Per-object margin (all)", per.get("header", []), per.get("rows", []))

    def _build_history(self):
        ttk = self.ttk
        f = self.tab_hist
        bar = ttk.Frame(f); bar.pack(fill="x", pady=(0, 6))
        ttk.Label(bar, text="All batches — click the ☐ box to check; double-click a row to open. "
                            "Checked rows drive PR Status / Outliers / Common / Compare.",
                  style="Muted.TLabel").pack(side="left")
        ttk.Button(bar, text="Refresh", command=self.refresh_history).pack(side="right")
        ttk.Button(bar, text="Compare checked", command=self._do_compare).pack(side="right", padx=6)
        ttk.Button(bar, text="Clear checks", command=self._clear_hist_checks).pack(side="right", padx=6)
        cols = ["✓", "Name", "When", "Vendor", "Ver", "Mean Late σ", "Health", "Status"]
        self.tv_hist = ttk.Treeview(f, columns=cols, show="headings", selectmode="browse")
        for c in cols:
            self.tv_hist.heading(c, text=c)
            self.tv_hist.column(c, width=120, anchor="center")
        self.tv_hist.column("✓", width=36, anchor="center", stretch=False)
        self.tv_hist.column("Name", width=240, anchor="w")
        self.tv_hist.pack(fill="both", expand=True)
        for h, bg in HEALTH_BG.items():
            self.tv_hist.tag_configure(h, background=bg)
        self.tv_hist.bind("<Double-1>", self._open_selected)
        self.tv_hist.bind("<Button-1>", self._on_hist_click)
        self._hist_ids: dict = {}
        self._hist_checked: set = set()

    def _on_hist_click(self, evt):
        # Toggle the check only when the ✓ column (#1) is clicked; let other clicks select.
        if self.tv_hist.identify_region(evt.x, evt.y) != "cell":
            return
        if self.tv_hist.identify_column(evt.x) != "#1":
            return
        iid = self.tv_hist.identify_row(evt.y)
        bid = self._hist_ids.get(iid)
        if not bid:
            return
        if bid in self._hist_checked:
            self._hist_checked.discard(bid)
        else:
            self._hist_checked.add(bid)
        self.tv_hist.set(iid, "✓", "☑" if bid in self._hist_checked else "☐")
        return "break"

    def _clear_hist_checks(self):
        self._hist_checked = set()
        for iid, bid in self._hist_ids.items():
            self.tv_hist.set(iid, "✓", "☐")

    def _build_compare(self):
        ttk = self.ttk
        f = self.tab_cmp
        ttk.Label(f, text="Late-sigma Base_PR across selected batches (pick in History).",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 6))
        self.cmp_holder = ttk.Frame(f); self.cmp_holder.pack(fill="both", expand=True)

    # ---- setup actions ----
    def _add_corner(self):
        c = self.e_corner.get().strip()
        if c and c not in self.corners:
            self.corners.append(c)
            self.lst_corner.insert("end", c)
        self.e_corner.delete(0, "end")

    def _remove_corner(self):
        sel = list(self.lst_corner.curselection())
        for i in reversed(sel):
            del self.corners[i]
            self.lst_corner.delete(i)

    def _add_suggestion(self):
        c = self.cb_sug.get().strip()
        if c and c not in self.corners:
            self.corners.append(c)
            self.lst_corner.insert("end", c)

    def _mode_key(self) -> str:
        label = self.cb_mode.get()
        for k, v in self._fmc_mode_labels.items():
            if v == label:
                return k
        return "decks"

    def _on_mode_change(self):
        # relabel the FMC dir field to hint what's expected
        mode = self._mode_key()
        hint = {"decks": "FMC dir (decks)", "parsed_dfds": "FMC dir (parsed DFDS)",
                "parsed_scld": "FMC dir (parsed SCLD)"}[mode]
        if hasattr(self, "fmc_dir_label"):
            self.fmc_dir_label.configure(text=hint)
        # Sensible default FMC unit: SCLD golden is ns; decks/DFDS are ps. (User can override.)
        if hasattr(self, "cb_fmc_unit"):
            self.cb_fmc_unit.set("ns" if mode == "parsed_scld" else "ps")

    def _on_vendor_change(self):
        # Sensible default Lib unit: CDNS libs are ps, SNPS libs are ns. (User can override.)
        if hasattr(self, "cb_lib_unit"):
            self.cb_lib_unit.set("ns" if self.vendor.get() == "snps" else "ps")

    def _gather(self) -> dict:
        types = [t for t, v in self.type_vars.items() if v.get()]
        mode = self._mode_key()
        cfg = {
            "name": self.e_name.get().strip(),
            "vendor": self.vendor.get(),
            "process": self.e_proc.get().strip(),
            "process_version": self.e_ver.get().strip(),
            "corners": list(self.corners),
            "types": types,
            "lib_dir": self.e_lib.get().strip(),
            "fmc_mode": mode,
            "vt_type": self.cb_vt.get().strip(),
            "rc_type": self.cb_rc.get().strip(),
            "library_type": self.cb_lib_type.get().strip() or "auto",
            "abs_tol_ps_by_corner": _parse_abs_tol(self.e_abs_tol.get(), list(self.corners)),
            "lib_unit": self.cb_lib_unit.get().strip(),
            "fmc_unit": self.cb_fmc_unit.get().strip(),
        }
        if mode == "decks":
            cfg["fmc_golden_dir"] = self.e_fmc.get().strip()
        else:
            cfg["fmc_input_dir"] = self.e_fmc.get().strip()
        return cfg

    def _submit(self):
        from tkinter import messagebox
        cfg = self._gather()
        if not cfg["corners"]:
            return messagebox.showerror("Missing corners", "Add at least one corner.")
        if not cfg["types"]:
            return messagebox.showerror("Missing types", "Select at least one timing type.")
        # Don't let a typo in abs_tol silently disable Waiver_2: if text was entered but
        # nothing parsed, make the user confirm running with W2 off.
        abs_tol_raw = self.e_abs_tol.get().strip()
        if abs_tol_raw and not cfg["abs_tol_ps_by_corner"]:
            if not messagebox.askyesno(
                    "abs_tol not understood",
                    f"The abs_tol entry '{abs_tol_raw}' could not be parsed into any "
                    "positive ps value, so Waiver_2 (hold abs_tol) will be OFF.\n\n"
                    "Expected: a single number (e.g. 19.5) or per-corner "
                    "'corner=val, corner2=val'.\n\nRun anyway with Waiver_2 off?"):
                return
        try:
            self.active_job = self.manager.submit(cfg)
        except ValueError as exc:
            return messagebox.showerror("Invalid configuration", str(exc))
        for lbl in self.stage_lbls.values():
            lbl.configure(text="pending", foreground=STATE_FG["pending"])
        self.pipe_banner.configure(text=f"{cfg['name'] or self.active_job} — queued…")
        self._audit_shown = 0
        self.audit_banner.configure(text="", bg=self.palette["BG"])
        self._logged_stage_state = {}
        self.log_text.configure(state="normal"); self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self._log(f"submitted: {cfg['name'] or self.active_job}  (mode={cfg['fmc_mode']}, "
                  f"corners={len(cfg['corners'])}, types={','.join(cfg['types'])})")
        self.nb.select(self.tab_pipe)
        self.root.after(300, self._poll)

    # ---- live polling (Tk main thread) ----
    def _poll(self):
        if not self.active_job:
            return
        st = self.manager.status(self.active_job)
        if not st:
            return
        label = {k: n for k, n in STAGES}
        for key, lbl in self.stage_lbls.items():
            s = st["stages"].get(key, "pending")
            lbl.configure(text=s, foreground=STATE_FG.get(s, "#222"))
            if self._logged_stage_state.get(key) != s and s != "pending":
                tag = "ok" if s == "passed" else "err" if s == "failed" else "warn" if s in ("partial", "running") else None
                self._log(f"  {label.get(key, key)}: {s}", tag)
                self._logged_stage_state[key] = s
        # drain any new audit findings into the log window + update audit banner
        from .. import audit as _audit
        findings = st.get("findings", [])
        shown = getattr(self, "_audit_shown", 0)
        if len(findings) > shown:
            new = findings[shown:]
            by_stage: dict = {}
            for fnd in new:
                by_stage.setdefault(fnd["stage"], []).append(fnd)
            for stage_name, items in by_stage.items():
                for text, tag in _audit.format_block(stage_name, items, cap=6):
                    self._log(text, tag)
            self._audit_shown = len(findings)
            s_sum = _audit.summarize(findings)
            bg = "#fad4d4" if s_sum["errors"] else ("#fdebc8" if s_sum["warns"] else "#d8f5e0")
            self.audit_banner.configure(
                text=f"Audit: {s_sum['errors']} errors · {s_sum['warns']} warnings", bg=bg)
        self.pipe_banner.configure(text=f"{st['name']} — {st['state']}"
                                        + (f": {st['error']}" if st.get("error") else ""))
        if st["state"] in ("passed", "partial", "failed"):
            self._surface_failures(self.active_job, st)
            self.refresh_history()
            self.load_results(self.active_job)
            return
        self.root.after(800, self._poll)

    def _surface_failures(self, batch_id, st):
        """On completion, collect stage failures from run_manifest.json into a
        single failures_summary.txt and point the user to it (C)."""
        import json
        tag = "ok" if st["state"] == "passed" else "err" if st["state"] == "failed" else "warn"
        self._log(f"run {st['state']}.", tag)
        if st.get("error"):
            self._log(f"  error: {st['error']}", "err")
        bdir = runs.batch_dir(self.runs_root, batch_id)
        manifest = bdir / "run_manifest.json"
        if not manifest.is_file():
            return
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        lines = []
        for stg in data.get("stage_execution", []):
            fails = stg.get("failures") or []
            if fails:
                name = stg.get("stage", "?")
                reasons = {}
                for fa in fails:
                    reasons[fa.get("reason", "?")] = reasons.get(fa.get("reason", "?"), 0) + 1
                summ = ", ".join(f"{n}x {r}" for r, n in reasons.items())
                self._log(f"  ⚠ {name}: {len(fails)} issue(s) — {summ}", "warn")
                lines.append(f"[{name}] {len(fails)} failures: {summ}")
                for fa in fails:
                    lines.append(f"  - {fa.get('reason','?')}: {fa.get('detail', fa.get('csv',''))}")
        if lines:
            fpath = bdir / "failures_summary.txt"
            try:
                fpath.write_text("\n".join(lines) + "\n", encoding="utf-8")
                self._log(f"  details written to: {fpath}", "warn")
            except OSError:
                pass

    # ---- history / results / compare ----
    def refresh_history(self):
        index = runs.read_index(self.runs_root)
        self.cb_sug["values"] = corner_suggestions(index)
        for iid in self.tv_hist.get_children():
            self.tv_hist.delete(iid)
        self._hist_ids = {}
        if not hasattr(self, "_hist_checked"):
            self._hist_checked = set()
        for row in index:
            mls = row.get("mean_late_sigma")
            checked = "☑" if row["id"] in self._hist_checked else "☐"
            vals = (checked, row.get("name", ""), (row.get("when_utc", "") or "").replace("T", " ")[:16],
                    row.get("vendor", ""), row.get("version", ""),
                    "—" if mls is None else f"{mls:.1f}%", row.get("worst_health", ""), row.get("status", ""))
            iid = self.tv_hist.insert("", "end", values=vals, tags=(row.get("worst_health", "OK"),))
            self._hist_ids[iid] = row["id"]

    def _open_selected(self, _evt=None):
        sel = self.tv_hist.selection()
        if sel:
            self.load_results(self._hist_ids.get(sel[0]))

    def load_results(self, batch_id):
        rec = runs.read_run_record(self.runs_root, batch_id) if batch_id else None
        self.loaded_rec = rec
        self._render_results()
        self.nb.select(self.tab_res)

    def _render_results(self):
        tk, ttk = self.tk, self.ttk
        for w in self.res_body.winfo_children():
            w.destroy()
        rec = getattr(self, "loaded_rec", None)
        if not rec:
            self.res_title.configure(text="No batch loaded.")
            self.verdict_lbl.configure(text="", bg=self.palette["BG"])
            return
        basis = getattr(self, "basis", "base")
        self.res_title.configure(text=f"{rec.get('name','')}  ·  {rec.get('status','')}")
        # verdict banner
        v = _summary.certification_verdict(rec, basis)
        if v["n_evaluated"] == 0:
            self.verdict_lbl.configure(text="CERTIFICATION: no data", bg="#eef2f7", fg="#475569")
        elif v["passed"]:
            self.verdict_lbl.configure(text=f"CERTIFICATION: PASS  —  all {v['n_evaluated']} type-metrics ≥ {v['threshold']:.0f}%  ({'+Waiver1' if basis=='w1' else 'Base PR'})",
                                       bg="#d8f5e0", fg="#15803d")
        else:
            self.verdict_lbl.configure(text=f"CERTIFICATION: FAIL  —  {len(v['failing'])} of {v['n_evaluated']} type-metrics below {v['threshold']:.0f}%  ({'+Waiver1' if basis=='w1' else 'Base PR'})",
                                       bg="#fad4d4", fg="#b91c1c")
        # per-type sections
        for section in _summary.per_type_sections(rec, basis):
            self._render_type_section(self.res_body, section)

    def _render_type_section(self, parent, section):
        tk, ttk = self.tk, self.ttk
        typ = section["type"]
        metrics = section["metrics"]
        box = ttk.LabelFrame(parent, text=typ.upper(), padding=8)
        box.pack(fill="x", expand=True, pady=(0, 10), padx=2)
        # header row
        hdr = ["Corner"] + [m.replace("_", " ") for m in metrics] + ["Coverage", "Health"]
        for c, text in enumerate(hdr):
            tk.Label(box, text=text, font=("DejaVu Sans", 9, "bold"), fg="#475569",
                     bg=self.palette["CARD"], padx=10, pady=5, anchor="w" if c == 0 else "center").grid(
                row=0, column=c, sticky="nsew", padx=1, pady=1)
        for r, row in enumerate(section["rows"], start=1):
            tk.Label(box, text=short_corner(row["corner"]), bg="#ffffff", fg="#0f172a",
                     padx=10, pady=5, anchor="w").grid(row=r, column=0, sticky="nsew", padx=1, pady=1)
            for c, m in enumerate(metrics, start=1):
                pr = row["values"].get(m)
                cls = pr_class(pr)
                tk.Label(box, text=fmt_pr(pr), bg=PR_BG[cls], fg=PR_FG[cls],
                         font=("DejaVu Sans", 10, "bold"), padx=10, pady=5).grid(
                    row=r, column=c, sticky="nsew", padx=1, pady=1)
            tk.Label(box, text=coverage_text(row), bg="#ffffff", fg="#475569", padx=10, pady=5).grid(
                row=r, column=len(metrics) + 1, sticky="nsew", padx=1, pady=1)
            hbg = HEALTH_BG.get(row["health"], "#eef2f7")
            tk.Label(box, text=row["health"], bg=hbg, fg="#334155", padx=10, pady=5).grid(
                row=r, column=len(metrics) + 2, sticky="nsew", padx=1, pady=1)

    def _export_csv(self):
        from tkinter import filedialog, messagebox
        rec = getattr(self, "loaded_rec", None)
        if not rec:
            return messagebox.showinfo("Export", "Open a batch first.")
        rows = _summary.flat_export_rows(rec, getattr(self, "basis", "base"))
        default = f"{rec.get('id','results')}_passrates.csv"
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=default,
                                            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        import csv as _csv
        with open(path, "w", newline="", encoding="utf-8") as fh:
            _csv.writer(fh).writerows(rows)
        # also copy to clipboard (tab-separated for easy paste)
        text = "\n".join("\t".join(str(c) for c in r) for r in rows)
        try:
            self.root.clipboard_clear(); self.root.clipboard_append(text)
        except Exception:
            pass
        messagebox.showinfo("Export", f"Wrote {len(rows)-1} pass-rate rows to:\n{path}\n(also copied to clipboard)")

    def _set_entry(self, entry, val):
        entry.delete(0, "end")
        entry.insert(0, val or "")

    def _rerun_loaded(self):
        """Load the currently-open batch's config back into Setup so it can be
        re-run (optionally after tweaks)."""
        from tkinter import messagebox
        rec = getattr(self, "loaded_rec", None)
        if not rec:
            return messagebox.showinfo("Rerun", "Open a batch (Results/History) first, then load its config.")
        cfg = rec.get("config", {})
        self.vendor.set(cfg.get("vendor", "cdns"))
        self._set_entry(self.e_name, rec.get("name", ""))
        self._set_entry(self.e_proc, cfg.get("process", ""))
        self._set_entry(self.e_ver, cfg.get("process_version", ""))
        self.corners = list(cfg.get("corners", []))
        self.lst_corner.delete(0, "end")
        for c in self.corners:
            self.lst_corner.insert("end", c)
        for t, var in self.type_vars.items():
            var.set(1 if t in (cfg.get("types") or []) else 0)
        self.cb_vt.set(cfg.get("vt_type") or "")
        self.cb_rc.set(cfg.get("rc_type") or "")
        self.cb_lib_type.set(cfg.get("library_type") or "auto")
        self.cb_lib_unit.set(cfg.get("lib_unit") or ("ns" if cfg.get("vendor") == "snps" else "ps"))
        self.cb_fmc_unit.set(cfg.get("fmc_unit") or ("ns" if cfg.get("fmc_mode") == "parsed_scld" else "ps"))
        at = cfg.get("abs_tol_ps_by_corner") or {}
        self._set_entry(self.e_abs_tol, ", ".join(f"{k}={v}" for k, v in at.items()))
        mode = cfg.get("fmc_mode") or "decks"
        self.cb_mode.set(self._fmc_mode_labels.get(mode, self._fmc_mode_labels["decks"]))
        self._on_mode_change()
        fmc_dir = cfg.get("fmc_golden_dir") if mode == "decks" else cfg.get("fmc_input_dir")
        self._set_entry(self.e_fmc, fmc_dir or "")
        self._set_entry(self.e_lib, cfg.get("lib_dir") or "")
        self.nb.select(self.tab_setup)

    def _do_compare(self):
        ttk = self.ttk
        checked = getattr(self, "_hist_checked", set())
        ids = [row["id"] for row in runs.read_index(self.runs_root) if row["id"] in checked]
        for w in self.cmp_holder.winfo_children():
            w.destroy()
        if len(ids) < 2:
            ttk.Label(self.cmp_holder, text="Check at least two batches in History (click the ☐ box).").pack(pady=20)
            self.nb.select(self.tab_cmp); return
        recs = [runs.read_run_record(self.runs_root, i) for i in ids]
        recs = [r for r in recs if r]
        basis = getattr(self, "pr_basis", "w1")

        # Compare ALL metric rows (sigma Early/Late + moments MS/Std/Skew + hold late),
        # not just Late_Sigma Base — at the current PR basis. Reuses the pivot model.
        per_rec = []
        for r in recs:
            per_rec.append((
                {(s["corner"], s["type"]): s for s in r.get("sigma", [])},
                {(m["corner"], m["type"]): m for m in r.get("moments", [])},
            ))
        # Row keys: (corner, prow) present in any batch, in PR_ROWS order.
        corners = []
        for sig, mom in per_rec:
            for (corner, _t) in list(sig) + list(mom):
                if corner not in corners:
                    corners.append(corner)
        corners.sort()

        ttk.Label(self.cmp_holder, text=f"Cross-batch PR — basis: {basis.upper()} "
                                        f"(set on PR Status). All metrics; — = NO_DATA.",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 4))
        cols = ["Corner · Metric"] + [f"{r.get('batch_id') or r.get('name','?')}" for r in recs]
        wrap = ttk.Frame(self.cmp_holder); wrap.pack(fill="both", expand=True)
        tv = ttk.Treeview(wrap, columns=cols, show="headings")
        sb = ttk.Scrollbar(wrap, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        for c in cols:
            tv.heading(c, text=c); tv.column(c, width=130, anchor="center")
        tv.column("Corner · Metric", width=260, anchor="w")
        tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        for corner in corners:
            for prow in _consolidate.PR_ROWS:
                vals = [f"{short_corner(corner)} · {prow['label']}"]
                any_val = False
                for sig, mom in per_rec:
                    s = sig.get((corner, prow["type"]))
                    m = mom.get((corner, prow["type"]))
                    pr = _consolidate._value(prow["metric"], basis, s, m)
                    if pr is not None:
                        any_val = True
                    vals.append("—" if pr is None else fmt_pr(pr))
                if any_val:
                    tv.insert("", "end", values=vals)
        self.nb.select(self.tab_cmp)

    def _on_close(self):
        try:
            self.manager.shutdown()
        finally:
            self.root.destroy()

    def run(self):
        self.root.mainloop()
