"""Local, append-only personal journal (data/journal.jsonl) plus settings (data/settings.json).

One JSON object per line. Every entry has `type`, `ts` (unix seconds) and `date` (local YYYY-MM-DD).
Entry types:
    consent        the user accepted the privacy notice (version)
    session        one work session: work/break minutes, prompts and answers, mean scores
    kss            Karolinska Sleepiness Scale answer (1-9)
    day_checkin    end-of-day check-in: energy, strain (0-10), breaks_ok (bool)
    questionnaire  instrument id, answers, score, zone
    recovery       exercise done during a break: id, minutes, rating (1-5), EEG change

Nothing in this module talks to the network. Deleting `data/` removes everything.
"""
import datetime
import json
import os
import shutil
import time
import zipfile

from . import config
from .session import _clean

PRIVACY_VERSION = 1


def local_date(ts):
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


class Journal:
    def __init__(self, data_dir=config.DATA_DIR, clock=time.time):
        self.data_dir = data_dir
        self.path = os.path.join(data_dir, "journal.jsonl")
        self.settings_path = os.path.join(data_dir, "settings.json")
        self._clock = clock
        os.makedirs(data_dir, exist_ok=True)

    # ── entries ──
    def add(self, type_, ts=None, **fields):
        ts = self._clock() if ts is None else ts
        entry = {"type": type_, "ts": round(ts, 3), "date": local_date(ts), **fields}
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(_clean(entry), allow_nan=False) + "\n")
        return entry

    def entries(self, type_=None, since_ts=None):
        if not os.path.isfile(self.path):
            return []
        out = []
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:        # a half-written last line after a crash
                    continue
                if type_ and e.get("type") != type_:
                    continue
                if since_ts is not None and e.get("ts", 0) < since_ts:
                    continue
                out.append(e)
        return out

    def last(self, type_, **match):
        for e in reversed(self.entries(type_)):
            if all(e.get(k) == v for k, v in match.items()):
                return e
        return None

    def today(self, type_=None):
        today = local_date(self._clock())
        return [e for e in self.entries(type_) if e.get("date") == today]

    # ── settings ──
    def settings(self):
        defaults = {"eye_rest": False, "sound": True, "retention_days": config.RETENTION_DAYS}
        if os.path.isfile(self.settings_path):
            try:
                with open(self.settings_path, encoding="utf-8") as fh:
                    defaults.update(json.load(fh))
            except (OSError, json.JSONDecodeError):
                pass
        return defaults

    def save_settings(self, **changes):
        s = self.settings()
        s.update(changes)
        tmp = self.settings_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(s, fh, indent=2)
        os.replace(tmp, self.settings_path)
        return s

    # ── consent and privacy controls ──
    def has_consent(self):
        e = self.last("consent")
        return bool(e and e.get("version") == PRIVACY_VERSION and e.get("accepted"))

    def record_consent(self, accepted=True):
        return self.add("consent", version=PRIVACY_VERSION, accepted=bool(accepted))

    def export_zip(self, dest_path):
        """Everything in data/ in one zip the user can keep or inspect."""
        with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _dirs, files in os.walk(self.data_dir):
                for name in files:
                    full = os.path.join(root, name)
                    if os.path.abspath(full) == os.path.abspath(dest_path):
                        continue
                    zf.write(full, os.path.relpath(full, self.data_dir))
        return dest_path

    def delete_all(self):
        """Remove every personal file the app has written. Cannot be undone."""
        if os.path.isdir(self.data_dir):
            shutil.rmtree(self.data_dir)
        os.makedirs(self.data_dir, exist_ok=True)

    def apply_retention(self, sessions_dir, days=None, now=None):
        """Delete session recording folders older than `days` (the journal summary stays).
        Returns the deleted folder names."""
        days = self.settings()["retention_days"] if days is None else days
        if not days or not os.path.isdir(sessions_dir):
            return []
        cutoff = (self._clock() if now is None else now) - days * 86400
        removed = []
        for name in os.listdir(sessions_dir):
            full = os.path.join(sessions_dir, name)
            if os.path.isdir(full) and os.path.getmtime(full) < cutoff:
                shutil.rmtree(full, ignore_errors=True)
                removed.append(name)
        return removed

