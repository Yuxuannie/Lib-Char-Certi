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
from ..web.executor import JobManager

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

        self.e_fmc = self._dir_field(f, "FMC golden dir (decks)")
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
        ttk = self.ttk
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

    def _build_results(self):
        ttk = self.ttk
        f = self.tab_res
        self.res_title = ttk.Label(f, text="No batch loaded.", style="Sec.TLabel")
        self.res_title.pack(anchor="w", pady=(0, 8))
        ttk.Label(f, text="Sigma", style="Sec.TLabel").pack(anchor="w")
        self.tv_sigma = self._make_table(f, ["Corner", "Type", "Early Base", "Early +W1",
                                             "Late Base", "Late +W1", "Coverage", "Health"])
        ttk.Label(f, text="Moments (from FMC)", style="Sec.TLabel").pack(anchor="w", pady=(10, 0))
        self.tv_mom = self._make_table(f, ["Corner", "Type", "Meanshift", "Std", "Skew", "Coverage", "Health"])

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

    def _gather(self) -> dict:
        types = [t for t, v in self.type_vars.items() if v.get()]
        return {
            "name": self.e_name.get().strip(),
            "vendor": self.vendor.get(),
            "process": self.e_proc.get().strip(),
            "process_version": self.e_ver.get().strip(),
            "corners": list(self.corners),
            "types": types,
            "fmc_golden_dir": self.e_fmc.get().strip(),
            "lib_dir": self.e_lib.get().strip(),
        }

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
        self.nb.select(self.tab_pipe)
        self.root.after(300, self._poll)

    # ---- live polling (Tk main thread) ----
    def _poll(self):
        if not self.active_job:
            return
        st = self.manager.status(self.active_job)
        if not st:
            return
        for key, lbl in self.stage_lbls.items():
            s = st["stages"].get(key, "pending")
            lbl.configure(text=s, foreground=STATE_FG.get(s, "#222"))
        self.pipe_banner.configure(text=f"{st['name']} — {st['state']}"
                                        + (f": {st['error']}" if st.get("error") else ""))
        if st["state"] in ("passed", "partial", "failed"):
            self.refresh_history()
            self.load_results(self.active_job)
            return
        self.root.after(800, self._poll)

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
        for tv in (self.tv_sigma, self.tv_mom):
            for iid in tv.get_children():
                tv.delete(iid)
        if not rec:
            self.res_title.configure(text="No batch loaded.")
            return
        self.res_title.configure(text=f"{rec.get('name','')}  ·  {rec.get('status','')}")
        for r in rec.get("sigma", []):
            self.tv_sigma.insert("", "end", tags=(r.get("health", "OK"),), values=(
                short_corner(r["corner"]), r["type"], fmt_pr(r.get("eBase")), fmt_pr(r.get("eW1")),
                fmt_pr(r.get("lBase")), fmt_pr(r.get("lW1")), coverage_text(r), r.get("health", "")))
        for r in rec.get("moments", []):
            self.tv_mom.insert("", "end", tags=(r.get("health", "OK"),), values=(
                short_corner(r["corner"]), r["type"], fmt_pr(r.get("ms")), fmt_pr(r.get("std")),
                fmt_pr(r.get("skew")), coverage_text(r), r.get("health", "")))
        self.nb.select(self.tab_res)

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
