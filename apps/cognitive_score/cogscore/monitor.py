"""Monitor: turns engine events into gated, smoothed, recorded session state.

It depends only on an object exposing `.events` (an EventBus) plus a few
attributes (`calibration`, `baseline`, `channel_names`, `sample_rate`), so tests
can drive it with a fake engine and no DLL.

Scores shown to the user (all 0-100):
    attention, cognitive_load, relaxation   SDK Emotions classifier (its own rest baseline)
    stress   high-beta/alpha from the SDK spectrum, 50 = your level in the first 2 min of work
    fatigue  (theta+alpha)/beta from the SDK spectrum, same reference, 60 s smoothing
Band powers (delta…gamma) come from our own raw-EEG spectrum (spectral.py); the chart shows
the % change of each band's absolute power vs the eyes-open rest baseline (ERD/ERS convention).

Events emitted on `monitor.events`:
    quality(grades, gate_progress, gate_open)   scores(snapshot dict)
    signal_warning(bool)                        break_suggested(reason)
    self_report_due()                           ppg_detected()
    stress_episode(active: bool)                scene(key or None)   (a demo scene started / ended)

Besides the CapsuleEngine events it also accepts, from a ReplayEngine:
    index_values(rel, own)   band_frame(frame)   (already-computed values from a recorded session)
"""
import math
import time

import numpy as np

from . import config
from .events import EventBus
from .metrics import (BaselineCollector, RollingMedian, RunningStats, clip01_100, compute_indices, is_valid,
                      level, percent_of_baseline, sanitize, score_vs_baseline)
from .quality import ArtifactWindow, ContactGate
from .rules import BreakRule, SelfReportScheduler, StressEpisodes
from .session import SessionWriter
from .spectral import RawBandAnalyzer

NAN = float("nan")

EMOTIONS = ("attention", "relaxation", "cognitive_load", "cognitive_control", "self_control")
SCORES = ("attention", "cognitive_load", "stress", "relaxation", "fatigue")
BAND_NAMES = tuple(config.RAW_BANDS)


class _Throttle:
    def __init__(self, interval_s):
        self.interval_s, self._last = interval_s, -math.inf

    def ready(self, now):
        if now - self._last >= self.interval_s:
            self._last = now
            return True
        return False


class Monitor:
    def __init__(self, engine, sessions_root=config.SESSIONS_DIR, clock=time.monotonic, wall_clock=time.time):
        self.engine = engine
        self.events = EventBus()
        self._clock = clock
        self._wall = wall_clock
        self._sessions_root = sessions_root
        self.session = None

        self.gate = ContactGate()
        self.gate_last_values = {}
        self.artifacts = ArtifactWindow()
        self.raw = None                        # RawBandAnalyzer, created once the sample rate is known
        self.break_rule = None                 # created when the session goes live
        self.self_reports = None
        self.stress_episodes = StressEpisodes()
        self.live_since = None
        self.gate_overrides = []
        self.breaks = []                       # [[start_elapsed, end_elapsed or None]]
        self.kss = []                          # [(elapsed_s, score)]
        self.markers = []                      # [(elapsed_s, text)]
        self.scenes = []                       # [{"key", "label", "start", "end", "duration"}] (demo scenes)
        self._scene_data = []                  # per scene: {"scores": {k: RunningStats}, "abs": {band: [..]}}
        self._outside = {"scores": {k: RunningStats() for k in SCORES}, "abs": {b: [] for b in BAND_NAMES}}
        self.disconnects = []                  # [[elapsed_s, reconnected_elapsed_s or None]]

        # references: stress/fatigue vs the first minutes of work, band powers vs rest
        self.ratio_base = BaselineCollector()
        self.work_ref_s = config.WORK_REF_S
        self.band_base = BaselineCollector(min_samples=max(6, config.OWN_BASELINE_MIN_SAMPLES // 2))
        self._collecting = False               # band rest baseline
        self._collect_until = None

        self.latest = {"productivity": {}, "indexes": {}, "emotions": {}, "own": {}, "rel": {}, "bands": {},
                       "cardio": {}}
        self._smooth = {k: RollingMedian(config.EMOTION_SMOOTHING_S) for k in EMOTIONS}
        self._smooth["stress"] = RollingMedian(config.SCORE_SMOOTHING_S)
        self._smooth["fatigue"] = RollingMedian(config.FATIGUE_SMOOTHING_S)
        self._smooth.update({f"band_{b}": RollingMedian(config.BAND_SMOOTHING_S) for b in BAND_NAMES})
        self._smooth.update({f"abs_{b}": RollingMedian(config.BAND_SMOOTHING_S) for b in BAND_NAMES})
        self.stats = {k: RunningStats() for k in SCORES}
        self.band_stats = {b: RunningStats() for b in BAND_NAMES}
        self.band_live_abs = {b: [] for b in BAND_NAMES}   # for the session median in the summary
        self.trend = []                        # (elapsed_s, {score: value}) at 1 Hz, whole session
        self.minute_bins = {}                  # minute -> {score: RunningStats}
        self._signal_poor = False

        self._t_res, self._t_art, self._t_emo, self._t_idx = (_Throttle(1.0), _Throttle(1.0),
                                                              _Throttle(0.5), _Throttle(1.0))
        self._t_prod, self._t_scores, self._t_trend = _Throttle(0.2), _Throttle(0.5), _Throttle(1.0)

        ev = engine.events
        for name in ("state", "connected", "resistances", "artifacts", "eeg", "psd", "emotions", "productivity",
                     "indexes", "cardio", "calibrated", "calibration_failed", "baseline", "disconnected", "error",
                     "reconnected", "index_values", "band_frame", "replay_scene", "replay_marker", "replay_break"):
            ev.subscribe(name, getattr(self, f"_on_{name}"))

    # ── public actions (called by the UI) ────────────────────────
    @property
    def elapsed_live(self):
        return 0.0 if self.live_since is None else self._clock() - self.live_since

    @property
    def in_break(self):
        return bool(self.break_rule and self.break_rule.in_break)

    @property
    def reference_ready(self):
        """Stress and fatigue have their working-level reference."""
        return self.ratio_base.frozen is not None

    def work_elapsed(self):
        """Live seconds minus time spent on breaks."""
        if self.live_since is None:
            return 0.0
        now = self.elapsed_live
        return now - sum((end if end is not None else now) - start for start, end in self.breaks)

    def reference_remaining(self):
        return 0.0 if self.reference_ready else max(0.0, self.work_ref_s - self.work_elapsed())

    def override_gate(self, step, detail=""):
        self.gate_overrides.append(step)
        self._event("gate_override", f"{step} {detail}".strip())

    def add_marker(self, text):
        self.markers.append((round(self.elapsed_live, 1), text))
        self._event("marker", text)

    # ── demo scenes ──────────────────────────────────────────────
    @property
    def scene(self):
        """The running scene dict, or None."""
        return self.scenes[-1] if self.scenes and self.scenes[-1]["end"] is None else None

    def scene_remaining(self):
        sc = self.scene
        return 0.0 if sc is None else max(0.0, sc["duration"] - (self.elapsed_live - sc["start"]))

    def start_scene(self, key, duration=None):
        """Start a scene (ends a running one). Not possible before live or during a break."""
        if self.live_since is None or self.in_break or key not in config.SCENES:
            return False
        if self.scene is not None:
            self.end_scene()
        label, default_s, _text = config.SCENES[key]
        now = round(self.elapsed_live, 1)
        self.scenes.append({"key": key, "label": label, "start": now, "end": None,
                            "duration": float(duration if duration is not None else default_s)})
        self._scene_data.append({"scores": {k: RunningStats() for k in SCORES}, "abs": {b: [] for b in BAND_NAMES}})
        self.markers.append((now, label))
        self._event("scene_start", f"{key} {label}")
        self.events.emit("scene", key)
        return True

    def end_scene(self):
        sc = self.scene
        if sc is None:
            return False
        sc["end"] = round(self.elapsed_live, 1)
        self._event("scene_end", sc["key"])
        self.events.emit("scene", None)
        return True

    def _scene_bucket(self, elapsed):
        """Where a clean live sample at `elapsed` belongs: a scene's data, the outside data, or None
        (the settling seconds at the start of a scene)."""
        sc = self.scene
        if sc is None:
            return self._outside
        if elapsed - sc["start"] < config.SCENE_SETTLE_S:
            return None
        return self._scene_data[-1]

    def start_break(self):
        if self.break_rule and not self.in_break:
            self.end_scene()
            self.break_rule.start_break(self._clock())
            self.breaks.append([round(self.elapsed_live, 1), None])
            self._event("break_start")
            if self.stress_episodes.active:         # an episode does not continue through a break
                self.stress_episodes.close(round(self.elapsed_live, 1))
                self._event("stress_episode_end")
                self.events.emit("stress_episode", False)

    def end_break(self):
        if self.in_break:
            counted = self.break_rule.end_break(self._clock())
            self.breaks[-1][1] = round(self.elapsed_live, 1)
            self._event("break_end", "" if counted else "short, work timer not reset")

    def record_self_report(self, score):
        self.kss.append((round(self.elapsed_live, 1), int(score)))
        if self.self_reports:
            self.self_reports.answered(self._clock())
        self._event("self_report_kss", str(int(score)))

    def skip_self_report(self):
        if self.self_reports:
            self.self_reports.answered(self._clock())
        self._event("self_report_skipped")

    def tick(self):
        """Call ~2×/s: evaluates the time-based rules."""
        now = self._clock()
        poor = self.artifacts.is_poor(now)
        if poor != self._signal_poor:
            self._signal_poor = poor
            self.events.emit("signal_warning", poor)
            if self.live_since is not None:
                self._event("signal_poor" if poor else "signal_ok", f"{self.artifacts.fraction(now):.0%} artifacted")
        if self.live_since is None:
            return
        if self.scene is not None and self.scene_remaining() <= 0:
            self.end_scene()
        # The check-in waits until a break or a scene is over (a pop-up during "eyes closed" would spoil it).
        if self.self_reports and not self.in_break and self.scene is None and self.self_reports.due(now):
            self.events.emit("self_report_due")
        reason = self.break_rule.update(now, self._smooth["fatigue"].value(now))
        if reason:
            self._event("break_suggested", reason)
            self.events.emit("break_suggested", reason)

    def snapshot(self):
        now = self._clock()
        sm = {k: m.value(now) for k, m in self._smooth.items()}
        card = self.latest["cardio"]
        snap = {k: sm[k] for k in SCORES}
        snap.update({
            "levels": {k: level(sm[k]) for k in SCORES},
            "bands_rel": {b: sm[f"band_{b}"] for b in BAND_NAMES},
            "bands_change": {b: percent_of_baseline(sm[f"abs_{b}"], self.band_base.get(f"abs_{b}")) for b in BAND_NAMES},
            "bands_ready": self.band_base.frozen is not None,
            "reference_ready": self.reference_ready,
            "reference_remaining_s": self.reference_remaining(),
            "stress_episode": self.stress_episodes.active,
            "artifact_fraction": self.artifacts.fraction(now),
            "signal_poor": self._signal_poor,
            "heart_rate": sanitize(card.get("heart_rate")) if card.get("metrics_available") else NAN,
            "hr_stress_index": sanitize(card.get("stress_index")) if card.get("metrics_available") else NAN,
            "in_break": self.in_break,
            "scene": self.scene["key"] if self.scene else None,
            "elapsed_s": self.elapsed_live,
        })
        return snap

    def summary(self):
        now_elapsed = self.elapsed_live
        curve = []
        for minute in sorted(self.minute_bins):
            b = self.minute_bins[minute]
            curve.append({"minute": minute, **{k: b[k].mean for k in SCORES}})
        return {
            "live_duration_s": round(now_elapsed, 1),
            "scores": {k: {"mean": v.mean, "max": v.max, "last": v.last} for k, v in self.stats.items()},
            "bands_rel_mean": {b: s.mean for b, s in self.band_stats.items()},
            "bands_change_mean": {b: percent_of_baseline(float(np.median(v)) if v else NAN,
                                                         self.band_base.get(f"abs_{b}"))
                                  for b, v in self.band_live_abs.items()},
            "stress_episodes": [[round(a, 1), round(b, 1) if b is not None else None]
                                for a, b in self.stress_episodes.episodes],
            "stress_time_s": round(self.stress_episodes.total_s(now_elapsed), 1),
            "curve": curve,
            "breaks": self.breaks,
            "self_reports_kss": self.kss,
            "markers": self.markers,
            "scenes": self.scene_summary(),
            "disconnects": self.disconnects,
            "mode": config.MODE,
            "artifact_fraction": round(self.artifacts.session_fraction, 3),
            "raw_windows_rejected": round(self.raw.rejected_fraction, 3) if self.raw else None,
            "gate_overrides": self.gate_overrides,
            "ppg_detected": bool(getattr(self.engine, "ppg_seen", False)),
            "own_baseline": {**(self.ratio_base.frozen or {}), **(self.band_base.frozen or {})},
            "session_path": self.session.path if self.session else None,
        }

    def scene_summary(self):
        """Per scene kind: mean scores and band change vs the rest baseline, plus the reference they are
        compared with ("Rest" scenes if there were any, otherwise the live time outside scenes)."""
        def pack(stats, abs_lists):
            return {"scores": {k: stats[k].mean for k in SCORES},
                    "bands_change": {b: percent_of_baseline(float(np.median(v)) if v else NAN,
                                                            self.band_base.get(f"abs_{b}"))
                                     for b, v in abs_lists.items()},
                    "samples": max(st.n for st in stats.values())}
        kinds = []
        for sc in self.scenes:
            if sc["key"] not in kinds:
                kinds.append(sc["key"])
        out = []
        for key in kinds:
            stats = {k: RunningStats() for k in SCORES}
            abs_lists = {b: [] for b in BAND_NAMES}
            seconds = 0.0
            for sc, data in zip(self.scenes, self._scene_data):
                if sc["key"] != key:
                    continue
                seconds += (sc["end"] if sc["end"] is not None else self.elapsed_live) - sc["start"]
                for k in SCORES:
                    st = data["scores"][k]
                    if st.n:
                        stats[k].n += st.n
                        stats[k].total += st.total
                for b in BAND_NAMES:
                    abs_lists[b].extend(data["abs"][b])
            out.append({"key": key, "label": config.SCENES[key][0], "seconds": round(seconds, 1),
                        "count": sum(sc["key"] == key for sc in self.scenes), **pack(stats, abs_lists)})
        rest = next((x for x in out if x["key"] == "rest"), None)
        reference = dict(rest, label="Rest") if rest else {"key": "outside", "label": "Rest of the session",
                                                           **pack(self._outside["scores"], self._outside["abs"])}
        return {"by_kind": out, "reference": reference,
                "list": [dict(sc) for sc in self.scenes]}

    def close(self):
        if self.session and not self.session.closed:
            self.end_scene()
            if self.in_break:
                self.end_break()
            if self.stress_episodes.active:
                self.stress_episodes.close(self.elapsed_live)
                self._event("stress_episode_end")
            self._event("session_end")
            self.session.set_meta("summary", self.summary())
            self.session.close()

    # ── engine event handlers ────────────────────────────────────
    def _event(self, kind, detail=""):
        if self.session:
            self.session.event(kind, detail)

    def _on_state(self, old, new):
        if new == "baseline":
            self._event("baseline_start")
            self.ratio_base, self.band_base = BaselineCollector(), BaselineCollector(
                min_samples=max(6, config.OWN_BASELINE_MIN_SAMPLES // 2))
            self._collecting = True

    def _on_connected(self, info):
        if self.session is None:
            self.session = SessionWriter(self._sessions_root, clock=self._wall)
            self.session.set_meta("device", info)
            self.session.set_meta("simulated", info.get("simulated", False))
            self.session.set_meta("settings", {"raw_bands_hz": config.RAW_BANDS, "sdk_bands_hz": config.BANDS,
                                               "mains_hz": config.MAINS_HZ, "high_beta_hz": config.HIGH_BETA,
                                               **config.mode_settings()})
            self.session.set_meta("mode", config.MODE)
            if info.get("replay_of"):
                self.session.set_meta("replay_of", info["replay_of"])
            if getattr(self.engine, "record_eeg", False):
                self.session.open_eeg(info.get("channels", []))
        channels = info.get("channels") or getattr(self.engine, "channel_names", [])
        fs = info.get("sample_rate") or getattr(self.engine, "sample_rate", None) or 250.0
        if channels:
            self.raw = RawBandAnalyzer(fs, len(channels))
        self._event("connected", info.get("serial", ""))

    def _on_disconnected(self):
        self._event("disconnected")
        if self.live_since is not None:
            self.disconnects.append([round(self.elapsed_live, 1), None])

    def _on_replay_scene(self, key):
        if key is None:
            self.end_scene()
        elif key in config.SCENES:
            self.start_scene(key)

    def _on_replay_marker(self, text):
        if text:
            self.add_marker(text)

    def _on_replay_break(self, started):
        if started and not self.in_break:
            self.start_break()
        elif not started and self.in_break:
            self.end_break()

    def _on_reconnected(self):
        self._event("reconnected")
        if self.disconnects and self.disconnects[-1][1] is None:
            self.disconnects[-1][1] = round(self.elapsed_live, 1)

    def _on_error(self, message):
        self._event("error", message)

    def _on_resistances(self, values):
        now = self._clock()
        self.gate_last_values = values
        grades = self.gate.update(now, values)
        self.events.emit("quality", grades, self.gate.progress(now), self.gate.is_open(now))
        if self.session and self._t_res.ready(now):
            for name, ohms in values.items():
                # An electrode off the skin reads as infinity: record it as "inf" (round(inf) used to raise,
                # so exactly the bad-contact moments were missing from resistances.csv).
                try:
                    value = round(float(ohms)) if math.isfinite(float(ohms)) else "inf"
                except (TypeError, ValueError):
                    value = ""
                self.session.write("resistances", {"electrode": name, "ohms": value, "grade": grades.get(name, "bad")})

    def _on_artifacts(self, sdk_ms, flags):
        now = self._clock()
        artifacted = any(a for a, _q in flags)
        self.artifacts.add(now, artifacted)
        if artifacted and self.raw:
            self.raw.mark_artifact()
        if self.session and self._t_art.ready(now):
            names = getattr(self.engine, "channel_names", []) or []
            for i, (artifact, quality) in enumerate(flags):
                self.session.write("artifacts", {"sdk_ms": sdk_ms, "channel": names[i] if i < len(names) else i,
                                                 "artifact": artifact, "quality": quality})

    def _on_eeg(self, ts, processed, raw):
        if raw is None:
            return
        if self.session and "eeg" in self.session.row_counts:
            wall = round(self._wall(), 3)
            for i, t in enumerate(ts):
                self.session.write_values("eeg", [wall, t, *raw[i], *processed[i]])
        if self.raw is None:
            return
        self.raw.push(raw)
        if self.raw.ready():
            frame = self.raw.compute()
            self._on_band_frame(frame)

    def _on_band_frame(self, frame):
        now = self._clock()
        if self.session:
            row = {"rejected": frame["rejected"] or "", "ptp_uv": frame["ptp"] * 1e6}
            if frame["rel"]:
                row.update({f"{b}_rel": frame["rel"][b] for b in BAND_NAMES})
                row.update({f"{b}_uv2": frame["abs"][b] * 1e12 for b in BAND_NAMES})
            self.session.write("bands", row)
        if not frame["rel"]:
            return
        self.latest["bands"] = frame["rel"]
        for b in BAND_NAMES:
            self._smooth[f"band_{b}"].add(now, frame["rel"][b])
            self._smooth[f"abs_{b}"].add(now, frame["abs"][b])
        if self._collecting:
            self.band_base.add({**{f"band_{b}": frame["rel"][b] for b in BAND_NAMES},
                                **{f"abs_{b}": frame["abs"][b] for b in BAND_NAMES}})
        elif self.band_base.frozen is not None and self.live_since is not None and not self.in_break:
            for b in BAND_NAMES:
                self.band_stats[b].add(frame["rel"][b])
                self.band_live_abs[b].append(frame["abs"][b])
            bucket = self._scene_bucket(self.elapsed_live)
            if bucket is not None:
                for b in BAND_NAMES:
                    bucket["abs"][b].append(frame["abs"][b])
        self._maybe_freeze(now)

    def _on_psd(self, freqs, spectrum, sdk_ms):
        cal = getattr(self.engine, "calibration", None) or {}
        rel, own = compute_indices(freqs, spectrum, cal.get("iapf"))
        self._on_index_values(rel, own)

    def _on_index_values(self, rel, own):
        """Relative SDK band powers + formula indices (from a live spectrum, or replayed from indices.csv)."""
        now = self._clock()
        own = {k: own.get(k, NAN) for k in ("concentration", "relaxation", "fatigue", "reverse_fatigue",
                                             "cognitive_load", "cognitive_control", "alpha_gravity", "arousal")}
        self.latest["rel"], self.latest["own"] = rel, own
        if self.session:
            self.session.write("indices", {**rel, **own})
        clean = self.live_since is not None and not self.in_break and not self._signal_poor
        if clean and self.ratio_base.frozen is None:
            self.ratio_base.add({"arousal": own["arousal"], "fatigue": own["fatigue"]})
            if self.work_elapsed() >= self.work_ref_s and self.ratio_base.enough:
                frozen = self.ratio_base.freeze()
                if self.session:
                    self.session.set_meta("own_baseline_ratios", frozen)
                self._event("reference_ready")
        if self.ratio_base.frozen is not None and not self._signal_poor:
            self._smooth["stress"].add(now, score_vs_baseline(own["arousal"], self.ratio_base.get("arousal")))
            self._smooth["fatigue"].add(now, score_vs_baseline(own["fatigue"], self.ratio_base.get("fatigue")))
        self._maybe_freeze(now)
        self._after_update(now)

    def _on_emotions(self, e):
        now = self._clock()
        clean = {k: clip01_100(e[k]) for k in EMOTIONS}
        self.latest["emotions"] = clean
        for k, v in clean.items():
            self._smooth[k].add(now, v)
        if self.session and self._t_emo.ready(now):
            self.session.write("emotions", {"sdk_ms": e.get("sdk_ms"), **clean})
        self._after_update(now)

    def _on_productivity(self, m):
        now = self._clock()
        clean = {k: (sanitize(v) if isinstance(v, float) else v) for k, v in m.items()}
        self.latest["productivity"] = clean
        if self.session and self._t_prod.ready(now):       # SDK sends ~25/s; 5/s is plenty
            self.session.write("productivity", clean)

    def _on_indexes(self, ix):
        now = self._clock()
        changed = ix.get("recommendation") != self.latest["indexes"].get("recommendation") or \
            ix.get("stress") != self.latest["indexes"].get("stress")
        self.latest["indexes"] = ix
        if self.session and (changed or self._t_idx.ready(now)):
            self.session.write("indexes", ix)

    def _on_cardio(self, c):
        first = not self.latest["cardio"].get("metrics_available") and c.get("metrics_available")
        self.latest["cardio"] = c
        if self.session:
            self.session.write("cardio", c)
        if first:
            self._event("ppg_detected")
            self.events.emit("ppg_detected")

    def _on_calibrated(self, data):
        if self.session:
            self.session.set_meta("calibration", data)
        self._event("calibrated", f"iAPF={data.get('iapf')}")

    def _on_calibration_failed(self, reason):
        self._event("calibration_failed", reason)

    def _on_baseline(self, data):
        now = self._clock()
        self.live_since = now
        self.break_rule = BreakRule(now)
        self.self_reports = SelfReportScheduler(now)
        self.stress_episodes = StressEpisodes()       # timings of the current mode
        if self.session:
            self.session.set_meta("baseline", data)
        imported = bool(data.get("imported"))
        self.work_ref_s = config.FAST_WORK_REF_S if imported else config.WORK_REF_S
        if not self._collecting:                   # imported baseline: band reference from the first seconds of live
            self._collecting = True
        self._collect_until = now if not imported else now + config.FAST_OWN_BASELINE_S
        self._maybe_freeze(now)
        self._event("live_start")

    def _maybe_freeze(self, now):
        """Freeze the band rest baseline once the SDK baseline is done and enough samples exist."""
        if not self._collecting or self._collect_until is None or now < self._collect_until:
            return
        if self.band_base.frozen is None and self.band_base.enough:
            frozen = self.band_base.freeze()
            if self.session:
                self.session.set_meta("own_baseline_bands", frozen)
            self._event("band_baseline_ready")
        if self.band_base.frozen is not None or self.raw is None:
            self._collecting = False

    # ── derived state ────────────────────────────────────────────
    def _after_update(self, now):
        if not self._t_scores.ready(now):
            return
        snap = self.snapshot()
        self.events.emit("scores", snap)
        if self.live_since is not None and self._t_trend.ready(now):
            self._record_trend(snap)

    def _record_trend(self, snap):
        elapsed = snap["elapsed_s"]
        values = {k: snap[k] for k in SCORES}
        self.trend.append((elapsed, values))
        if self.session:
            self.session.write("scores", {"elapsed_s": round(elapsed, 1), **values,
                                          "signal_poor": int(snap["signal_poor"]), "in_break": int(snap["in_break"])})
        usable = not (snap["signal_poor"] or snap["in_break"])
        change = self.stress_episodes.update(elapsed, snap["stress"] if usable else None)
        if change:
            self._event(f"stress_episode_{change}")
            self.events.emit("stress_episode", change == "start")
        if snap["signal_poor"] or snap["in_break"]:
            return                               # artifacted / break seconds do not count towards the summary
        minute = int(elapsed // 60)
        bins = self.minute_bins.setdefault(minute, {k: RunningStats() for k in SCORES})
        bucket = self._scene_bucket(elapsed)
        for k in SCORES:
            if is_valid(values[k]):
                self.stats[k].add(values[k])
                bins[k].add(values[k])
                if bucket is not None:
                    bucket["scores"][k].add(values[k])


COMPARE = (("alpha", "Alpha waves", "band"), ("attention", "Attention", "score"),
           ("cognitive_load", "Cognitive load", "score"), ("relaxation", "Relaxation", "score"),
           ("stress", "Stress", "score"))


def scene_rows(summary):
    """Rows for the "What changed" table: per scene kind, the change vs the reference.
    Band: % change of alpha power vs the eyes-open rest baseline (difference to the reference's own
    change, in percentage points). Scores: difference of the mean 0-100 score vs the reference."""
    sc = summary.get("scenes") or {}
    ref = sc.get("reference") or {}
    rows = []
    for kind in sc.get("by_kind", []):
        if kind["key"] == "rest" and ref.get("key") == "rest":
            continue
        cells = []
        for key, _label, typ in COMPARE:
            if typ == "band":
                v, r = kind["bands_change"].get(key), ref.get("bands_change", {}).get(key)
            else:
                v, r = kind["scores"].get(key), ref.get("scores", {}).get(key)
            cells.append(v - r if is_valid(v) and is_valid(r) else math.nan)
        rows.append((kind["label"], kind["seconds"], cells))
    return ref.get("label", "rest"), rows
