"""MI Live: imagine LEFT or RIGHT hand, see the decision in real time, drive a bot.

Flow (headset):  1 Signal check  ->  2 Calibration on a calm full screen (cued trials, recorded)
                 ->  your own model is trained automatically (yours + BCI IV 2b, honest score)
                 ->  3 Cued test  ->  free mode (the bot follows).
  python live.py                          headset (LEHeadPhones2)
  python live.py --source sim             simulator (hold the Left/Right arrow keys to 'imagine')
  python live.py --source replay2b --sub 4 --session 4 [--speed 2]
                                          a real 2b session streamed as if live, model never saw B04
  python live.py --source sim --speed 8 --selftest   runs the whole flow by itself -> _out/selftest.json
"""
import argparse
import json
import sys
import threading
import time
import traceback
from collections import deque
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, ttk

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import milive  # noqa: E402,F401  (puts apps/mi_bci on the path)
from mibci import config as C  # noqa: E402
from mibci.dsp import apply_montage  # noqa: E402
from mibci.paradigm import Paradigm, RecordedParadigm, make_schedule  # noqa: E402
from mibci.recorder import Recorder  # noqa: E402
from mibci.sources import HeadphonesSource, SimulatedSource  # noqa: E402
from milive import settings as S  # noqa: E402
from milive.bot import SimBot  # noqa: E402
from milive.commands import CommandSender  # noqa: E402
from milive.cued import CuedSession, format_results  # noqa: E402
from milive.dsp_extra import signal_check  # noqa: E402
from milive.models import available_models, load_model  # noqa: E402
from milive.personal import format_report, train_personal, user_runs  # noqa: E402
from milive.pipeline import LivePipeline  # noqa: E402

COL = dict(bg="#0f1317", panel="#1a2027", fg="#e8edf2", dim="#7b8794", grid="#2c3540", left="#4aa3ff",
           right="#ffb347", good="#3ccf6e", bad="#ff5c5c", thr="#46525f", warn="#ffd25c", calm="#c9ced6")
BAR_W, BAR_H = 760, 170
TR_W, TR_H = 760, 110
BOT_W, BOT_H = 340, 230
K_W, K_H = 380, 160
SIG_S = 15


class App:
    def __init__(self, root, args):
        self.root, self.args = root, args
        root.title("MI Live - left / right in real time  (BCI IV 2b model + your calibration)")
        root.configure(bg=COL["bg"])
        self.kind = args.source
        V = tk.StringVar
        self.subject, self.status, self.info, self.model_choice = V(value=args.subject), V(), V(), V()
        self.thr, self.hold = tk.DoubleVar(value=S.THRESHOLD), tk.DoubleVar(value=S.HOLD_S)
        self.neutral = V(value=S.NEUTRAL)
        self.bias_on, self.adaptive = tk.BooleanVar(value=True), tk.BooleanVar(value=True)
        self.calm_display = tk.BooleanVar(value=True)
        self.n_trials, self.fb = tk.IntVar(value=10), tk.BooleanVar(value=False)
        self.cal_blocks, self.cal_trials = tk.IntVar(value=3), tk.IntVar(value=10)
        self.cal_movement, self.all_days = tk.BooleanVar(value=False), tk.BooleanVar(value=False)
        self.udp_on, self.udp_addr, self.serial_port = tk.BooleanVar(value=False), V(value="127.0.0.1:5005"), V()
        self.source = self.pipe = self.session = self.rec_session = None
        self.streaming = False
        self.sender = CommandSender()
        self.bot = SimBot(BOT_W, BOT_H)
        self.trace = deque(maxlen=int(10 / S.OUT_DT))
        self.last = None
        self.cmd_now = "STOP"
        self.last_draw = 0.0
        self.last_tick = time.perf_counter()
        self.last_data_t = None
        self.rate_hist = deque(maxlen=400)
        self.stalled = self._was_stalled = False
        self.exclude = set()
        self.sim_key = None
        self.seen_calib = 0
        self.last_results = None
        self.sig = None                 # running signal check
        self.sig_result = None
        self.calm = None                # running calm calibration
        self.training = False
        self.train_rep = None
        self.st = dict(stage=0, saw_bar=False, saw_arrow=False, t0=time.time())
        self.model_paths = {}
        self.sound = None
        try:
            from mibci.sound import Sound
            self.sound = Sound(muted=args.selftest)
        except Exception:
            pass
        self._build()
        self._fill_models()
        if self.kind == "sim":
            root.after(100, self._start_sim)
        elif self.kind == "replay2b":
            root.after(100, self._start_replay)
        else:
            self.status.set("Headset: put the headphones on, press Scan, pick them, Connect.")
        for key, cls in (("Left", C.LEFT), ("Right", C.RIGHT)):
            root.bind(f"<KeyPress-{key}>", lambda e, c=cls: self._key(c))
            root.bind(f"<KeyRelease-{key}>", lambda e: self._key(None))
        root.bind("<Escape>", lambda e: self.stop_test())
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(20, self.loop)
        if args.selftest and self.kind == "sim":
            root.after(300, self._selftest)

    # ================================================================== layout
    def _lab(self, parent, text="", **kw):
        return tk.Label(parent, text=text, bg=kw.pop("bg", COL["bg"]), fg=kw.pop("fg", COL["fg"]), **kw)

    def _build(self):
        try:
            ttk.Style().theme_use("clam")
        except Exception:
            pass
        top = tk.Frame(self.root, bg=COL["bg"])
        top.pack(fill="x", padx=10, pady=(8, 2))
        self._lab(top, "Subject").pack(side="left")
        e = ttk.Entry(top, textvariable=self.subject, width=9)
        e.pack(side="left", padx=(4, 10))
        e.bind("<FocusOut>", lambda ev: self._fill_models())
        self._lab(top, "Model").pack(side="left")
        self.model_box = ttk.Combobox(top, textvariable=self.model_choice, width=70, state="readonly")
        self.model_box.pack(side="left", padx=4)
        self.model_box.bind("<<ComboboxSelected>>", lambda ev: self._model_changed())
        if self.kind == "headset":
            ttk.Button(top, text="Scan", command=self.scan).pack(side="left", padx=(12, 2))
            self.dev_box = ttk.Combobox(top, width=24, state="readonly")
            self.dev_box.pack(side="left", padx=2)
            ttk.Button(top, text="Connect", command=self.connect).pack(side="left", padx=2)
            ttk.Button(top, text="Disconnect", command=self.disconnect).pack(side="left", padx=2)
        self._lab(self.root, textvariable=self.status, fg=COL["warn"], anchor="w").pack(fill="x", padx=10)
        self._lab(self.root, textvariable=self.info, fg=COL["dim"], anchor="w",
                  font=("Consolas", 9)).pack(fill="x", padx=10)

        mid = tk.Frame(self.root, bg=COL["bg"])
        mid.pack(fill="x", padx=10, pady=4)
        lc = tk.Frame(mid, bg=COL["bg"])
        lc.pack(side="left", anchor="n")
        self.bar = tk.Canvas(lc, width=BAR_W, height=BAR_H, bg=COL["panel"], highlightthickness=0)
        self.bar.pack()
        self._lab(lc, "last 10 s:  thin = raw output (squashed),  thick = 2 s smoothed (what the bot uses),  "
                  "red ticks = artifact", fg=COL["dim"], font=("", 8)).pack(anchor="w")
        self.tr = tk.Canvas(lc, width=TR_W, height=TR_H, bg=COL["panel"], highlightthickness=0)
        self.tr.pack()
        rc = tk.Frame(mid, bg=COL["bg"])
        rc.pack(side="left", anchor="n", padx=(10, 0))
        self.cmd_lab = tk.Label(rc, text="STOP", font=("", 26, "bold"), bg=COL["bg"], fg=COL["dim"])
        self.cmd_lab.pack()
        self.botc = tk.Canvas(rc, width=BOT_W, height=BOT_H, bg=COL["panel"], highlightthickness=0)
        self.botc.pack()
        ttk.Button(rc, text="Reset bot", command=self.bot.reset).pack(pady=2)

        ctl = tk.Frame(self.root, bg=COL["bg"])
        ctl.pack(fill="x", padx=10, pady=2)
        r1 = tk.Frame(ctl, bg=COL["bg"])
        r1.pack(fill="x", pady=2)
        self.btns = [ttk.Button(r1, text=f"1. Signal check ({SIG_S} s)", command=self.start_signal_check)]
        self.btns[-1].pack(side="left")
        self.btns.append(ttk.Button(r1, text="2. Calibrate (calm screen)", command=self.start_calibration))
        self.btns[-1].pack(side="left", padx=(12, 2))
        self._lab(r1, "blocks").pack(side="left")
        ttk.Spinbox(r1, from_=2, to=8, textvariable=self.cal_blocks, width=3).pack(side="left", padx=2)
        self._lab(r1, "x trials/hand").pack(side="left")
        ttk.Spinbox(r1, from_=4, to=20, textvariable=self.cal_trials, width=3).pack(side="left", padx=2)
        ttk.Checkbutton(r1, text="+ real-squeeze warm-up block", variable=self.cal_movement).pack(side="left", padx=4)
        self.btns.append(ttk.Button(r1, text="Retrain my model", command=self.train_model))
        self.btns[-1].pack(side="left", padx=(10, 2))
        ttk.Checkbutton(r1, text="use all days", variable=self.all_days).pack(side="left")

        r1b = tk.Frame(ctl, bg=COL["bg"])
        r1b.pack(fill="x", pady=2)
        self.btns.append(ttk.Button(r1b, text="3. Cued test", command=self.start_test))
        self.btns[-1].pack(side="left")
        self._lab(r1b, "trials/hand").pack(side="left", padx=(6, 0))
        ttk.Spinbox(r1b, from_=2, to=40, textvariable=self.n_trials, width=4).pack(side="left", padx=2)
        ttk.Checkbutton(r1b, text="show feedback bar", variable=self.fb).pack(side="left", padx=6)
        ttk.Button(r1b, text="Stop (Esc)", command=self.stop_test).pack(side="left", padx=4)
        self._lab(r1b, "   4. Free mode: just imagine; the bot follows", fg=COL["dim"]).pack(side="left")
        ttk.Checkbutton(r1b, text="calm display", variable=self.calm_display).pack(side="left", padx=10)

        r2 = tk.Frame(ctl, bg=COL["bg"])
        r2.pack(fill="x", pady=2)
        self._lab(r2, "Threshold |v|").pack(side="left")
        tk.Scale(r2, from_=0.1, to=0.95, resolution=0.05, orient="horizontal", variable=self.thr, length=130,
                 bg=COL["bg"], fg=COL["fg"], highlightthickness=0).pack(side="left")
        self._lab(r2, "Hold (s)").pack(side="left", padx=(8, 0))
        tk.Scale(r2, from_=0.1, to=2.0, resolution=0.1, orient="horizontal", variable=self.hold, length=110,
                 bg=COL["bg"], fg=COL["fg"], highlightthickness=0).pack(side="left")
        self._lab(r2, "When undecided").pack(side="left", padx=(8, 2))
        ttk.Combobox(r2, textvariable=self.neutral, values=["STOP", "FORWARD"], width=9,
                     state="readonly").pack(side="left")
        ttk.Checkbutton(r2, text="remove bias", variable=self.bias_on).pack(side="left", padx=8)
        ttk.Checkbutton(r2, text="keep adapting alignment", variable=self.adaptive,
                        command=self._adaptive_changed).pack(side="left")

        r3 = tk.Frame(ctl, bg=COL["bg"])
        r3.pack(fill="x", pady=2)
        ttk.Checkbutton(r3, text="Send to bot by UDP", variable=self.udp_on, command=self._udp).pack(side="left")
        ttk.Entry(r3, textvariable=self.udp_addr, width=18).pack(side="left", padx=4)
        self._lab(r3, "Serial port (e.g. COM5)").pack(side="left", padx=(14, 2))
        ttk.Entry(r3, textvariable=self.serial_port, width=8).pack(side="left")
        ttk.Button(r3, text="Open", command=self._serial_open).pack(side="left", padx=2)
        ttk.Button(r3, text="Close", command=self.sender.close_serial).pack(side="left")
        self.send_lab = self._lab(r3, fg=COL["dim"])
        self.send_lab.pack(side="left", padx=10)

        bottom = tk.Frame(self.root, bg=COL["bg"])
        bottom.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self.txt = tk.Text(bottom, width=80, height=11, bg=COL["panel"], fg=COL["fg"], font=("Consolas", 9),
                           insertbackground=COL["fg"], relief="flat")
        self.txt.pack(side="left", fill="both", expand=True)
        kf = tk.Frame(bottom, bg=COL["bg"])
        kf.pack(side="left", padx=(10, 0), anchor="n")
        self._lab(kf, "Kappa over time after the cue (competition metric)", fg=COL["dim"], font=("", 8)).pack()
        self.kc = tk.Canvas(kf, width=K_W, height=K_H, bg=COL["panel"], highlightthickness=0)
        self.kc.pack()
        self._say("Steps: 1) Signal check  2) Calibrate on the calm screen (your model is trained from it)  "
                  "3) Cued test  4) Free mode.\nUnplug the laptop charger (mains hum); keep jaw, eyes and hands still.")

    def _say(self, text):
        self.txt.insert("end", text + ("" if text.endswith("\n") else "\n"))
        self.txt.see("end")

    def _busy(self):
        return self.session is not None or self.calm is not None or self.sig is not None or self.training

    # ================================================================== models / sources
    def _fill_models(self, select_path=None):
        if self.kind == "replay2b":
            return
        items = available_models(self.subject.get().strip())
        self.model_paths = {name: p for name, p in items}
        self.model_box["values"] = [n for n, _ in items]
        if select_path is not None:
            for name, p in items:
                if Path(p) == Path(select_path):
                    self.model_choice.set(name)
        if self.model_choice.get() not in self.model_paths:
            self.model_choice.set(items[0][0])

    def _model_changed(self):
        if self.source is not None:
            self._new_pipeline()
            self._say(f"Model: {self.model_choice.get()}. Alignment restarts; give it ~30 s (or calibrate).")

    def _new_pipeline(self, model=None):
        if self.session is not None:
            self.stop_test()
        model = model or load_model(self.model_paths[self.model_choice.get()])
        self.pipe = LivePipeline(model, adaptive=bool(self.adaptive.get()))
        self.seen_calib = 0
        self.trace.clear()
        self.last = None

    def _adaptive_changed(self):
        if self.pipe is not None:
            self.pipe.set_adaptive(self.adaptive.get())
            self._say("Alignment: " + ("adapting again" if self.adaptive.get() else "FROZEN as it is now"))

    def _attach(self, source):
        self.source = source
        self.last_data_t = time.perf_counter()
        self.rate_hist.clear()
        self._new_pipeline(getattr(self, "_replay_model", None))
        self.streaming = True

    def _start_sim(self):
        src = SimulatedSource(skill=self.args.skill, seed=int(time.time()) % 1000, speed=self.args.speed)
        src.start()
        self._attach(src)
        self.status.set(f"SIMULATOR (skill {self.args.skill}). Hold the Left / Right arrow key to 'imagine'. "
                        f"Recordings go to {S.DATA_LIVE}.")

    def _start_replay(self):
        from milive.replay2b import Replay2bSource, load_session, loso_model
        sub, ses = self.args.sub, self.args.session
        self.status.set(f"Building the model without B{sub:02d} ...")
        self.root.update()
        try:
            model = loso_model(sub)
            eeg, events, art = load_session(sub, ses)
        except Exception as e:
            self.status.set(f"Replay could not start: {e}")
            return messagebox.showerror("Replay", f"Could not load BCI IV 2b B{sub:02d}:\n{e}\n\n"
                                        f"The 2b .mat files must be in {C.BCI2B_DIR}")
        self._replay_model = model
        name = f"{model.name}, trained on the 8 other 2b subjects (B{sub:02d} never seen)"
        self.model_box["values"] = [name]
        self.model_choice.set(name)
        self.model_box.configure(state="disabled")
        for b in self.btns:
            b.configure(state="disabled")
        self._attach(Replay2bSource(eeg, speed=self.args.speed))
        self.pipe.start_calibration([("data", 60)])
        self.session = CuedSession(RecordedParadigm("feedback", events), offset=0, feedback=True,
                                   min_cue=60 * S.FS)
        self.exclude = art
        mins = len(eeg) / S.FS / 60
        self.status.set(f"REPLAY of real EEG: BCI IV 2b B{sub:02d} session {ses} ({mins:.0f} min at "
                        f"{self.args.speed}x). Arrows = the cue the person saw.")
        self._say(f"Replay B{sub:02d} session {ses}: first 60 s warm-up (alignment, no labels), then every trial "
                  f"is scored. {len(art)} trials marked as artifacts in 2b are left out, as in the competition.")

    def scan(self):
        self.status.set("Scanning for 8 s ...")

        def work():
            try:
                src = HeadphonesSource()
                devs = src.scan(8)
                self.root.after(0, lambda: self._scanned(src, devs))
            except Exception as e:
                msg = f"Scan failed: {e}"
                self.root.after(0, lambda: self.status.set(msg))
        threading.Thread(target=work, daemon=True).start()

    def _scanned(self, src, devs):
        self.hs, self.devs = src, devs
        self.dev_box["values"] = [f"{d['name']} {d['serial']}" for d in devs]
        if devs:
            self.dev_box.current(0)
            self.status.set(f"Found {len(devs)}. Press Connect.")
        else:
            self.status.set("Nothing found. Headphones on and charged? Bluetooth on? mi_bci closed? Scan again.")

    def connect(self):
        if not getattr(self, "devs", None):
            return
        dev = self.devs[max(0, self.dev_box.current())]
        self.status.set("Connecting ...")

        def work():
            try:
                self.hs.connect(dev["info"])
                self.hs.start()
                self.root.after(0, lambda: (self._attach(self.hs), self.status.set(
                    "Streaming. Wait ~10 s for the signal to settle, then 1. Signal check.")))
            except Exception as e:
                msg = f"Connect failed: {e}"
                self.root.after(0, lambda: self.status.set(msg))
        threading.Thread(target=work, daemon=True).start()

    def disconnect(self):
        self.streaming = False
        if self.calm is not None:
            self._calm_abort()
        if self.session is not None:
            self.stop_test()
        if isinstance(self.source, HeadphonesSource):
            try:
                self.source.disconnect()
            except Exception:
                pass
        self.source = None
        self.status.set("Disconnected.")

    def _key(self, cls):
        self.sim_key = cls

    def _rec_root(self):
        return C.DATA_DIR if isinstance(self.source, HeadphonesSource) else S.DATA_LIVE

    def _subject(self):
        return self.subject.get().strip() or ("SIM" if self.kind == "sim" else "P00")

    # ================================================================== 1. signal check
    def start_signal_check(self):
        if self.pipe is None or self._busy():
            return
        self.sig = dict(buf=[], n=0)
        self._say(f"Signal check: sit still, eyes open on the screen, relax jaw, {SIG_S} s ...")

    def _sig_feed(self, x):
        m = apply_montage(x)[:, [1, 2]]
        self.sig["buf"].append(m)
        self.sig["n"] += len(m)
        if self.sig["n"] >= SIG_S * S.FS:
            r = signal_check(np.vstack(self.sig["buf"]))
            self.sig, self.sig_result = None, r
            self._say(f"SIGNAL CHECK: {r['verdict']}  | EEG 8-30 Hz C3 {r['rms_8_30'][0]} uV, C4 {r['rms_8_30'][1]} uV"
                      f" | 50 Hz hum C3 {r['hum_50'][0]} uV, C4 {r['hum_50'][1]} uV | alpha peak "
                      f"{r['alpha_peak_hz']:.1f} Hz\n  " + "\n  ".join(r["advice"]))
            self.status.set(f"Signal check: {r['verdict']}" + ("" if r["level"] == 0 else " - see advice below, "
                            "fix and check again"))

    # ================================================================== 2. calm calibration
    def _ints(self, *vars_):
        try:
            return [int(v.get()) for v in vars_]
        except Exception:
            return None

    def start_calibration(self, test_trials=None):
        if self.pipe is None or self._busy() or self.kind == "replay2b":
            return
        if test_trials is None:
            v = self._ints(self.cal_blocks, self.cal_trials)
            if not v or not (2 <= v[0] <= 8 and 4 <= v[1] <= 20):
                return messagebox.showinfo("Calibrate", "Blocks 2-8 and trials per hand 4-20, whole numbers.")
            nb, nt = v
        else:
            nb, nt = 1, test_trials
        if not self.args.selftest:
            if self.sig_result is None:
                if not messagebox.askyesno("Calibrate", "No signal check yet. Calibrate anyway?"):
                    return
            elif self.sig_result["level"] == 2:
                if not messagebox.askyesno("Calibrate", "The last signal check was BAD:\n\n" +
                                           "\n".join(self.sig_result["advice"]) +
                                           "\n\nRecordings with this signal will not train a good model. Continue anyway?"):
                    return
        blocks = ([("movement", max(4, nt // 2))] if self.cal_movement.get() and test_trials is None else []) \
            + [("screening", nt)] * nb
        win = tk.Toplevel(self.root)
        win.configure(bg="black")
        win.title("Calibration")
        try:
            win.attributes("-fullscreen", not self.args.selftest)
        except Exception:
            pass
        if self.args.selftest:
            win.geometry("900x600")
        c = tk.Canvas(win, bg="black", highlightthickness=0)
        c.pack(fill="both", expand=True)
        win.bind("<space>", lambda e: self._calm_next())
        win.bind("<Escape>", lambda e: self._calm_abort())
        win.protocol("WM_DELETE_WINDOW", self._calm_abort)
        win.focus_force()
        self.calm = dict(blocks=blocks, k=0, state="intro", win=win, c=c, runs=[], key=None,
                         test=test_trials is not None, results=[])
        win.bind("<Configure>", lambda e: self.calm is not None and self.calm.update(key=None))
        if test_trials is None:
            self.pipe.reset_alignment()              # alignment from now on (drops the settling seconds)
            self.pipe.calib_result = None
        else:
            self._say(f"Cued test on the calm screen with: {self.model_choice.get()}")
            return
        mins = sum(2 * n for _, n in blocks) * 9 / 60
        self._say(f"Calibration on the calm screen: {len(blocks)} blocks ({', '.join(f'{t} {n}+{n}' for t, n in blocks)}),"
                  f" about {mins:.0f} min plus breaks. Space = start / next block, Esc = stop.")

    def _calm_next(self):
        cm = self.calm
        if cm is None or cm["state"] not in ("intro", "break") or self.session is not None:
            return
        run_type, n = cm["blocks"][cm["k"]]
        par = Paradigm(run_type, make_schedule(n, seed=int(time.time() * 1000) % 2 ** 31),
                       seed=int(time.time()) % 2 ** 31)
        meta = (dict(app="mi_live", cued_test=True, calm_screen=True, model=self.model_choice.get()) if cm["test"]
                else dict(app="mi_live", calm_calibration=True, block=cm["k"] + 1, blocks=len(cm["blocks"])))
        rec = Recorder(self._subject(), run_type, root=self._rec_root(), meta=meta)
        self.rec_session = rec
        self.session = CuedSession(par, offset=self.pipe.n, recorder=rec, sound=self.sound, feedback=False)
        cm["state"] = "run"

    def _calm_block_done(self, rec_dir):
        cm = self.calm
        cm["runs"].append(rec_dir)
        cm["k"] += 1
        if cm["k"] < len(cm["blocks"]):
            cm["state"] = "break"
        else:
            cm["state"] = "done"
            self.root.after(1500, self._calm_finish)

    def _calm_finish(self, aborted=False):
        cm, self.calm = self.calm, None
        if cm is None:
            return
        try:
            cm["win"].destroy()
        except Exception:
            pass
        if cm["test"]:
            for res in cm["results"]:
                self.last_results = res
                self._say("\n" + format_results(res, "TEST RESULT (calm screen)" + (" (stopped early)" if aborted else ""))
                          + "\n" + self._confirm_line(res))
            return
        imag = [p for p in cm["runs"] if json.loads((Path(p) / "run.json").read_text()).get("run_type") == "screening"]
        self._say(f"Calibration {'stopped' if aborted else 'finished'}: {len(cm['runs'])} block(s) recorded.")
        if imag:
            self.train_model()

    def _calm_abort(self):
        if self.calm is None:
            return
        if self.session is not None:
            self._finish_session(stopped=True)
        self._calm_finish(aborted=True)

    def _draw_calm(self):
        cm = self.calm
        c = cm["c"]
        s = self.session
        ph = s.phase if s else None
        cls = s.cls if s else None
        W, H = c.winfo_width(), c.winfo_height()
        if W < 200 or H < 200:
            return                                   # window not laid out yet (full screen not applied)
        key = (cm["state"], ph, cls, cm["k"], W, H)
        if key == cm["key"]:
            return                                   # nothing changed: do not redraw (no flicker)
        cm["key"] = key
        c.delete("all")
        cx, cy = W / 2, H / 2
        nb = len(cm["blocks"])
        if cm["state"] in ("intro", "break"):
            run_type, n = cm["blocks"][cm["k"]]
            what = ("REALLY SQUEEZE the hand the arrow points to (a firm fist), then relax."
                    if run_type == "movement" else
                    "IMAGINE squeezing the hand the arrow points to. Feel the squeeze, do not move.")
            title = "Cued test" if cm.get("test") else "Calibration"
            head = title if cm["state"] == "intro" else f"Block {cm['k']} of {nb} done. Rest, blink, move."
            txt = (f"{head}\n\nNext: block {cm['k'] + 1} of {nb}  ({n} left + {n} right, mixed)\n\n{what}\n\n"
                   "Keep your EYES ON THE CROSS the whole time (do not look at the arrow tip).\n"
                   "A beep, then a small arrow on the cross for about a second.\n"
                   "Keep going until the cross disappears. Relax and blink when the screen is empty.\n\n"
                   "Press SPACE to start.        Esc = stop")
            c.create_text(cx, cy, text=txt, fill=COL["calm"], font=("", 16), justify="center", width=min(W * 0.8, 1100))
        elif cm["state"] == "done":
            c.create_text(cx, cy, text="Done. Thank you." + ("" if cm.get("test") else "\n\nTraining your model ..."),
                          fill=COL["calm"],
                          font=("", 18), justify="center")
        else:
            if ph in ("fixation", "cue", "task"):
                L = min(W, H) * 0.06
                c.create_line(cx - L, cy, cx + L, cy, fill=COL["calm"], width=3)
                c.create_line(cx, cy - L, cx, cy + L, fill=COL["calm"], width=3)
            if ph == "cue" and cls is not None:
                self.st["saw_arrow"] = True
                d = -1 if cls == C.LEFT else 1
                L = min(W, H) * 0.06                 # same size as the cross arms, centred on the cross
                c.create_line(cx - d * L, cy, cx + d * L, cy, fill=COL["calm"], width=9, arrow="last",
                              arrowshape=(22, 26, 11))

    # ================================================================== your model
    def train_model(self):
        if self.training or self.kind == "replay2b":
            return
        subj = self._subject()
        paths = user_runs(subj, self._rec_root(), today_only=not self.all_days.get())
        if len(paths) < 1:
            return messagebox.showinfo("Train", "No cued runs for this subject yet. Calibrate first.")
        self.training = True
        self.status.set(f"Training your model on {len(paths)} run(s) ...")

        def progress(msg):
            self.root.after(0, lambda: self.status.set(msg))

        def work():
            try:
                model, rep, seeds = train_personal(paths, subj, out_dir=Path(self._rec_root()) / subj / "decoders_live",
                                                   progress=progress)
                self.root.after(0, lambda: self._trained(model, rep, seeds))
            except Exception as e:
                err = f"Training failed: {e}"
                (S.OUT_DIR / "error_log.txt").open("a").write(traceback.format_exc() + "\n")
                self.root.after(0, lambda: (self.status.set(err), setattr(self, "training", False)))
        threading.Thread(target=work, daemon=True).start()

    def _trained(self, model, rep, seeds):
        self.training = False
        self.train_rep = rep
        self._say("\n" + format_report(rep) + "\n")
        self._fill_models(select_path=rep.get("model_path"))
        self._new_pipeline(model)
        if self.pipe.seed_alignment(seeds):
            self._say("Now using your model; alignment started from your calibration data.")
        self.status.set(f"Your model: {rep['verdict']}"
                        + (f" ({100 * rep['accuracy']:.0f} % on runs it never saw)" if "accuracy" in rep else "")
                        + ". Next: 3. Cued test.")

    # ================================================================== 3. cued test
    def start_test(self):
        if self.pipe is None or self._busy() or self.kind == "replay2b":
            return
        v = self._ints(self.n_trials)
        if not v or not 2 <= v[0] <= 40:
            return messagebox.showinfo("Test", "Trials per hand must be a whole number from 2 to 40.")
        n = v[0]
        fb = bool(self.fb.get())
        if not fb:                                   # no feedback: same calm full screen as the calibration
            return self.start_calibration(test_trials=n)
        run_type = "feedback" if fb else "screening"
        par = Paradigm(run_type, make_schedule(n, seed=int(time.time()) % 2 ** 31), seed=int(time.time()) % 2 ** 31)
        rec = Recorder(self._subject(), run_type, root=self._rec_root(),
                       meta=dict(app="mi_live", cued_test=True, model=self.model_choice.get()))
        self.rec_session = rec
        self.session = CuedSession(par, offset=self.pipe.n, recorder=rec, sound=self.sound, feedback=fb)
        self._say(f"Cued test: {n} LEFT + {n} RIGHT ({'with' if fb else 'without'} feedback). Cross + beep, then "
                  "an arrow: imagine squeezing that hand until the cross goes away.")

    def stop_test(self):
        if self.kind == "replay2b":
            return
        if self.calm is not None:
            return self._calm_abort()
        if self.session is not None:
            self._finish_session(stopped=True)

    def _finish_session(self, stopped=False):
        s, self.session = self.session, None
        res = s.results(exclude=self.exclude)
        rec, self.rec_session = self.rec_session, None
        is_calm = self.calm is not None
        if is_calm and self.calm["test"]:
            self.calm["results"].append(res)
        if not is_calm:
            self.last_results = res
            self._say("\n" + format_results(res, "TEST RESULT" + (" (stopped early)" if stopped else "")) + "\n"
                      + self._confirm_line(res))
        if rec is not None:
            short = {k: v for k, v in res.items() if not k.startswith(("curve", "kappa_"))}
            rec.close(dict(summary=short, decoder=self.pipe.model.to_dict(), stopped_early=stopped,
                           source=getattr(self.source, "name", "?"),
                           source_status=self.source.status() if self.source else None))
            (rec.dir / "mi_live_results.json").write_text(json.dumps(res, indent=1, default=float))
            if is_calm:
                if not stopped:
                    self._calm_block_done(rec.dir)
                else:
                    self.calm["runs"].append(rec.dir)
            else:
                self._say(f"Saved in {rec.dir.name}.")

    def _confirm_line(self, res):
        """A personal model is only trusted after a cued test on new trials agrees."""
        name = self.model_choice.get()
        if not name.startswith("YOURS") or not res.get("trials"):
            return ""
        ok = res["p"] < 0.05
        path = self.model_paths.get(name)
        try:
            j = json.loads(Path(path).read_text())
            j["meta"].setdefault("tests", []).append(dict(accuracy=res["accuracy"], trials=res["trials"], p=res["p"],
                                                          when=time.strftime("%Y-%m-%d %H:%M:%S")))
            if ok:
                j["meta"]["verdict"] = "READY (confirmed by a cued test)"
            Path(path).write_text(json.dumps(j, indent=1, default=float))
            self._fill_models(select_path=path)
        except Exception:
            pass
        return ("CONFIRMED: your model works on new trials -> READY for free mode." if ok else
                "NOT CONFIRMED on new trials: free mode would mostly guess. Calibrate more blocks, then test again.")

    # ================================================================== bot output
    def _udp(self):
        try:
            self.sender.set_udp(self.udp_addr.get() if self.udp_on.get() else None)
        except Exception as e:
            self.udp_on.set(False)
            messagebox.showerror("UDP", str(e))

    def _serial_open(self):
        try:
            self.sender.open_serial(self.serial_port.get().strip())
            self._say(f"Serial {self.serial_port.get()} open: sends L / R / S / F + newline.")
        except Exception as e:
            messagebox.showerror("Serial", f"Could not open {self.serial_port.get()}: {e}")

    # ================================================================== main loop
    def _sim_task(self):
        if not isinstance(self.source, SimulatedSource):
            return
        cls = self.sim_key
        if self.pipe.calib is not None:
            name, _ = self.pipe.calib.block_at(self.pipe.n)
            cls = {"left": C.LEFT, "right": C.RIGHT}.get(name)
        elif self.session is not None:
            cls = self.session.cls if self.session.phase in ("cue", "task") else None
        elif self.sig is not None or self.calm is not None:
            cls = None
        self.source.set_task(cls)

    def loop(self):
        try:
            now = time.perf_counter()
            dt = min(0.2, now - self.last_tick)
            self.last_tick = now
            if self.streaming and self.source is not None and self.pipe is not None:
                p = self.pipe
                p.logic.threshold, p.logic.hold_s, p.logic.neutral = self.thr.get(), self.hold.get(), self.neutral.get()
                p.bias_correct = bool(self.bias_on.get())
                self._sim_task()
                x = self.source.read()
                if len(x):
                    self.last_data_t = now
                    self.rate_hist.append((now, len(x)))
                    outs = p.feed(x)
                    if self.sig is not None:
                        self._sig_feed(x)
                    if self.session is not None:
                        k0 = len(self.session.trial_log)
                        self.session.process(x, p.n, outs)
                        if self.calm is None:
                            for line in self.session.trial_log[k0:]:
                                self._say(line)
                        if self.session.done:
                            self._finish_session()
                    for o in outs:
                        self.trace.append((o.d, o.v, o.bad))
                    if outs:
                        self.last = outs[-1]
                if p.calib_count != self.seen_calib:
                    self.seen_calib = p.calib_count
                if getattr(self.source, "finished", False) and self.kind == "replay2b":
                    self.streaming = False
                    if self.session is not None:
                        self._finish_session()
                    self.status.set("Replay finished. See the result below.")
                    if self.args.selftest:
                        self._write_replay_selftest()
            cmd = self.last.cmd if (self.last and self.streaming) else "STOP"
            self.stalled = bool(self.streaming and self.last_data_t is not None and now - self.last_data_t > 1.0)
            if self.stalled or self._busy() or (self.pipe is not None and self.pipe.calib is not None):
                cmd = "STOP"            # no data, or a check / calibration / test / training is running
            self.cmd_now = cmd
            self.bot.step(cmd, dt)
            if self.last is not None:
                self.sender.send(cmd, self.last.v, self.last.d)
            if now - self.last_draw >= 0.04:
                self.last_draw = now
                if self.calm is not None:
                    self._draw_calm()
                else:
                    self._draw()
        except Exception:
            err = traceback.format_exc()
            (S.OUT_DIR / "error_log.txt").open("a").write(time.strftime("%H:%M:%S ") + err + "\n")
            self.status.set("Error (see _out/error_log.txt): " + err.strip().splitlines()[-1])
        self.root.after(15, self.loop)

    # ================================================================== drawing (main window)
    def _draw(self):
        self._draw_bar()
        self._draw_trace()
        self._draw_bot()
        if self.last_results and self.last_results.get("curve_t") and getattr(self, "_k_drawn", None) is not self.last_results:
            self._draw_kappa(self.last_results)
            self._k_drawn = self.last_results
        p = self.pipe
        if p is not None and self.last is not None:
            c3, c4 = self.last.rms
            al = "alignment " + ("adapting" if p.R_fixed is None else "frozen")
            rh = [r for r in self.rate_hist if self.last_tick - r[0] <= 5.0]
            if len(rh) > 1 and self.last_tick - rh[0][0] > 2:
                rate = sum(r[1] for r in rh[1:]) / (rh[-1][0] - rh[0][0])
                al += f" | {rate:5.0f} samples/s"
                if self.kind == "headset" and rate < 0.9 * S.FS:
                    al += " (LOW: Bluetooth losing data?)"
            self.info.set(f"t {p.n / S.FS:7.1f} s | EEG 8-30 Hz C3 {c3:5.1f} uV  C4 {c4:5.1f} uV | artifacts "
                          f"{100 * p.n_bad / max(1, p.n_out):4.1f} % | d {self.last.d:+.2f}  v {self.last.v:+.2f} | {al}")
        col = {"LEFT": COL["left"], "RIGHT": COL["right"], "FORWARD": COL["good"]}.get(self.cmd_now, COL["dim"])
        label = self.cmd_now
        if self.session is not None:
            label, col = "TEST", COL["dim"]
        elif self.training:
            label, col = "TRAINING", COL["dim"]
        elif self.sig is not None:
            label, col = "CHECK", COL["dim"]
        elif self.stalled:
            label, col = "NO DATA", COL["bad"]
        self.cmd_lab.configure(text=label, fg=col)
        if not self.stalled and self._was_stalled:
            self.status.set("EEG data is arriving again.")
        self._was_stalled = self.stalled
        if self.stalled and self.kind == "headset":
            self.status.set(f"NO EEG DATA for {time.perf_counter() - self.last_data_t:.0f} s - bot stopped. "
                            "Headphones still on and connected?")
        s = f"sent {self.sender.n_sent}" if self.sender.active else "not sending (on-screen bot only)"
        self.send_lab.configure(text=s + (f" | {self.sender.error}" if self.sender.error else ""))

    def _cross(self, c, x, y, L=25):
        c.create_line(x - L, y, x + L, y, fill=COL["fg"], width=3)
        c.create_line(x, y - L, x, y + L, fill=COL["fg"], width=3)

    def _draw_bar(self):
        c, W, H = self.bar, BAR_W, BAR_H
        c.delete("all")
        cx, cy, half = W / 2, H / 2 + 10, W / 2 - 40
        s = self.session
        ph = s.phase if s else None
        cls = s.cls if s else None
        p = self.pipe
        if self.sig is not None:
            frac = self.sig["n"] / (SIG_S * S.FS)
            c.create_text(cx, cy - 20, text="Signal check: sit still, relax, eyes open", fill=COL["warn"], font=("", 15))
            c.create_rectangle(40, cy + 20, 40 + (W - 80) * frac, cy + 32, fill=COL["warn"], outline="")
            return
        if self.training:
            c.create_text(cx, cy, text="Training your model ...", fill=COL["warn"], font=("", 16))
            return
        calm = bool(self.calm_display.get())
        thr = self.thr.get()
        for sgn in (-1, 1):
            x = cx + sgn * thr * half
            c.create_line(x, 40, x, H - 15, fill=COL["thr"], dash=(4, 3))
        c.create_line(cx, 35, cx, H - 10, fill=COL["dim"])
        c.create_text(20, cy, text="L", fill=COL["left"], font=("", 20, "bold"))
        c.create_text(W - 20, cy, text="R", fill=COL["right"], font=("", 20, "bold"))
        hide = s is not None and not s.feedback
        if self.last is not None and not hide:
            v = self.last.v
            x = cx + v * half
            colr = COL["left"] if v < 0 else COL["right"]
            if s is not None and ph == "task" and cls is not None:
                colr = COL["good"] if (v < 0) == (cls == C.LEFT) else COL["bad"]
            c.create_rectangle(min(cx, x), cy - 26, max(cx, x), cy + 26, fill=colr, outline="", tags="bar")
            if not calm:
                dx = cx + float(np.tanh(self.last.d)) * half
                c.create_polygon(dx - 8, cy + 42, dx + 8, cy + 42, dx, cy + 30, fill=COL["fg"])
            self.st["saw_bar"] = True
        if p is not None and p.calib is not None:
            name, left_s = p.calib.block_at(p.n)
            c.create_text(cx, 18, text=f"warm-up {left_s:4.1f} s", fill=COL["warn"], font=("", 12))
        elif s is not None:
            st = s.ui_state()
            c.create_text(70, 18, text=f"trial {st['trial'] + 1}/{st['n_trials']}", fill=COL["dim"])
            if ph in ("fixation", "cue", "task") and (hide or ph == "fixation"):
                self._cross(c, cx, cy)
            show_arrow = cls is not None and (ph == "cue" or (ph == "task" and s.feedback))
            if show_arrow:
                self.st["saw_arrow"] = True
                d = -1 if cls == C.LEFT else 1
                c.create_line(cx, 18, cx + d * 110, 18, fill=COL["calm"], width=8, arrow="last", arrowshape=(20, 24, 10))
        else:
            c.create_text(cx, 18, text="FREE MODE: imagine left or right hand; the bot follows",
                          fill=COL["dim"], font=("", 11))

    def _draw_trace(self):
        c, W, H = self.tr, TR_W, TR_H
        c.delete("all")
        if (self.session is not None and not self.session.feedback) or self.calm_display.get():
            c.create_text(W / 2, H / 2, text="trace hidden (calm display)" if self.calm_display.get() else
                          "hidden during a test without feedback", fill=COL["dim"])
            return
        cy, half = H / 2, H / 2 - 8
        thr = self.thr.get()
        c.create_line(0, cy, W, cy, fill=COL["grid"])
        for sgn in (-1, 1):
            c.create_line(0, cy - sgn * thr * half, W, cy - sgn * thr * half, fill=COL["thr"], dash=(3, 4))
        c.create_text(12, 10, text="R", fill=COL["right"])
        c.create_text(12, H - 10, text="L", fill=COL["left"])
        n = self.trace.maxlen
        tr = list(self.trace)
        if len(tr) < 2:
            return
        x0, dx = W - len(tr) * W / n, W / n
        pd, pv = [], []
        for k, (d, v, bad) in enumerate(tr):
            x = x0 + k * dx
            pd += [x, cy - float(np.tanh(d)) * half]
            pv += [x, cy - v * half]
            if bad:
                c.create_line(x, H - 6, x, H, fill=COL["bad"])
        c.create_line(*pd, fill=COL["dim"])
        c.create_line(*pv, fill=COL["fg"], width=2)

    def _draw_bot(self):
        c, b = self.botc, self.bot
        c.delete("all")
        for gx in range(0, BOT_W, 40):
            c.create_line(gx, 0, gx, BOT_H, fill=COL["grid"])
        for gy in range(0, BOT_H, 40):
            c.create_line(0, gy, BOT_W, gy, fill=COL["grid"])
        pts = list(b.trail)
        for (x1, y1), (x2, y2) in zip(pts[:-1], pts[1:]):
            if abs(x1 - x2) < 20 and abs(y1 - y2) < 20:
                c.create_line(x1, y1, x2, y2, fill=COL["dim"])
        a = np.radians(b.heading)
        tip = (b.x + 16 * np.cos(a), b.y + 16 * np.sin(a))
        lft = (b.x + 10 * np.cos(a + 2.5), b.y + 10 * np.sin(a + 2.5))
        rgt = (b.x + 10 * np.cos(a - 2.5), b.y + 10 * np.sin(a - 2.5))
        col = {"LEFT": COL["left"], "RIGHT": COL["right"], "FORWARD": COL["good"]}.get(self.cmd_now, COL["fg"])
        c.create_polygon(*tip, *lft, *rgt, fill=col, outline=COL["fg"])
        c.create_text(6, 8, anchor="w", text=f"driven {b.distance:5.0f} px, turned {b.turned:5.0f} deg",
                      fill=COL["dim"], font=("", 8))

    def _draw_kappa(self, res):
        c, W, H = self.kc, K_W, K_H
        c.delete("all")
        t = np.array(res["curve_t"])
        x = lambda tt: 30 + (tt - t[0]) / (t[-1] - t[0]) * (W - 40)  # noqa: E731
        y = lambda k: H - 20 - (k + 0.2) / 1.2 * (H - 30)            # noqa: E731
        c.create_line(30, y(0), W - 10, y(0), fill=COL["grid"])
        for kk in (0.5, 1.0):
            c.create_line(30, y(kk), W - 10, y(kk), fill=COL["grid"], dash=(2, 4))
            c.create_text(15, y(kk), text=f"{kk:.1f}", fill=COL["dim"], font=("", 7))
        ch = res.get("max_kappa_chance95")
        if ch is not None:
            c.create_line(30, y(ch), W - 10, y(ch), fill=COL["bad"], dash=(4, 2))
            c.create_text(W - 12, y(ch) - 7, anchor="e", text="chance (max, 95 %)", fill=COL["bad"], font=("", 7))
        c.create_line(x(0), 10, x(0), H - 20, fill=COL["warn"])
        c.create_text(x(0), H - 10, text="cue", fill=COL["warn"], font=("", 7))
        for tt in (1, 2, 3, 4):
            c.create_text(x(tt), H - 10, text=f"{tt} s", fill=COL["dim"], font=("", 7))
        for key, col, w in (("kappa_raw", COL["dim"], 1), ("kappa_smoothed", COL["fg"], 2)):
            pts = []
            for tt, kk in zip(t, res[key]):
                pts += [x(tt), y(kk)]
            c.create_line(*pts, fill=col, width=w)

    # ================================================================== self-tests / close
    def _write_replay_selftest(self):
        r = self.last_results or {}
        (S.OUT_DIR / "selftest_replay.json").write_text(json.dumps(dict(
            subject=self.args.sub, session=self.args.session, model=self.pipe.model.name,
            result={k: v for k, v in r.items() if not k.startswith(("curve", "kappa_"))},
            saw_bar=self.st["saw_bar"], saw_arrow=self.st["saw_arrow"],
            wall_seconds=round(time.time() - self.st["t0"], 1)), indent=1, default=float))
        self.root.after(200, self.close)

    def _selftest(self):
        st, p = self.st, self.pipe
        if p is None:
            return self.root.after(200, self._selftest)
        stage = st["stage"]
        if stage == 0:
            self.start_signal_check()
            st["stage"] = 1
        elif stage == 1 and self.sig is None and self.sig_result is not None:
            self.cal_blocks.set(2)
            self.cal_trials.set(self.args.st_trials)
            self.start_calibration()
            st["stage"] = 2
        elif stage == 2 and self.calm is not None:
            c = self.calm["c"]
            if self.calm["state"] in ("intro", "break") and self.session is None and c.winfo_width() > 200 \
                    and c.find_all():
                st.setdefault("calm_states", []).append(self.calm["state"])
                st["calm_canvas_items"] = len(self.calm["c"].find_all())
                self._calm_next()
        elif stage == 2 and self.calm is None and not self.training and self.train_rep is not None:
            self.n_trials.set(self.args.st_trials)
            self.start_test()
            st["stage"] = 3
        elif stage == 3 and self.calm is not None:
            c = self.calm["c"]
            if self.calm["state"] == "intro" and self.session is None and c.winfo_width() > 200 and c.find_all():
                st["test_on_calm_screen"] = True
                st["calm_text_bbox"] = self.calm["c"].bbox("all")
                st["calm_size"] = (self.calm["c"].winfo_width(), self.calm["c"].winfo_height())
                self._calm_next()
        elif stage == 3 and self.calm is None and self.session is None and self.last_results is not None:
            st["stage"] = 4
            st["free_t"] = p.n
            self.sim_key = C.RIGHT
        elif stage == 4:
            el = (p.n - st["free_t"]) / S.FS
            if el > 6 and "cmd_right" not in st:
                st["cmd_right"] = self.cmd_now
                self.sim_key = C.LEFT
            elif el > 12:
                st["cmd_left"] = self.cmd_now
                rep = self.train_rep
                out = dict(signal_check=self.sig_result,
                           personal_model=dict(verdict=rep.get("verdict"), accuracy=rep.get("accuracy"),
                                               chosen=rep.get("chosen"), runs=rep.get("runs"),
                                               candidates={k: round(v["accuracy"], 3) for k, v in rep["candidates"].items()}),
                           model_in_use=p.model.name,
                           test={k: v for k, v in self.last_results.items() if not k.startswith(("curve", "kappa_"))},
                           calm_states=st.get("calm_states"), calm_canvas_items=st.get("calm_canvas_items"),
                           test_on_calm_screen=st.get("test_on_calm_screen"), calm_text_bbox=st.get("calm_text_bbox"),
                           calm_size=st.get("calm_size"),
                           saw_arrow=st["saw_arrow"], saw_bar=st["saw_bar"], free_mode_right=st["cmd_right"],
                           free_mode_left=st["cmd_left"], bot_distance=self.bot.distance, bot_turned=self.bot.turned,
                           wall_seconds=round(time.time() - st["t0"], 1), sim_skill=self.args.skill)
                (S.OUT_DIR / "selftest.json").write_text(json.dumps(out, indent=2, default=float))
                return self.close()
        self.root.after(200, self._selftest)

    def close(self):
        try:
            if self.calm is not None:
                self._calm_abort()
            if self.session is not None and self.kind != "replay2b":
                self._finish_session(stopped=True)
            self.sender.close()
            if isinstance(self.source, HeadphonesSource):
                self.source.disconnect()
            if self.sound is not None:
                self.sound.close()
        finally:
            self.root.destroy()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["headset", "sim", "replay2b"], default="headset")
    ap.add_argument("--subject", default="Pratham")
    ap.add_argument("--sub", type=int, default=4, help="2b subject for --source replay2b")
    ap.add_argument("--session", type=int, default=4, help="2b session 1-5 (4, 5 = competition evaluation)")
    ap.add_argument("--speed", type=float, default=1.0, help="replay / simulator speed (1 = real time)")
    ap.add_argument("--skill", type=float, default=0.6, help="simulator: how strong the imagery effect is")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--st-trials", type=int, default=8)
    args = ap.parse_args()
    if args.source == "sim" and args.subject == "Pratham":
        args.subject = "SIM"
    S.OUT_DIR.mkdir(exist_ok=True)
    root = tk.Tk()
    App(root, args)
    root.mainloop()


if __name__ == "__main__":
    main()
