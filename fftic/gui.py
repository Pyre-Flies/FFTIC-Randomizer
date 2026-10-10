"""Standard-library desktop front end. Writes only generated mod folders."""
import os
from pathlib import Path
import secrets
import subprocess
import threading
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk, filedialog, messagebox

from . import VERSION
from .package import create_seed
from .randomize import FLAGS, DEFAULT_FLAGS
from .runtime import (default_game_dir, default_output_dir, resource_root, is_linux,
                      external_application_environment)


FLAG_HELP = {
    'r': "Changes which job levels unlock other jobs and the JP needed to raise a job's level. Includes ordinary job progression.",
    'i': "Changes a job's built-in abilities, starting and immune statuses, elemental properties, and permitted equipment. These traits apply to everyone using that job.",
    's': "Changes the action, reaction, support, and movement abilities available to humanoid jobs, including unique character and enemy jobs. The chosen ability mode controls how their skillsets are built.",
    'a': "Changes ability properties such as charge time, MP cost, power, range, and area of effect. A skill keeps these properties wherever it appears.",
    'y': "Changes the statuses inflicted or granted by abilities and weapons, such as Poison, Haste, or Protect.",
    'j': "Changes humanoid job stats and growth rates, the JP required to learn skills, and eligible skill-learning chances.",
    'm': "Changes monster job stats, built-in traits, and skillsets, including the hidden fourth skill. The chosen ability mode also applies to monster skillsets.",
    'u': "Changes enemy and ally battle units: jobs, secondary skillsets, equipped abilities, equipment, and related unit traits. Story characters keep their required identities.",
    'z': "Adds special surprises involving character names, weather, special units, and later story encounters. With formations enabled, some encounters can also move to different maps.",
    'f': "Changes battle formations and starting positions using each map's terrain. Also rearranges random-encounter groups and player deployment areas.",
    't': "Changes battle trophies, poaching rewards, and treasures found with Treasure Hunter, including their rare alternatives.",
    'p': "Changes item prices, shop unlock timing, and rarity. This determines when and where equipment becomes available.",
    'w': "Changes weapon, armor, accessory, and consumable properties, including power, evasion, HP/MP bonuses, and equipment stat bonuses.",
    'c': "Shuffles eligible battle music while preserving tracks needed by particular scenes.",
    'o': "Automatically advances event dialogue. Useful when replaying opening scenes or testing a new seed.",
    'b': "Makes six selected action abilities cost zero JP and MP and cast instantly wherever they are assigned. Useful for testing; this does not unlock every job or skill.",
}


def _open_folder(path):
    """Launch the platform file manager without tying its lifetime to Tk."""
    if is_linux():
        subprocess.Popen(['xdg-open', str(Path(path).resolve())],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True,
                         close_fds=True, env=external_application_environment())
    else:
        os.startfile(path)


def _work_area(widget):
    """Return the current monitor's usable area, including negative origins."""
    bounds = (0, 0, widget.winfo_screenwidth(), widget.winfo_screenheight())
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class MonitorInfo(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

        user32 = ctypes.windll.user32
        user32.MonitorFromWindow.argtypes = (wintypes.HWND, wintypes.DWORD)
        user32.MonitorFromWindow.restype = wintypes.HANDLE
        user32.GetMonitorInfoW.argtypes = (wintypes.HANDLE, ctypes.POINTER(MonitorInfo))
        user32.GetMonitorInfoW.restype = wintypes.BOOL
        info = MonitorInfo(cbSize=ctypes.sizeof(MonitorInfo))
        monitor = user32.MonitorFromWindow(widget.winfo_id(), 2)
        if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            area = info.rcWork
            bounds = area.left, area.top, area.right, area.bottom
    return bounds


class _Tooltips:
    """Delayed hover/focus help with one popup and app-local bindings."""

    def __init__(self, app, delay=500):
        self.app, self.delay = app, delay
        self.controls = {}
        self.target = self.popup = self.pending = None
        app.bind("<Escape>", self.dismiss, add="+")
        app.bind("<ButtonPress>", self.dismiss, add="+")
        app.bind("<Configure>", self._app_changed, add="+")
        app.bind("<Destroy>", self._app_changed, add="+")

    def add(self, widget, text):
        self.controls[widget] = text
        widget.bind("<Enter>", lambda event: self.schedule(widget), add="+")
        widget.bind("<FocusIn>", lambda event: self.schedule(widget), add="+")
        for sequence in ("<Leave>", "<FocusOut>", "<ButtonPress>", "<Unmap>"):
            widget.bind(sequence, lambda event: self.dismiss(), add="+")
        widget.bind("<Destroy>", lambda event: self._removed(widget), add="+")
        return widget

    def schedule(self, widget):
        self.dismiss()
        if widget.winfo_exists() and widget.winfo_ismapped():
            self.target = widget
            self.pending = self.app.after(self.delay, self._show)

    def _show(self):
        self.pending = None
        widget = self.target
        if widget is None or not widget.winfo_exists() or not widget.winfo_ismapped():
            self.dismiss()
            return
        left, top, right, bottom = _work_area(widget)
        width = max(1, min(440, right - left - 32))
        popup = self.popup = tk.Toplevel(self.app)
        popup.withdraw()
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        text = self.controls[widget]
        label = tk.Label(popup, text=text() if callable(text) else text,
                         justify="left", wraplength=width, background="#fffbe5",
                         foreground="#202020", relief="solid", borderwidth=1,
                         padx=9, pady=7, font="TkDefaultFont", takefocus=False)
        label.pack()
        popup.update_idletasks()
        requested_width, requested_height = popup.winfo_reqwidth(), popup.winfo_reqheight()
        x, y = widget.winfo_rootx(), widget.winfo_rooty() + widget.winfo_height() + 7
        if y + requested_height > bottom - 8:
            y = widget.winfo_rooty() - requested_height - 7
        x = max(left + 8, min(x, right - requested_width - 8))
        y = max(top + 8, min(y, bottom - requested_height - 8))
        popup.geometry(f"+{x}+{y}")
        popup.deiconify()

    def dismiss(self, event=None):
        if self.pending is not None:
            self.app.after_cancel(self.pending)
            self.pending = None
        if self.popup is not None:
            self.popup.destroy()
            self.popup = None
        self.target = None

    def _removed(self, widget):
        if self.target == widget:
            self.dismiss()
        self.controls.pop(widget, None)

    def _app_changed(self, event):
        if event.widget == self.app:
            self.dismiss()


class _ScrollableSettings(ttk.Frame):
    """Resizable settings viewport; actions live outside this scroll area."""

    def __init__(self, parent, on_scroll=None):
        super().__init__(parent)
        self.on_scroll = on_scroll
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0,
                                yscrollincrement=16, takefocus=False)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self._scrollbar_view)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = ttk.Frame(self.canvas, padding=18)
        self._window = self.canvas.create_window(0, 0, window=self.body, anchor="nw")
        self.canvas.bind("<Configure>", self._resize)
        self.body.bind("<Configure>", self._update_region)
        self._wheel_remainder = 0
        self._tag = f"fftic-settings-{id(self)}"
        self.bind_class(self._tag, "<MouseWheel>", self._wheel)
        self.bind_class(self._tag, "<Button-4>", lambda event: self._scroll(-3))
        self.bind_class(self._tag, "<Button-5>", lambda event: self._scroll(3))
        self.bind_class(self._tag, "<FocusIn>", self._show_focus)

    def _resize(self, event):
        self.canvas.itemconfigure(self._window, width=event.width)

    def _update_region(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        if self.body.winfo_height() <= self.canvas.winfo_height():
            self.canvas.yview_moveto(0)

    def bind_controls(self):
        """Use an app-local tag, never a global mouse-wheel binding."""
        def attach(widget):
            tags = widget.bindtags()
            widget.bindtags((tags[0], self._tag, *tags[1:]))
            for child in widget.winfo_children():
                attach(child)
        attach(self.canvas)

    def _scroll(self, units):
        if self.on_scroll:
            self.on_scroll()
        if self.body.winfo_height() > self.canvas.winfo_height():
            self.canvas.yview_scroll(units, "units")
        return "break"

    def _scrollbar_view(self, *args):
        if self.on_scroll:
            self.on_scroll()
        self.canvas.yview(*args)

    def _wheel(self, event):
        # Let open combobox menus handle their own scrolling. Closed controls
        # scroll the settings without changing a seed option accidentally.
        self._wheel_remainder += event.delta
        units = int(self._wheel_remainder / 120)
        self._wheel_remainder -= units * 120
        return self._scroll(-units * 3)

    def _show_focus(self, event):
        widget = event.widget
        if widget == self.canvas or not widget.winfo_ismapped():
            return
        height = self.body.winfo_height()
        visible = self.canvas.winfo_height()
        top = widget.winfo_rooty() - self.body.winfo_rooty()
        bottom = top + widget.winfo_height()
        offset = self.canvas.canvasy(0)
        if top < offset + 8:
            self.canvas.yview_moveto(max(0, top - 8) / height)
        elif bottom > offset + visible - 8:
            self.canvas.yview_moveto(max(0, bottom + 8 - visible) / height)


def _fit_window(app):
    left, top, right, bottom = _work_area(app)
    width, height = right - left, bottom - top
    available_width, available_height = max(1, width - 48), max(1, height - 64)
    window_width, window_height = min(1120, available_width), min(1000, available_height)
    app.minsize(min(520, available_width), min(340, available_height))
    app.geometry(f"{window_width}x{window_height}+{left + (width-window_width)//2}+{top + 16}")


def _wrapped_text(text, font, width):
    lines, line = [], ""
    for word in text.split():
        candidate = f"{line} {word}" if line else word
        if line and font.measure(candidate) > width:
            lines.append(line)
            line = word
        else:
            line = candidate
    return "\n".join([*lines, line])


def create_app(project_root):
    app = tk.Tk()
    app.title("FFTIC Randomizer")
    _fit_window(app)
    tips = _Tooltips(app)
    app._fftic_tooltips = tips
    footer = ttk.Frame(app, padding=(18, 12))
    footer.pack(side="bottom", fill="x")
    settings = _ScrollableSettings(app, on_scroll=tips.dismiss)
    settings.pack(fill="both", expand=True)
    frame = settings.body
    ttk.Label(frame, text="FFTIC Randomizer", font=("Segoe UI", 21, "bold")).pack(anchor="w")
    subtitle = ttk.Label(frame, text="Enhanced mode | Seeded randomization | Two ability modes", font=("Segoe UI", 10))
    subtitle.pack(anchor="w", pady=(3, 14))
    variables = {}
    path_help = {
        "Game folder": "Select the installed Final Fantasy Tactics: The Ivalice Chronicles folder. Generation reads the game files and creates a separate mod.",
        "Output folder": "Choose where generated seed folders, installable mod archives, and spoiler reports are saved.",
        "Seed": "A seed names the random draw sequence. Use the same seed and settings in this version to reproduce a result, or choose New seed for another draw.",
    }
    for label, initial in (("Game folder", str(default_game_dir(project_root))),
                           ("Output folder", str(default_output_dir(project_root))),
                           ("Seed", secrets.token_hex(4))):
        tips.add(ttk.Label(frame, text=label), path_help[label]).pack(anchor="w")
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=(3, 10))
        variable = tk.StringVar(value=initial)
        variables[label] = variable
        tips.add(ttk.Entry(row, textvariable=variable), path_help[label]).pack(side="left", fill="x", expand=True)
        if label != "Seed":
            def browse(var=variable):
                selected = filedialog.askdirectory(initialdir=var.get())
                if selected:
                    var.set(selected)
            tips.add(ttk.Button(row, text="Browse", command=browse),
                     f"Choose the {label.lower()} using the folder picker.").pack(side="right", padx=(8, 0))
        else:
            tips.add(ttk.Button(row, text="New seed", command=lambda: variable_seed.set(secrets.token_hex(4))),
                     "Choose a fresh random seed. Your other settings stay the same.").pack(side="right", padx=(8, 0))
    variable_seed = variables["Seed"]
    group = ttk.LabelFrame(frame, text="Randomize", padding=10)
    group.pack(fill="x", pady=(0, 10))
    enabled = {}
    flag_controls = []
    for i, (flag, name) in enumerate(FLAGS.items()):
        enabled[flag] = tk.BooleanVar(value=flag in DEFAULT_FLAGS)
        text = tk.StringVar(value=name)
        control = ttk.Checkbutton(group, textvariable=text, variable=enabled[flag])
        tips.add(control, FLAG_HELP[flag])
        flag_controls.append((control, text, name))
        control.grid(row=i, column=0, sticky="w", pady=3)
    flag_font = tkfont.Font(font=ttk.Style(app).lookup("TCheckbutton", "font") or "TkDefaultFont")
    last_flag_width = [None]

    def layout_flags(event):
        if event.width == last_flag_width[0]:
            return
        last_flag_width[0] = event.width
        width = max(1, event.width - 24)
        preferred = max(flag_font.measure(name) for name in FLAGS.values()) + 40
        columns = 2 if width >= preferred * 2 + 16 else 1
        cell_width = max(1, (width - 16 * (columns - 1)) // columns)
        group.columnconfigure(0, weight=1, uniform="flags")
        group.columnconfigure(1, weight=1 if columns == 2 else 0, uniform="flags" if columns == 2 else "")
        for i, (control, text, name) in enumerate(flag_controls):
            control.grid(row=i // columns, column=i % columns,
                         padx=(0, 16 if columns == 2 and i % columns == 0 else 0))
            text.set(_wrapped_text(name, flag_font, max(1, cell_width - 32)))
    group.bind("<Configure>", layout_flags)
    mode = tk.StringVar(value="Shuffle")
    row = ttk.Frame(frame)
    row.pack(fill="x", pady=(0, 12))
    mode_tip = ("Shuffle exchanges abilities among existing skillsets while keeping protected command structures and the original reuse rules. "
                "Full redistribution deals new skillsets from separate humanoid and monster pools; each pool refills only after exhaustion. Applies when job or monster skills are enabled.")
    tips.add(ttk.Label(row, text="Ability mode"), mode_tip).pack(side="left")
    mode_selector = ttk.Combobox(row, state="readonly", width=23, textvariable=mode,
                                values=("Shuffle","Full redistribution"))
    tips.add(mode_selector, mode_tip)
    mode_selector.pack(side="left", padx=12)
    fiesta,easymodo = tk.BooleanVar(value=False),tk.BooleanVar(value=False)
    row = ttk.Frame(frame)
    row.pack(fill="x", pady=(0, 12))
    tips.add(ttk.Checkbutton(row,text='Job Fiesta',variable=fiesta),
             "Starts Ramza and the initial party as Mimes, clears their secondary and passive loadouts, and gives early enemies Stone Guns. Intended as a new-game challenge.").pack(anchor="w")
    tips.add(ttk.Checkbutton(row,text='Easy Mode',variable=easymodo),
             "Sets every enemy to level 1. Enemies with generic sprites also receive Tietra's job; special character sprites keep their jobs. Applied after the other randomization settings.").pack(anchor="w", pady=(4, 0))
    spread = tk.StringVar(value="25%")
    row = ttk.Frame(frame)
    row.pack(fill="x", pady=(0, 12))
    spread_tip = "Controls how far randomized numerical values can move from their starting values. Lower percentages stay closer to the originals; higher percentages allow larger changes across enabled numeric options."
    tips.add(ttk.Label(row, text="Stat randomness"), spread_tip).pack(side="left")
    tips.add(ttk.Combobox(row, state="readonly", width=8, textvariable=spread, values=("10%", "25%", "50%", "75%", "100%")), spread_tip).pack(side="left", padx=12)
    degree = tk.StringVar(value="100%")
    row = ttk.Frame(frame)
    row.pack(fill="x", pady=(0, 12))
    degree_tip = "Controls the extent of skillset changes. Shuffle at 100% uses its full exchange probabilities; lower values reduce changes. Full redistribution replaces this percentage of eligible enabled skillsets."
    tips.add(ttk.Label(row, text="Ability degree"), degree_tip).pack(side="left")
    tips.add(ttk.Combobox(row, state="readonly", width=8, textvariable=degree, values=("10%", "25%", "50%", "75%", "100%")), degree_tip).pack(side="left", padx=12)
    row = ttk.Frame(frame)
    row.pack(fill='x',pady=(0,12))
    chaos = tk.StringVar(value='1.0')
    chaos_tip = "Scales progression and difficulty boosts in enabled options, including stronger later enemies and equipment. 1.0 is the standard setting; higher values can make encounters much harder. 0 removes these boosts while keeping randomization."
    tips.add(ttk.Label(row,text='Chaos multiplier'), chaos_tip).pack(side='left')
    tips.add(ttk.Combobox(row,state='readonly',width=6,textvariable=chaos,values=('0','0.5','1.0','1.5','2.0','3.0','5.0','10.0')), chaos_tip).pack(side='left',padx=12)
    full_controls = ttk.LabelFrame(frame, text="Full redistribution counts", padding=10)
    min_actions = tk.StringVar(value="6")
    max_actions = tk.StringVar(value="12")
    passives = tk.StringVar(value="1")
    full_selectors = []
    count_help = {
        "Minimum actions": "In Full redistribution, the lower bound on action abilities dealt to a humanoid job. Some command menus require a compatible list rather than an arbitrary selection. Must not exceed Maximum actions.",
        "Maximum actions": "In Full redistribution, the upper bound on action abilities dealt to a humanoid job. Monster lists keep their required four skills, and a special surprise can add an extra action.",
        "Each passive type": "In Full redistribution, the number of reaction, support, and movement abilities dealt to each humanoid job: 1 gives one of each; 2 gives two of each. Monster jobs do not receive these passive slots.",
    }
    for i,(label,variable,choices) in enumerate((("Minimum actions",min_actions,tuple(range(1,17))),
                                   ("Maximum actions",max_actions,tuple(range(1,17))),
                                   ("Each passive type",passives,(1,2)))):
        tips.add(ttk.Label(full_controls,text=label), count_help[label]).grid(row=i,column=0,sticky="w",padx=(0,8),pady=3)
        selector = ttk.Combobox(full_controls,state="disabled",width=5,
                                textvariable=variable,values=choices)
        selector.grid(row=i,column=1,sticky="w",pady=3)
        tips.add(selector, count_help[label])
        full_selectors.append(selector)
    mode_help = tk.StringVar()
    description = ttk.Label(frame, textvariable=mode_help, wraplength=990)
    description.pack(anchor="w", pady=(0, 12))

    def update_mode(event=None):
        full = mode.get() == "Full redistribution"
        for selector in full_selectors:
            selector.configure(state="readonly" if full else "disabled")
        if full:
            full_controls.pack(fill="x",pady=(0,12),before=description)
            mode_help.set("Full redistribution builds new lists from separate human and monster pools.\n"
                          "Ordinary and unique jobs share the job-skillset option. 100% replaces every enabled skillset; lower degrees replace a percentage of jobs. Pools refill after exhaustion.")
        else:
            full_controls.pack_forget()
            mode_help.set("Shuffle exchanges actions between existing lists and consumes the ordinary passive pool.\n"
                          "Ordinary and unique jobs share the job-skillset option. 100% uses the original exchange probabilities. Shared skills and rare monster crossover follow the established reuse rules.")
    mode_selector.bind("<<ComboboxSelected>>",update_mode)
    update_mode()
    status = tk.StringVar(value="Generate a mod, then enable it through Reloaded-II and the FFTIC mod loader.")
    status_label = ttk.Label(footer, textvariable=status, wraplength=675)
    status_label.pack(anchor="w", pady=(0, 10))
    buttons = ttk.Frame(footer)
    buttons.pack(fill="x")
    latest = [None]

    def open_output():
        path = latest[0] or Path(variables["Output folder"].get())
        if path.exists():
            try:
                _open_folder(path)
            except OSError as error:
                messagebox.showerror("Could not open output folder", f"{path}\n\n{error}")

    def complete(result, error=None):
        generate_button.configure(state="normal")
        if error:
            status.set("Generation stopped. No original game files were changed.")
            messagebox.showerror("Could not generate seed", str(error))
        else:
            destination, manifest = result
            latest[0] = destination
            status.set(f"Generated {manifest['property_changes']} changes. Open output for the mod and spoiler report. Gameplay remains untested.")

    def generate():
        flags = "".join(f for f in FLAGS if enabled[f].get())
        arguments = dict(
            game_dir=variables["Game folder"].get(), output_root=variables["Output folder"].get(),
            seed=variables["Seed"].get(), flags=flags,
            spread=int(spread.get().rstrip("%")) / 100, project_root=project_root,
            skill_degree=int(degree.get().rstrip("%")) / 100, chaos=float(chaos.get()),
            ability_mode="full" if mode.get()=="Full redistribution" else "rcc",
            min_actions=int(min_actions.get()), max_actions=int(max_actions.get()),
            passives_per_type=int(passives.get()),fiesta=fiesta.get(),easymodo=easymodo.get())
        generate_button.configure(state="disabled")
        status.set("Verifying the game build and generating the seed...")
        def worker():
            try:
                result = create_seed(**arguments)
                app.after(0, complete, result)
            except Exception as error:
                app.after(0, complete, None, error)
        threading.Thread(target=worker, daemon=True).start()

    credits_dialog = [None]

    def show_credits():
        if credits_dialog[0] is not None and credits_dialog[0].winfo_exists():
            credits_dialog[0].lift()
            return
        tips.dismiss()
        dialog = credits_dialog[0] = tk.Toplevel(app)
        dialog.title("About FFTIC Randomizer")
        dialog.transient(app)
        left, top, right, bottom = _work_area(app)
        width, height = min(780, right - left - 32), min(650, bottom - top - 48)
        x = max(left + 8, min(app.winfo_rootx() + 30, right - width - 8))
        y = max(top + 8, min(app.winfo_rooty() + 30, bottom - height - 8))
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        dialog.minsize(min(400, width), min(300, height))
        container = ttk.Frame(dialog, padding=16)
        container.pack(fill="both", expand=True)
        summary = ttk.Label(container, justify="left", wraplength=max(1, width - 32), text=(
            f"FFTIC Randomizer {VERSION}\n\n"
            "Randomization rules adapted from Rumble Chaos Crashdown v27 by abyssonym.\n"
            "Game archive and table conversion powered by FF16Tools by Nenkai.\n"
            "Mod support uses Reloaded-II and Nenkai's FFTIC mod loader.\n"
            "Event metadata adapted from Gibbed's Final Fantasy Tactics tools.\n\n"
            "Credits, component licenses, and third-party notices:"))
        summary.pack(anchor="w", fill="x", pady=(0, 12))
        close = ttk.Button(container, text="Close", command=dialog.destroy)
        close.pack(side="bottom", anchor="e", pady=(12, 0))
        notice_frame = ttk.Frame(container)
        notice_frame.pack(fill="both", expand=True)
        notices = tk.Text(notice_frame, wrap="word", font="TkDefaultFont", padx=8, pady=8)
        scrollbar = ttk.Scrollbar(notice_frame, orient="vertical", command=notices.yview)
        notices.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        notices.pack(fill="both", expand=True)
        try:
            text = (resource_root(project_root) / "THIRD_PARTY_NOTICES.txt").read_text(encoding="utf-8-sig")
        except OSError:
            text = "The third-party notices file is unavailable in this package."
        notices.insert("1.0", text)
        notices.configure(state="disabled")
        dialog.bind("<Escape>", lambda event: dialog.destroy())
        dialog.bind("<Configure>", lambda event: summary.configure(wraplength=max(1, event.width - 32))
                    if event.widget == dialog else None, add="+")
        dialog.bind("<Destroy>", lambda event: credits_dialog.__setitem__(0, None)
                    if event.widget == dialog else None, add="+")
        close.focus_set()

    generate_button = ttk.Button(buttons, text="Generate randomizer mod", command=generate)
    output_button = ttk.Button(buttons, text="Open output", command=open_output)
    about_button = ttk.Button(buttons, text="About / Credits", command=show_credits)
    tips.add(generate_button, "Create an installable mod and spoiler report from these settings. The mod is saved in the output folder; enable it in Reloaded-II to play this seed.")
    tips.add(output_button, "Open the latest generated seed folder, or your selected output folder if you have not generated a seed yet.")
    tips.add(about_button, "View the randomizer version, project credits, and licenses for bundled components.")

    def layout_footer(event):
        status_label.configure(wraplength=max(1, event.width - 36))
        available = max(1, event.width - 36)
        row = column = used = 0
        for button in (generate_button, output_button, about_button):
            needed = button.winfo_reqwidth() + (12 if column else 0)
            if column and used + needed > available:
                row += 1
                column = used = 0
                needed = button.winfo_reqwidth()
            button.grid(row=row, column=column, sticky="w",
                        padx=(12 if column else 0, 0), pady=(6 if row else 0, 0))
            used += needed
            column += 1

    def wrap_descriptions(event):
        width = max(1, event.width - 36)
        subtitle.configure(wraplength=width)
        description.configure(wraplength=width)

    footer.bind("<Configure>", layout_footer)
    frame.bind("<Configure>", wrap_descriptions, add="+")
    settings.bind_controls()
    return app


def run(project_root):
    create_app(project_root).mainloop()
