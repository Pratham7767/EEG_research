"""Start window: choose Demo or Real use (or, as a stage backup, replay a recorded session)."""
import customtkinter as ctk

from .. import config
from . import theme

DESCRIPTIONS = {
    "demo": ("Demo", "For a presentation (about 10 minutes).",
             ["Stress and fatigue start after 1 minute (instead of 2)",
              "Break prompt possible after 3 minutes; a sure prompt at 6 minutes",
              "Scene buttons: Rest, Eyes closed, Mental math, Relax",
              "Summary shows what changed in each scene"]),
    "real": ("Real use", "For an actual work session (30 minutes or more).",
             ["Stress and fatigue reference: your first 2 minutes of work",
              "Break prompt after 3 minutes of high fatigue (after 10 minutes), or after 50 minutes",
              "Sleepiness check-in every 10 minutes",
              "Markers for anything you want to note"]),
}


class StartWindow(ctk.CTk):
    """Returns `.choice` = ("demo" | "real", replay_path or None, stress_break_on), or None if closed."""

    def __init__(self, sessions_root=config.SESSIONS_DIR, simulate=None):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title("Cognitive Score")
        self.configure(fg_color=theme.PAGE)
        self.resizable(False, False)
        self.choice = None
        self.sessions_root = sessions_root
        ctk.CTkLabel(self, text="Cognitive Score", font=theme.font(28, "bold"), text_color=theme.INK).pack(
            anchor="w", padx=32, pady=(28, 0))
        sub = "Choose how you want to use it." + ("   (SIMULATOR: no headphones needed)" if simulate else "")
        ctk.CTkLabel(self, text=sub, font=theme.font(14), text_color=theme.MUTED).pack(anchor="w", padx=32, pady=(2, 18))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(padx=24)
        for mode in ("demo", "real"):
            self._card(row, mode).pack(side="left", padx=8, anchor="n")

        self.stress_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(self, text="Full-screen stress break (opens when stress stays high)", variable=self.stress_var,
                      font=theme.font(13), text_color=theme.INK_2).pack(anchor="w", padx=32, pady=(18, 0))
        self.replay_row = ctk.CTkFrame(self, fg_color="transparent")
        self.replay_row.pack(fill="x", padx=32, pady=(14, 22))
        self._build_replay()
        self.bind("<Escape>", lambda _e: self.quit())
        self.protocol("WM_DELETE_WINDOW", self.quit)
        self.after(50, self._centre)

    def _card(self, parent, mode):
        title, sub, bullets = DESCRIPTIONS[mode]
        card = ctk.CTkFrame(parent, fg_color=theme.SURFACE, corner_radius=12, border_width=1,
                            border_color=theme.BORDER, width=380)
        ctk.CTkLabel(card, text=title, font=theme.font(22, "bold"), text_color=theme.INK).pack(anchor="w", padx=22, pady=(18, 0))
        ctk.CTkLabel(card, text=sub, font=theme.font(13), text_color=theme.INK_2).pack(anchor="w", padx=22, pady=(0, 10))
        for b in bullets:
            ctk.CTkLabel(card, text=f"•  {b}", font=theme.font(12), text_color=theme.MUTED, wraplength=330,
                         justify="left").pack(anchor="w", padx=22, pady=1)
        ctk.CTkButton(card, text=f"Start {title.lower()}", height=40, corner_radius=8, font=theme.font(15, "bold"),
                      command=lambda m=mode: self._pick(m)).pack(fill="x", padx=22, pady=(14, 20))
        return card

    def _build_replay(self):
        from ..replay import list_sessions
        sessions = list_sessions(self.sessions_root)
        ctk.CTkLabel(self.replay_row, text="Backup if the headphones fail on stage:", font=theme.font(13),
                     text_color=theme.MUTED).pack(side="left")
        if not sessions:
            ctk.CTkLabel(self.replay_row, text="no recorded session of 1 min or more yet", font=theme.font(13),
                         text_color=theme.MUTED).pack(side="left", padx=8)
            return
        self._sessions = {f"{name}   ({live / 60:.0f} min, {config.MODE_LABELS.get(mode, mode)})": path
                          for path, name, live, mode in sessions}
        labels = list(self._sessions)
        self.replay_var = ctk.StringVar(value=labels[0])
        ctk.CTkOptionMenu(self.replay_row, values=labels, variable=self.replay_var, width=330,
                          font=theme.font(12)).pack(side="left", padx=8)
        ctk.CTkButton(self.replay_row, text="Replay", width=90, fg_color=theme.SURFACE, hover_color=theme.RAISED,
                      border_width=1, border_color=theme.BORDER, command=self._replay).pack(side="left")

    def _pick(self, mode):
        self.choice = (mode, None, bool(self.stress_var.get()))
        self.quit()

    def _replay(self):
        self.choice = ("demo", self._sessions[self.replay_var.get()], bool(self.stress_var.get()))
        self.quit()

    def close(self):
        """Hide, do not destroy: destroying a first customtkinter root leaves its internal timers firing
        into the dead interpreter ("invalid command name ...check_dpi_scaling" in the console)."""
        self.withdraw()

    def _centre(self):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x, y = (self.winfo_screenwidth() - w) // 2, (self.winfo_screenheight() - h) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")


_KEEP = []          # the hidden start window lives until the process ends (see StartWindow.close)


def choose(sessions_root=config.SESSIONS_DIR, simulate=None):
    win = StartWindow(sessions_root, simulate)
    _KEEP.append(win)
    win.mainloop()
    choice = win.choice
    win.close()
    return choice
