"""MI-BCI app: record cued left/right motor imagery, check it, train a decoder, then move a smiley
with your imagery in real time (the Graz BCI IV 2b design, on our LEHeadPhones2 headset).

    python app.py                  normal use
    python app.py --simulate       no headset: simulated EEG (pick 'Simulator' on tab 1)
    python app.py --selftest       drives the whole app on the simulator, then exits (0 = pass)

Tabs: 1 Connect  2 Record  3 Check & Train  4 Feedback  5 Log.  Esc stops a running run.
"""
import argparse
import json
import queue
import sys
import threading
import time
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mibci import config as C                                              # noqa: E402
from mibci.analysis import alpha_check, erd_check, signal_quality          # noqa: E402
from mibci.decoder import Decoder, load_decoder                            # noqa: E402
from mibci.svm_trainer import BASE_JSON, evaluate_on_run, session_reference, train_svm  # noqa: E402
from mibci.engine import Engine                                            # noqa: E402
from mibci.paradigm import BaselineParadigm, Paradigm, make_schedule       # noqa: E402
from mibci.recorder import Recorder, list_runs, load_run                   # noqa: E402
from mibci.sources import HeadphonesSource, ReplaySource, SimulatedSource  # noqa: E402
from mibci.trainer import should_switch, train                             # noqa: E402

from mibci.sound import Sound, list_outputs                                # noqa: E402

BG, FG, GREY, GREEN, RED = "#101418", "#e8e8e8", "#9aa0a6", "#3fb950", "#f85149"


class App:
    def __init__(self, root, args):
        self.root, self.args = root, args
        self.source = None
        self.engine = None
        self.running = False
        self.jobs = queue.Queue()
        self.data_root = Path(args.root) if args.root else C.DATA_DIR
        root.title("MI-BCI  (left/right motor imagery)")
        root.geometry("1100x760")
        root.bind("<Escape>", lambda e: self.stop_run("stopped by Esc"))
        self.subject = tk.StringVar(value=args.subject)
        self.src_kind = tk.StringVar(value="simulator" if args.simulate or args.selftest else "headphones")
        self.skill = tk.DoubleVar(value=0.5)
        self.speed = tk.DoubleVar(value=args.speed)
        self.status = tk.StringVar(value="Not connected")
        self.decoder_path = tk.StringVar(value="")

        top = ttk.Frame(root)
        top.pack(fill="x", padx=8, pady=4)
        ttk.Label(top, text="Subject:").pack(side="left")
        ttk.Entry(top, textvariable=self.subject, width=12).pack(side="left", padx=4)
        ttk.Label(top, textvariable=self.status).pack(side="left", padx=16)

        self.nb = ttk.Notebook(root)
        self.nb.pack(fill="both", expand=True, padx=8, pady=4)
        self.tab_connect = ttk.Frame(self.nb)
        self.tab_record = ttk.Frame(self.nb)
        self.tab_train = ttk.Frame(self.nb)
        self.tab_fb = ttk.Frame(self.nb)
        self.tab_log = ttk.Frame(self.nb)
        for t, name in ((self.tab_connect, "1 Connect"), (self.tab_record, "2 Record"),
                        (self.tab_train, "3 Check & Train"), (self.tab_fb, "4 Feedback"), (self.tab_log, "5 Log")):
            self.nb.add(t, text=name)
        self.canvas = tk.Canvas(root, bg=BG, highlightthickness=0)     # stimulus screen (shown during runs)
        self._build_connect()
        self._build_record()
        self._build_train()
        self._build_feedback()
        self.sound = Sound(muted=args.selftest)
        self.sound_dev.set(self.sound.device or f"(no audio device: {self.sound.error})")
        root.protocol("WM_DELETE_WINDOW", lambda: (self.sound.close(), root.destroy()))
        self.logbox = tk.Text(self.tab_log, height=30, wrap="word")
        self.logbox.pack(fill="both", expand=True)
        self._refresh_decoder()
        # a different subject code = that subject's own model and runs (never another person's)
        self.subject.trace_add("write", lambda *_: self.root.after(300, self._subject_changed))
        self.root.after(200, self._poll_jobs)
        self.root.after(500, self._poll_status)

    def _subject_changed(self):
        self._refresh_decoder()
        if hasattr(self, "run_list"):
            self.refresh_runs()

    # ---------------------------------------------------------------- helpers
    def log(self, msg):
        line = time.strftime("%H:%M:%S ") + str(msg)
        self.logbox.insert("end", line + "\n")
        self.logbox.see("end")
        print(line, flush=True)

    def in_thread(self, fn, done=None):
        def run():
            try:
                res = fn()
                self.jobs.put((done, res, None))
            except Exception as e:                       # report, never crash the window
                self.jobs.put((done, None, traceback.format_exc()))
        threading.Thread(target=run, daemon=True).start()

    def _poll_jobs(self):
        while not self.jobs.empty():
            done, res, err = self.jobs.get()
            if err:
                self.log("ERROR\n" + err)
                if not self.args.selftest:
                    messagebox.showerror("Error", err.strip().splitlines()[-1])
                self.selftest_failed = err
            elif done:
                done(res)
        self.root.after(200, self._poll_jobs)

    def _poll_status(self):
        if self.source is not None and not self.running:
            st = self.source.status()
            res = st.get("resistance") or {}
            txt = []
            for ch in C.CHANNELS:
                v = res.get(ch)
                if v is None:
                    continue
                k = v / 1e3
                q = "good" if k < 500 else ("fair" if k <= 1000 else "BAD")
                txt.append(f"{ch} {k:.0f} kOhm ({q})")
            self.resist_lbl.config(text="   ".join(txt) or "no resistance data")
            if st.get("battery") is not None:
                self.status.set(f"Connected: {self.source.name}, battery {st['battery']}%")
        self.root.after(500, self._poll_status)

    def _make_source(self):
        k = self.src_kind.get()
        if k == "simulator":
            return SimulatedSource(skill=self.skill.get(), seed=int(time.time()) % 10000,
                                   speed=self.speed.get(), realtime=True)
        if k == "replay":
            p = filedialog.askdirectory(title="Pick a recorded run folder", initialdir=self.data_root)
            if not p:
                return None
            return ReplaySource(load_run(p)["eeg"], realtime=True, speed=self.speed.get())
        return self.source if isinstance(self.source, HeadphonesSource) and self.source.sensor else None

    # ---------------------------------------------------------------- tab 1
    def _build_connect(self):
        f = self.tab_connect
        ttk.Label(f, text="Signal source", font=("", 11, "bold")).grid(row=0, column=0, sticky="w", pady=6)
        for i, (k, label) in enumerate((("headphones", "Headphones (LEHeadPhones2, Bluetooth)"),
                                        ("simulator", "Simulator (no headset)"),
                                        ("replay", "Replay a recorded run"))):
            ttk.Radiobutton(f, text=label, value=k, variable=self.src_kind).grid(row=1 + i, column=0, sticky="w")
        ttk.Label(f, text="Simulator skill (0 = no signal, 1 = perfect)").grid(row=4, column=0, sticky="w", pady=(10, 0))
        ttk.Scale(f, from_=0, to=1, variable=self.skill, length=240).grid(row=5, column=0, sticky="w")
        ttk.Label(f, text="Speed (x real time; simulator/replay only)").grid(row=6, column=0, sticky="w", pady=(10, 0))
        ttk.Spinbox(f, from_=1, to=50, textvariable=self.speed, width=6).grid(row=7, column=0, sticky="w")
        ttk.Separator(f).grid(row=8, column=0, columnspan=3, sticky="ew", pady=10)
        ttk.Button(f, text="Scan for headphones (8 s)", command=self.scan).grid(row=9, column=0, sticky="w")
        self.dev_list = tk.Listbox(f, height=4, width=50)
        self.dev_list.grid(row=10, column=0, sticky="w", pady=4)
        ttk.Button(f, text="Connect selected", command=self.connect).grid(row=11, column=0, sticky="w")
        ttk.Button(f, text="Use simulator", command=self.use_sim).grid(row=12, column=0, sticky="w", pady=4)
        ttk.Button(f, text="10 s signal test (do this before recording)", command=self.signal_test).grid(
            row=12, column=1, sticky="w", pady=4)
        snd = ttk.Frame(f)
        snd.grid(row=11, column=1, sticky="w")
        ttk.Button(snd, text="Test beep", command=lambda: self.sound.play("beep")).pack(side="left")
        ttk.Label(snd, text="  sound out:").pack(side="left")
        self.sound_dev = tk.StringVar(value="")
        try:
            names = [n for _, n in list_outputs()]
        except Exception:
            names = []
        cb = ttk.Combobox(snd, textvariable=self.sound_dev, values=names, width=34, state="readonly")
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self._set_sound(self.sound_dev.get()))
        self.quality_lbl = ttk.Label(f, text="", font=("Consolas", 10))
        self.quality_lbl.grid(row=15, column=0, columnspan=3, sticky="w", pady=8)
        self.resist_lbl = ttk.Label(f, text="", font=("Consolas", 10))
        self.resist_lbl.grid(row=13, column=0, columnspan=3, sticky="w", pady=8)
        ttk.Label(f, text="Aim for every electrode good (< 500 kOhm) or fair (<= 1 MOhm) before recording.\n"
                          "Wet the pads with saline, sit still, hands resting on the table.",
                  foreground="#555").grid(row=14, column=0, columnspan=3, sticky="w")
        self.devices = []

    def scan(self):
        self.src_kind.set("headphones")
        hp = HeadphonesSource()
        self.log("Scanning for LEHeadPhones2 ...")

        def done(devs):
            self.source = hp
            self.devices = devs
            self.dev_list.delete(0, "end")
            for d in devs:
                self.dev_list.insert("end", f"{d['name']}  serial {d['serial']}")
            self.log(f"found {len(devs)} device(s)")
        self.in_thread(lambda: hp.scan(8), done)

    def connect(self):
        sel = self.dev_list.curselection()
        if not sel:
            messagebox.showinfo("Connect", "Scan and pick a device first.")
            return
        info = self.devices[sel[0]]["info"]

        def go():
            for attempt in range(3):
                try:
                    self.source.connect(info)
                    self.source.start_resistance()
                    return attempt + 1
                except Exception:
                    time.sleep((2, 5, 10)[attempt])
            raise RuntimeError("connection failed after 3 attempts")
        self.in_thread(go, lambda n: (self.log(f"connected (attempt {n})"), self.status.set("Connected: headphones")))

    def _set_sound(self, name):
        try:
            self.sound.open(name)
            self.log(f"sound output: {self.sound.device}")
            if any(w.lower() in name.lower() for w in ("USAMS", "YX05")):
                messagebox.showwarning("Sound on the EEG headset",
                                       "This is the EEG headset itself. Beeps over its Bluetooth link can be lost, "
                                       "and audio in the same device as the electrodes can disturb the EEG. "
                                       "The laptop speakers are better.")
            self.sound.play("beep")
        except Exception as e:
            messagebox.showerror("Sound", str(e))

    def signal_test(self):
        src = self._make_source()
        if src is None:
            return messagebox.showinfo("Signal test", "Connect the headphones or choose the simulator first.")
        self.source = src
        self.quality_lbl.config(text="Recording 13 s (first 3 s are ignored while the amplifier settles) ... "
                                     "sit still, eyes open, jaw relaxed.")
        settle, total = 3.0, 13.0

        def go():
            import numpy as np
            src.start()
            chunks, t0 = [], time.time()
            while time.time() - t0 < total:
                chunks.append(src.read())
                time.sleep(0.05)
            src.stop()
            if isinstance(src, HeadphonesSource):
                src.start_resistance()
            x = np.vstack([c for c in chunks if len(c)]) if any(len(c) for c in chunks) else np.zeros((0, 4))
            # keep the raw test so it can be inspected later
            out = self.data_root / self.subject.get() / "signal_tests"
            out.mkdir(parents=True, exist_ok=True)
            f = out / f"signal_test_{time.strftime('%Y-%m-%d_%H%M%S')}.csv"
            np.savetxt(f, np.hstack([np.arange(len(x))[:, None], x]), delimiter=",", fmt=["%d"] + ["%.3f"] * 4,
                       header="sample," + ",".join(C.CHANNELS), comments="")
            q = signal_quality(x, skip_s=settle)
            q_all = signal_quality(x, skip_s=0.0)
            q["first_3s_included_eeg_uV"] = q_all.get("eeg_1_40Hz_uV")
            q["samples_received"] = len(x)
            q["rate_hz"] = round(len(x) / total, 1)
            q["saved"] = str(f)
            return q

        def done(q):
            self.last_quality = q
            lines = [q.get("verdict", q.get("error", ""))]
            for k in ("eeg_1_40Hz_uV", "mains_50Hz_uV", "first_3s_included_eeg_uV", "rate_hz", "saved"):
                if k in q:
                    lines.append(f"{k}: {q[k]}")
            self.quality_lbl.config(text="\n".join(lines))
            self.log(f"signal test: {q}")
        self.in_thread(go, done)

    def use_sim(self):
        self.src_kind.set("simulator")
        self.source = SimulatedSource(skill=self.skill.get(), realtime=True)
        self.status.set("Simulator")
        self.log("using the simulator")

    # ---------------------------------------------------------------- tab 2
    def _build_record(self):
        f = self.tab_record
        self.rec_type = tk.StringVar(value="baseline")
        self.rec_trials = tk.IntVar(value=10)
        ttk.Label(f, text="Recording runs (no feedback)", font=("", 11, "bold")).grid(row=0, column=0, sticky="w", pady=6)
        for i, (k, label) in enumerate((
                ("baseline", "Baseline: eyes open 60 s, eyes closed 60 s, blinks 30 s, jaw 30 s (start of every session)"),
                ("movement", "Movement check: really SQUEEZE the cued hand (first visit; milestone M0)"),
                ("screening", "Screening: IMAGINE squeezing the cued hand, keep still (Graz sessions 1-2)"))):
            ttk.Radiobutton(f, text=label, value=k, variable=self.rec_type).grid(row=1 + i, column=0, sticky="w")
        ttk.Label(f, text="Trials per hand in this run").grid(row=4, column=0, sticky="w", pady=(10, 0))
        ttk.Spinbox(f, from_=2, to=40, textvariable=self.rec_trials, width=6).grid(row=5, column=0, sticky="w")
        ttk.Button(f, text="Start run", command=self.start_record).grid(row=6, column=0, sticky="w", pady=10)
        ttk.Label(f, text="Trial: cross + beep at 0 s, arrow at 3 s for 1.25 s, keep going until 7 s, rest 1.5-2.5 s.\n"
                          "Left and right are mixed at random. About 3.5 min per run of 10 + 10 trials.",
                  foreground="#555").grid(row=7, column=0, sticky="w")
        self.rec_result = ttk.Label(f, text="", font=("Consolas", 10))
        self.rec_result.grid(row=8, column=0, sticky="w", pady=8)

    def start_record(self):
        self.start_run(self.rec_type.get(), self.rec_trials.get(), None, self.rec_result)

    # ---------------------------------------------------------------- tab 3
    def _build_train(self):
        f = self.tab_train
        ttk.Label(f, text="Recorded runs for this subject (select with Ctrl/Shift)", font=("", 11, "bold")).pack(anchor="w")
        self.run_list = tk.Listbox(f, height=10, selectmode="extended", font=("Consolas", 10))
        self.run_list.pack(fill="x", pady=4)
        b = ttk.Frame(f)
        b.pack(anchor="w")
        ttk.Button(b, text="Refresh list", command=self.refresh_runs).pack(side="left")
        ttk.Button(b, text="Alpha check (baseline run)", command=self.do_alpha).pack(side="left", padx=4)
        ttk.Button(b, text="ERD check - M0 (movement/screening runs)", command=self.do_erd).pack(side="left", padx=4)
        ttk.Button(b, text="Train decoder (screening/feedback runs)", command=self.do_train).pack(side="left", padx=4)
        self.train_out = tk.Text(f, height=22, font=("Consolas", 9))
        self.train_out.pack(fill="both", expand=True, pady=4)
        self.runs = []

    def refresh_runs(self):
        self.runs = list_runs(self.subject.get(), None, self.data_root)
        self.run_list.delete(0, "end")
        for r in self.runs:
            m = json.loads((r / "run.json").read_text())
            s = m.get("summary") or {}
            acc = s.get("accuracy")
            self.run_list.insert("end", f"{r.name:40s} {m.get('run_type', ''):10s} "
                                        f"{'' if acc is None else f'online acc {acc:.2f}'}")

    def _selected(self, types):
        sel = [self.runs[i] for i in self.run_list.curselection()] if self.runs else []
        if not sel:
            sel = [r for r in self.runs if json.loads((r / "run.json").read_text()).get("run_type") in types]
        return sel

    def _show(self, title, res):
        self.train_out.delete("1.0", "end")
        head = [title, "=" * len(title)]
        if "verdict" in res and "score_text" in res:                   # training report
            head += [f"SCORE:   {res['score_text']}", f"VERDICT: {res['verdict']}",
                     f"Trained on {len(res.get('runs', []))} run(s), {res.get('trials')} trials. "
                     f"Features: {', '.join(res.get('features', []))}"]
            for r in res.get("per_run", []):
                head.append(f"   held-out run {r['run']}: {r['accuracy']:.0%} of {r['trials']} trials")
        if "summary" in res:                                          # ERD check
            head += res["summary"] + ["", res.get("how_to_read", "")]
        self.train_out.insert("end", "\n".join(head) + "\n\nDetails:\n" + json.dumps(res, indent=2, default=float))
        self.log(title + ": " + " | ".join(head[2:5]))

    def do_alpha(self):
        self.refresh_runs()
        runs = self._selected(("baseline",))
        if not runs:
            return messagebox.showinfo("Alpha", "Record a baseline run first.")
        self.in_thread(lambda: alpha_check(runs[-1]), lambda r: self._show(f"Alpha check on {runs[-1].name}", r))

    def do_erd(self):
        self.refresh_runs()
        runs = self._selected(("movement", "screening"))
        if not runs:
            return messagebox.showinfo("ERD", "Record movement or screening runs first.")
        self.in_thread(lambda: erd_check([str(r) for r in runs]),
                       lambda r: self._show(f"ERD check on {len(runs)} run(s) (passes = contralateral ERD, p < 0.05)", r))

    def do_train(self, done_extra=None):
        self.refresh_runs()
        runs = self._selected(("screening", "feedback"))
        if not runs:
            return messagebox.showinfo("Train", "Record screening runs first (at least 2).")
        self.train_out.delete("1.0", "end")
        self.train_out.insert("end", f"Training the SVM on 2b + {len(runs)} of your run(s): testing 3 weightings, "
                                     f"each run held out once. Takes about a minute...\n" if C.MODEL == "svm" else
                              f"Training on {len(runs)} run(s)... (nested selection + permutation test)\n")
        out_dir = self.data_root / self.subject.get() / "decoders"
        n_perm = 30 if self.args.selftest else 200

        def done(res):
            dec, rep = res
            self._refresh_decoder()
            self._show("Training report", rep)
            if done_extra:
                done_extra(rep)
        if C.MODEL == "svm":
            self.in_thread(lambda: train_svm(runs, self.subject.get(), out_dir=out_dir), done)
        else:
            self.in_thread(lambda: train(runs, self.subject.get(), out_dir=out_dir, n_perm=n_perm), done)

    # ---------------------------------------------------------------- tab 4
    def _build_feedback(self):
        f = self.tab_fb
        self.fb_trials = tk.IntVar(value=20)
        ttk.Label(f, text="Smiley feedback (Graz sessions 3-5)  -  model: " +
                  ("CSP + SVM + Euclidean Alignment (2b base, improved with your runs)" if C.MODEL == "svm"
                   else "Graz LDA"), font=("", 11, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=6)
        ttk.Label(f, text="Decoder:").grid(row=1, column=0, sticky="w")
        ttk.Label(f, textvariable=self.decoder_path, font=("Consolas", 9)).grid(row=2, column=0, sticky="w")
        self.dec_score = ttk.Label(f, text="", font=("", 10, "bold"))
        self.dec_score.grid(row=2, column=1, sticky="w", padx=12)
        ttk.Button(f, text="Choose another decoder...", command=self.pick_decoder).grid(row=3, column=0, sticky="w", pady=4)
        ttk.Label(f, text="Trials per hand in this run").grid(row=4, column=0, sticky="w", pady=(10, 0))
        ttk.Spinbox(f, from_=2, to=40, textvariable=self.fb_trials, width=6).grid(row=5, column=0, sticky="w")
        ttk.Button(f, text="Start feedback run", command=self.start_feedback).grid(row=6, column=0, sticky="w", pady=10)
        ttk.Button(f, text="Retrain on all runs (switch only if >= 5 points better)",
                   command=self.retrain_rule).grid(row=7, column=0, sticky="w")
        ttk.Label(f, text="Grey smiley at 0 s, beep at 2 s, arrow + live feedback 3-7.5 s.\n"
                          "Keep the smiley on the arrow's side as long as you can. Green = right side, red = wrong side.",
                  foreground="#555").grid(row=8, column=0, sticky="w", pady=6)
        self.fb_result = ttk.Label(f, text="", font=("Consolas", 10))
        self.fb_result.grid(row=9, column=0, sticky="w", pady=8)

    def _refresh_decoder(self):
        p = self.data_root / self.subject.get() / "decoders" / "current.json"
        if not p.exists() and C.MODEL == "svm" and BASE_JSON.exists():
            p = BASE_JSON                                  # nothing trained yet: the 2b base SVM
        if not p.exists():
            self.decoder_path.set("(none yet: train one on tab 3)")
            return
        self.decoder_path.set(str(p))
        try:
            m = load_decoder(p).meta
            s = m.get("score")
            txt = f"Score: {'no score' if s is None else f'{s:.0%} on held-out runs'}  -  {m.get('verdict', 'unknown')}"
        except Exception:
            txt = ""
        if hasattr(self, "dec_score"):
            self.dec_score.config(text=txt)

    def pick_decoder(self):
        p = filedialog.askopenfilename(initialdir=self.data_root, filetypes=[("decoder", "*.json")])
        if p:
            self.decoder_path.set(p)

    def start_feedback(self):
        p = Path(self.decoder_path.get())
        if not p.exists():
            return messagebox.showinfo("Feedback", "Train a decoder first (tab 3).")
        dec = load_decoder(p)
        if getattr(dec, "kind", "") == "csp_svm_ea":          # align to today's session, no labels needed
            R = session_reference(self.subject.get(), root=self.data_root)
            dec.set_reference(R)
            self.log("SVM alignment: " + ("today's recordings" if R is not None else
                                           "none recorded today yet - uses the running mean of this run"))
        verdict = dec.meta.get("verdict", "")
        if not verdict.startswith("READY") and not self.args.selftest:
            if not messagebox.askyesno("Decoder not ready",
                                       f"This decoder's check says:\n\n{verdict or 'no score'}\n\n"
                                       "Feedback with it will probably look random (about 50%).\n"
                                       "Record more screening runs and train again first?\n\n"
                                       "Yes = go back.   No = run feedback anyway."):
                pass
            else:
                return
        self.start_run("feedback", self.fb_trials.get(), dec, self.fb_result)

    def retrain_rule(self):
        """Graz: retrain on everything except the latest feedback run, compare on that run."""
        self.refresh_runs()
        fb = [r for r in self.runs if json.loads((r / "run.json").read_text()).get("run_type") == "feedback"]
        cur = Path(self.decoder_path.get())
        if not fb or not cur.exists():
            return messagebox.showinfo("Retrain", "Needs a current decoder and at least one feedback run.")
        latest = fb[-1]
        train_runs = [r for r in self.runs if r != latest and
                      json.loads((r / "run.json").read_text()).get("run_type") in ("screening", "feedback")]
        out_dir = self.data_root / self.subject.get() / "decoders" / "candidates"

        def go():
            if C.MODEL == "svm":
                new, rep = train_svm(train_runs, self.subject.get(), out_dir=out_dir)
                a_new = evaluate_on_run(new, latest)[0]
                a_old = evaluate_on_run(load_decoder(cur), latest)[0]
                switch = bool(a_new >= a_old + 0.05)
                if switch:
                    new.save(self.data_root / self.subject.get() / "decoders" / "current.json")
                return dict(compared_on=latest.name, new_accuracy=a_new, current_accuracy=a_old, switched=switch)
            new, rep = train(train_runs, self.subject.get(), out_dir=out_dir, n_perm=0)
            switch, a_new, a_old = should_switch(new, Decoder.load(cur), latest)
            if switch:
                new.save(self.data_root / self.subject.get() / "decoders" / "current.json")
            return dict(compared_on=latest.name, new_accuracy=a_new, current_accuracy=a_old, switched=switch)
        self.in_thread(go, lambda r: (self._refresh_decoder(), self._show("Retrain (Graz >= 5 point rule)", r)))

    # ---------------------------------------------------------------- runs + stimulus screen
    def start_run(self, run_type, n_per_class, decoder, result_label):
        if self.running:
            return
        src = self._make_source()
        if src is None:
            return messagebox.showinfo("Run", "Connect the headphones (or choose the simulator) on tab 1 first.")
        self.source = src
        if run_type == "baseline":
            par = BaselineParadigm(scale=self.args.baseline_scale)
        else:
            par = Paradigm(run_type, make_schedule(n_per_class))
        rec = Recorder(self.subject.get(), run_type, root=self.data_root,
                       meta=dict(app="mi_bci", source=src.name))
        self.engine = Engine(src, par, decoder, rec, on_event=self._on_event)
        self.result_label = result_label
        self.running = True
        self.nb.pack_forget()
        self.canvas.pack(fill="both", expand=True)
        self.log(f"run started: {run_type}, {n_per_class} per hand, folder {rec.dir}")
        try:
            src.start()
        except Exception as e:
            self.stop_run(f"could not start the stream: {e}")
            return
        self._last_draw = 0
        if not self.args.selftest:
            self.sound.start_keepalive()
        self.root.after(10, self._tick)

    def _on_event(self, s, name, cls):
        if name == "beep" or name.endswith("_start") and name not in ("trial_start", "run_start", "feedback_start"):
            self.sound.play("beep", self.root)
        elif name.endswith("_end") and name not in ("run_end", "task_end"):
            self.sound.play("high", self.root)

    def _tick(self):
        if not self.running:
            return
        try:
            more = self.engine.pump()
        except Exception:
            self.log("ERROR in run\n" + traceback.format_exc())
            self.stop_run("error")
            return
        now = time.perf_counter()
        if now - self._last_draw >= 0.04:                 # redraw at 25 Hz, as Graz did
            st = self.engine.state()
            self._draw(st)
            self._last_draw = now
            if self.args.selftest:
                self._check_drawing(st)
        if not more:
            self.stop_run("finished")
            return
        self.root.after(10, self._tick)

    def stop_run(self, why):
        if not self.running:
            return
        self.running = False
        self.sound.stop()
        try:
            self.source.stop()
        except Exception:
            pass
        summ = self.engine.finish(dict(stopped=why))
        try:                                           # mains hum check on the last 30 s of this run
            x = load_run(self.engine.rec.dir)["eeg"]
            if len(x) > 15 * C.FS:
                q = signal_quality(x[-30 * C.FS:])
                hum = [q["mains_50Hz_uV"][k] / max(q["eeg_1_40Hz_uV"][k], 1e-6) for k in ("C3-A1", "C4-A2")
                       if k in q.get("mains_50Hz_uV", {})]
                summ["eeg_uV"], summ["mains_uV"] = q.get("eeg_1_40Hz_uV"), q.get("mains_50Hz_uV")
                # 50 Hz itself is filtered out of the decoder's bands (<= 30 Hz); this flags the much stronger
                # pickup seen when the charger is in / hands touch the laptop (P01, 2026-10-26: ~10-18x)
                if hum and max(hum) > 8:
                    summ["warning"] = ("Strong 50 Hz mains hum in this run. Unplug the laptop charger, keep hands "
                                       "off the laptop and away from cables, then continue.")
        except Exception as e:
            self.log(f"quality check after run failed: {e}")
        self.canvas.pack_forget()
        self.nb.pack(fill="both", expand=True, padx=8, pady=4)
        self.log(f"run {why}: {summ}")
        txt = f"Last run: {why}. "
        if summ.get("accuracy") is not None:
            txt += f"Online accuracy {summ['accuracy']:.0%} over {summ['trials_scored']} trials, " \
                   f"integrated error {summ['integrated_error']:.0%}. "
        txt += f"Artifact outputs {summ['artifact_outputs']}/{summ['outputs']}. Samples {summ['samples']}."
        if summ.get("effective_rate_hz") and self.source.name == "headphones":
            txt += f" Stream rate {summ['effective_rate_hz']:.1f} Hz (should be ~250)."
        if summ.get("warning"):
            txt += "\nWARNING: " + summ["warning"]
            if not self.args.selftest:
                messagebox.showwarning("Mains hum", summ["warning"])
        self.result_label.config(text=txt)
        if isinstance(self.source, HeadphonesSource):
            try:
                self.source.start_resistance()
            except Exception:
                pass
        self.last_summary = summ
        self.refresh_runs()

    def _draw(self, st):
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width() or 1100, c.winfo_height() or 700
        cx, cy = w // 2, h // 2
        ph, rt = st["phase"], st["run_type"]
        c.create_text(12, 12, anchor="nw", fill=GREY, font=("", 10),
                      text=f"{rt}  trial {max(st['trial'], 0) + 1}/{st['n_trials']}   Esc = stop")
        if rt == "baseline":
            c.create_text(cx, cy - 120, text=st.get("text", ""), fill=FG, font=("", 22))
            if ph != "eyes_closed":
                self._cross(cx, cy)
            return
        if ph in ("wait", "rest", "done"):
            return
        if rt == "feedback":
            self._smiley(c, st, cx, cy, w)
            return
        self._cross(cx, cy)
        if ph == "cue":
            self._arrow(cx, cy, st["cls"])
        if rt == "movement" and ph in ("cue", "task"):
            c.create_text(cx, cy + 150, text="squeeze", fill=GREY, font=("", 16))

    def _check_drawing(self, st):
        """Self-test only: read back what was drawn on the canvas (no screen capture) and check it
        matches the state: arrow points to the cued side; smiley on the decoded side, green when that
        is the cued side, red otherwise; grey and centred before feedback."""
        c = self.canvas
        w = c.winfo_width() or 1100
        cx = w // 2
        checks = getattr(self, "draw_checks", {})
        want = -1 if st["cls"] == C.LEFT else 1
        arrows = [i for i in c.find_all() if c.type(i) == "line" and c.itemcget(i, "arrow") == "last"]
        if st["run_type"] in ("screening", "movement") and st["phase"] == "cue":
            x0, _, x1, _ = c.coords(arrows[0]) if arrows else (0, 0, 0, 0)
            checks.setdefault("cue_arrow_points_to_cued_side", []).append(bool(arrows) and (x1 - x0) * want > 0)
        if st["run_type"] == "feedback" and st["phase"] not in ("wait", "rest", "done"):
            ovals = [i for i in c.find_all() if c.type(i) == "oval"]
            face = max(ovals, key=lambda i: (lambda b: b[2] - b[0])(c.coords(i)))
            x0, _, x1, _ = c.coords(face)
            fx, col = (x0 + x1) / 2, c.itemcget(face, "fill")
            v = st["integrated"]
            if not st["feedback_active"]:
                checks.setdefault("smiley_grey_and_centred_before_feedback", []).append(col == GREY and abs(fx - cx) < 2)
            elif abs(v) > 0.2:
                side_ok = (fx - cx) * v > 0
                colour_ok = col == (GREEN if v * want > 0 else RED)
                checks.setdefault("smiley_moves_to_decoded_side", []).append(side_ok)
                checks.setdefault("smiley_green_if_correct_red_if_wrong", []).append(colour_ok)
                checks.setdefault("feedback_shows_cue_arrow", []).append(bool(arrows))
        self.draw_checks = checks

    def _cross(self, cx, cy, s=40):
        self.canvas.create_line(cx - s, cy, cx + s, cy, fill=FG, width=4)
        self.canvas.create_line(cx, cy - s, cx, cy + s, fill=FG, width=4)

    def _arrow(self, cx, cy, cls, y_off=0):
        d = -1 if cls == C.LEFT else 1
        self.canvas.create_line(cx, cy + y_off, cx + d * 160, cy + y_off, fill="#f2cc60", width=14, arrow="last",
                                arrowshape=(36, 44, 18))

    def _smiley(self, c, st, cx, cy, w):
        active = st["feedback_active"]
        v = st["integrated"] if active else 0.0
        x = cx + v * (w * 0.38)
        r = 70
        want = -1 if st["cls"] == C.LEFT else 1
        good = (v * want) > 0
        col = GREY if not active else (GREEN if good else RED)
        c.create_oval(x - r, cy - r, x + r, cy + r, fill=col, outline="")
        c.create_oval(x - 28, cy - 25, x - 14, cy - 11, fill=BG, outline="")
        c.create_oval(x + 14, cy - 25, x + 28, cy - 11, fill=BG, outline="")
        bend = (1 if good else -1) * abs(v) * 28 if active else 0      # happy or sad, by how far
        c.create_line(x - 34, cy + 28, x, cy + 28 + bend, x + 34, cy + 28, smooth=True, width=6, fill=BG)
        if active and st["cls"] in (C.LEFT, C.RIGHT):
            self._arrow(cx, cy, st["cls"], y_off=-190)


# -------------------------------------------------------------------- self-test
def selftest(app):
    """Drive the real UI on the simulator: baseline, movement, 3 screening runs, train, feedback."""
    steps = []
    app.selftest_failed = None
    app.skill.set(0.6)
    app.speed.set(8)              # fast, but slow enough that every screen is drawn (25 Hz redraw)
    app.use_sim()

    def run_and_wait(fn, check, next_step):
        fn()

        def wait():
            if app.selftest_failed:
                return finish(False)
            if app.running:
                return app.root.after(100, wait)
            ok = check()
            steps.append(ok)
            if not ok:
                return finish(False)
            next_step()
        app.root.after(300, wait)

    def finish(ok):
        out = C.APP_DIR / "_out" / "selftest.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(dict(passed=ok, steps=steps, error=app.selftest_failed,
                                       drawing=getattr(app, "drawing_summary", None),
                                       last=getattr(app, "last_summary", None)), indent=2, default=float))
        app.log(f"SELFTEST {'PASSED' if ok else 'FAILED'}")
        app.root.after(300, app.root.destroy)
        app.exit_code = 0 if ok else 1

    def s_baseline():
        app.rec_type.set("baseline")
        run_and_wait(app.start_record, lambda: app.last_summary["samples"] > 0, s_movement)

    def s_movement():
        app.rec_type.set("movement")
        app.rec_trials.set(4)
        run_and_wait(app.start_record, lambda: app.last_summary["samples"] > 0, lambda: s_screen(0))

    def s_screen(k):
        app.rec_type.set("screening")
        app.rec_trials.set(6)
        nxt = (lambda: s_screen(k + 1)) if k < 2 else s_train
        run_and_wait(app.start_record, lambda: app.last_summary["samples"] > 0, nxt)

    def s_train():
        app.refresh_runs()
        app.run_list.selection_clear(0, "end")

        def after(rep):
            steps.append(rep.get("nested_run_accuracy", 0) >= 0.7)
            s_feedback()
        app.do_train(after)

    def s_feedback():
        app.fb_trials.set(5)
        run_and_wait(app.start_feedback, lambda: (app.last_summary.get("accuracy") or 0) >= 0.6, s_drawing)

    def s_drawing():
        dc = getattr(app, "draw_checks", {})
        summary = {k: f"{sum(v)}/{len(v)}" for k, v in dc.items()}
        app.log(f"drawing checks: {summary}")
        app.drawing_summary = summary
        needed = ("cue_arrow_points_to_cued_side", "smiley_grey_and_centred_before_feedback",
                  "smiley_moves_to_decoded_side", "smiley_green_if_correct_red_if_wrong", "feedback_shows_cue_arrow")
        ok = all(k in dc and dc[k] and all(dc[k]) for k in needed)
        steps.append(ok)
        finish(ok)

    def s_signal():
        app.last_quality = None
        app.signal_test()

        def wait():
            if app.selftest_failed:
                return finish(False)
            if app.last_quality is None:
                return app.root.after(200, wait)
            ok = app.last_quality.get("verdict") == "GOOD"
            steps.append(ok)
            return s_baseline() if ok else finish(False)
        app.root.after(500, wait)

    app.root.after(500, s_signal)


def _dpi_aware():
    """Windows display scaling: without this, window coordinates and screen pixels disagree."""
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def main():
    _dpi_aware()
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject", default="P01")
    ap.add_argument("--simulate", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--root", help="data folder (default D:/trainsvm/data/mi_bci)")
    ap.add_argument("--baseline-scale", type=float, default=1.0)
    args = ap.parse_args()
    if args.selftest:
        args.subject = "selftest_" + time.strftime("%Y%m%d_%H%M%S")     # fresh every time
        args.root = args.root or str(C.APP_DIR / "_out" / "selftest_data")
        args.baseline_scale = 0.2
    root = tk.Tk()
    app = App(root, args)
    app.exit_code = 0
    if args.selftest:
        root.after(100, lambda: selftest(app))
        root.after(15 * 60 * 1000, lambda: (app.log("SELFTEST TIMEOUT"), setattr(app, "exit_code", 2), root.destroy()))
    root.mainloop()
    sys.exit(app.exit_code)


if __name__ == "__main__":
    main()
