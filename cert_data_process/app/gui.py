"""Tkinter GUI for the Lib-Char-Certi console.

Single process: draws the window AND runs the pipeline (via the UI-agnostic
JobManager). No HTTP/port/localhost/host-matching — displays over X11/Exceed like
a terminal. Pure helpers are module-level (display-free, testable); the Tk window
is created only when CertiApp() is instantiated.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ..web import runs
from ..web import summary as _summary
from ..web.executor import JobManager

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
        self.tab_hist = ttk.Frame(self.nb, padding=12)
        self.tab_cmp = ttk.Frame(self.nb, padding=12)
        for f, t in [(self.tab_setup, "Setup"), (self.tab_pipe, "Pipeline"),
                     (self.tab_res, "Results"), (self.tab_hist, "History"), (self.tab_cmp, "Compare")]:
            self.nb.add(f, text=t)
        self._build_setup()
        self._build_pipeline()
        self._build_results()
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
            ttk.Radiobutton(row, text=v.upper(), value=v, variable=self.vendor).pack(side="left", padx=6)

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

        self.e_fmc = self._dir_field(f, "FMC dir")
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

    def _dir_field(self, parent, label):
        ttk = self.ttk
        from tkinter import filedialog
        row = ttk.Frame(parent); row.pack(fill="x", pady=4)
        ttk.Label(row, text=label, width=16).pack(side="left")
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
        self.pipe_banner.pack(anchor="w", pady=(0, 14))
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
        # high-level live log (C)
        ttk.Label(f, text="Log", style="Sec.TLabel").pack(anchor="w", pady=(16, 4))
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
        for key, txt in (("base", "Base"), ("w1", "+Waiver1")):
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

    def _build_history(self):
        ttk = self.ttk
        f = self.tab_hist
        bar = ttk.Frame(f); bar.pack(fill="x", pady=(0, 6))
        ttk.Label(bar, text="All batches — double-click to open; multi-select then Compare",
                  style="Muted.TLabel").pack(side="left")
        ttk.Button(bar, text="Refresh", command=self.refresh_history).pack(side="right")
        ttk.Button(bar, text="Compare selected", command=self._do_compare).pack(side="right", padx=6)
        cols = ["Name", "When", "Vendor", "Ver", "Mean Late σ", "Health", "Status"]
        self.tv_hist = ttk.Treeview(f, columns=cols, show="headings", selectmode="extended")
        for c in cols:
            self.tv_hist.heading(c, text=c)
            self.tv_hist.column(c, width=120, anchor="center")
        self.tv_hist.column("Name", width=240, anchor="w")
        self.tv_hist.pack(fill="both", expand=True)
        for h, bg in HEALTH_BG.items():
            self.tv_hist.tag_configure(h, background=bg)
        self.tv_hist.bind("<Double-1>", self._open_selected)
        self._hist_ids: dict = {}

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
        try:
            self.active_job = self.manager.submit(cfg)
        except ValueError as exc:
            return messagebox.showerror("Invalid configuration", str(exc))
        for lbl in self.stage_lbls.values():
            lbl.configure(text="pending", foreground=STATE_FG["pending"])
        self.pipe_banner.configure(text=f"{cfg['name'] or self.active_job} — queued…")
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
        for row in index:
            mls = row.get("mean_late_sigma")
            vals = (row.get("name", ""), (row.get("when_utc", "") or "").replace("T", " ")[:16],
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
        mode = cfg.get("fmc_mode") or "decks"
        self.cb_mode.set(self._fmc_mode_labels.get(mode, self._fmc_mode_labels["decks"]))
        self._on_mode_change()
        fmc_dir = cfg.get("fmc_golden_dir") if mode == "decks" else cfg.get("fmc_input_dir")
        self._set_entry(self.e_fmc, fmc_dir or "")
        self._set_entry(self.e_lib, cfg.get("lib_dir") or "")
        self.nb.select(self.tab_setup)

    def _do_compare(self):
        ttk = self.ttk
        ids = [self._hist_ids[i] for i in self.tv_hist.selection() if i in self._hist_ids]
        for w in self.cmp_holder.winfo_children():
            w.destroy()
        if len(ids) < 2:
            ttk.Label(self.cmp_holder, text="Select at least two batches in History.").pack(pady=20)
            self.nb.select(self.tab_cmp); return
        recs = [runs.read_run_record(self.runs_root, i) for i in ids]
        recs = [r for r in recs if r]
        keys = []
        for r in recs:
            for s in r.get("sigma", []):
                k = (s["corner"], s["type"])
                if k not in keys:
                    keys.append(k)
        cols = ["Corner · Type"] + [f"{r.get('version','')} {r.get('vendor','')}" for r in recs]
        tv = ttk.Treeview(self.cmp_holder, columns=cols, show="headings")
        for c in cols:
            tv.heading(c, text=c); tv.column(c, width=130, anchor="center")
        tv.column("Corner · Type", width=220, anchor="w")
        tv.pack(fill="both", expand=True)
        for (corner, typ) in keys:
            vals = [f"{short_corner(corner)} · {typ}"]
            for r in recs:
                m = next((s for s in r.get("sigma", []) if s["corner"] == corner and s["type"] == typ), None)
                vals.append("n/a" if not m else ("—" if m.get("health") == "NO_DATA" else fmt_pr(m.get("lBase"))))
            tv.insert("", "end", values=vals)
        self.nb.select(self.tab_cmp)

    def _on_close(self):
        try:
            self.manager.shutdown()
        finally:
            self.root.destroy()

    def run(self):
        self.root.mainloop()
