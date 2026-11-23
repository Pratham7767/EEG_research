"""Daily / weekly trends and a simple, explainable strain-and-recovery indicator.

Research basis: research_notes/questionnaires_trends.md, break_timing.md, eeg_markers.md.
    * Burnout develops over months, so the weekly view is framed as "strain and recovery balance".
    * Only questionnaires with published cut-offs can move the level to "talk to someone"
      (CBI >= 50, WHO-5 <= 50). The BAT4 has no cut-off, so it is compared with the person's
      own baseline (median of their first weekly answers).
    * EEG and work hours are context: they explain, they never raise the level by themselves
      (no EEG marker of burnout is validated; hours are a known risk factor, WHO/ILO 2021).
"""
import datetime
import math
import statistics

from . import config
from .journal import local_date

LEVELS = {
    "balanced": "Balanced",
    "watch": "Keep an eye on it",
    "talk": "Talk to someone",
    "unknown": "Not enough data yet",
}

BAT4_RISE = 0.5               # points on the 1-5 scale above your own baseline
BAT4_BASELINE_N = 4           # weekly answers that form the baseline (first month)


def _mean(xs):
    xs = [x for x in xs if isinstance(x, (int, float)) and math.isfinite(x)]
    return sum(xs) / len(xs) if xs else math.nan


def daily(entries, days=14, today=None):
    """One row per calendar day (oldest first) for the last `days` days."""
    today = today or datetime.date.today()
    rows = {}
    for i in range(days - 1, -1, -1):
        d = (today - datetime.timedelta(days=i)).isoformat()
        rows[d] = {"date": d, "work_min": 0.0, "break_min": 0.0, "breaks": 0, "prompts": 0, "accepted": 0,
                   "skipped": 0, "fatigue": [], "tension": [], "kss": [], "energy": math.nan,
                   "strain": math.nan, "recoveries": 0}
    for e in entries:
        r = rows.get(e.get("date"))
        if r is None:
            continue
        t = e["type"]
        if t == "session":
            r["work_min"] += e.get("work_min", 0) or 0
            r["break_min"] += e.get("break_min", 0) or 0
            r["breaks"] += e.get("real_breaks", 0) or 0
            p = e.get("prompts", {}) or {}
            r["prompts"] += p.get("prompts", 0)
            r["accepted"] += p.get("accept", 0)
            r["skipped"] += p.get("skip", 0) + p.get("ignored", 0)
            r["fatigue"].append(e.get("fatigue_mean"))
            r["tension"].append(e.get("tension_mean"))
        elif t == "kss":
            r["kss"].append(e.get("score"))
        elif t == "day_checkin":
            r["energy"], r["strain"] = e.get("energy", math.nan), e.get("strain", math.nan)
        elif t == "recovery":
            r["recoveries"] += 1
    out = []
    for r in rows.values():
        r["fatigue"], r["tension"], r["kss"] = _mean(r["fatigue"]), _mean(r["tension"]), _mean(r["kss"])
        out.append(r)
    return out


def week_hours(entries, now_ts):
    """Monitored work hours in the last 7 days (only time the app was running)."""
    since = now_ts - 7 * 86400
    return sum((e.get("work_min") or 0) for e in entries if e["type"] == "session" and e["ts"] >= since) / 60.0


def series(entries, instrument):
    return [(e["ts"], e["score"]) for e in entries
            if e["type"] == "questionnaire" and e.get("instrument") == instrument and e.get("score") is not None]


def bat4_baseline(entries):
    s = series(entries, "BAT4")
    if len(s) < 3:
        return None
    return statistics.median([v for _, v in s[:BAT4_BASELINE_N]])


def assess(entries, now_ts):
    """Returns {"level", "label", "reasons": [...], "context": [...], "advice"}."""
    reasons, context = [], []
    level = "unknown"

    def bump(new):
        nonlocal level
        order = ["unknown", "balanced", "watch", "talk"]
        if order.index(new) > order.index(level):
            level = new

    cbi = [e for e in entries if e["type"] == "questionnaire" and e.get("instrument") == "CBI"]
    who = [e for e in entries if e["type"] == "questionnaire" and e.get("instrument") == "WHO5"]
    bat = series(entries, "BAT4")
    if cbi and now_ts - cbi[-1]["ts"] <= 35 * 86400:
        d = cbi[-1].get("detail", {})
        if cbi[-1].get("zone") == "high":
            bump("talk")
            reasons.append(f"Copenhagen Burnout Inventory: work {d.get('work', 0):.0f}, personal "
                           f"{d.get('personal', 0):.0f} (50 or more is 'high')")
        else:
            bump("balanced")
    if who and now_ts - who[-1]["ts"] <= 21 * 86400:
        if who[-1].get("zone") == "low":
            bump("talk")
            reasons.append(f"WHO-5 wellbeing {who[-1]['score']}/100 (50 or less: worth checking in with a professional)")
        else:
            bump("balanced")
    base = bat4_baseline(entries)
    if bat:
        bump("balanced")
        if base is not None and len(bat) > BAT4_BASELINE_N:
            recent = [v for _, v in bat[-4:]]
            above = [v >= base + BAT4_RISE for v in recent]
            if len(recent) >= 4 and all(above):
                bump("talk")
                reasons.append(f"Weekly burnout pulse has been {BAT4_RISE} or more above your usual "
                               f"({base:.2f}) for 4 weeks in a row")
            elif sum(above[-2:]) == 2:
                bump("watch")
                reasons.append(f"Weekly burnout pulse {recent[-1]:.2f}, above your usual {base:.2f} for 2 weeks")

    checkins = [e for e in entries if e["type"] == "day_checkin" and e["ts"] >= now_ts - 7 * 86400]
    if len(checkins) >= 4:
        bump("balanced")
        strain = _mean([e.get("strain") for e in checkins])
        energy = _mean([e.get("energy") for e in checkins])
        if strain >= 7 and energy <= 3:
            bump("watch")
            reasons.append(f"End-of-day check-ins this week: strain {strain:.1f}/10, energy {energy:.1f}/10")

    hours = week_hours(entries, now_ts)
    if hours >= config.WEEK_HOURS_HIGH:
        context.append(f"{hours:.0f} h of monitored work in 7 days. 55 h or more a week is linked to higher "
                       f"stroke and heart-disease risk (WHO/ILO 2021).")
    elif hours >= config.WEEK_HOURS_WATCH:
        context.append(f"{hours:.0f} h of monitored work in 7 days, above 45 h.")
    days = daily(entries, 7, datetime.date.fromtimestamp(now_ts))
    worked = [d for d in days if d["work_min"] >= 60]
    if worked:
        bpd = sum(d["breaks"] for d in worked) / len(worked)
        skipped = sum(d["skipped"] for d in worked)
        prompts = sum(d["prompts"] for d in worked)
        context.append(f"{bpd:.1f} real breaks per working day this week"
                       + (f"; {skipped} of {prompts} break suggestions skipped or ignored" if prompts else ""))
        fat = [d["fatigue"] for d in worked if math.isfinite(d["fatigue"])]
        if len(fat) >= 3:
            context.append(f"Average fatigue signal {sum(fat) / len(fat):.0f} (50 = your usual start-of-work level)")

    advice = {
        "unknown": "Answer the weekly pulse and use a few sessions; the picture builds up over 2-4 weeks.",
        "balanced": "Keep the rhythm: short breaks every hour and a proper lunch away from the screen.",
        "watch": "Protect your breaks and evenings this week, and try one recovery exercise a day. "
                 "If it continues, talk to your manager, HR, or someone you trust about workload.",
        "talk": "Please talk to someone: a doctor, a counsellor, your company's EAP, or "
                + config.HELPLINE + ". This app cannot diagnose anything.",
    }[level]
    return {"level": level, "label": LEVELS[level], "reasons": reasons, "context": context, "advice": advice}


def today_str(now_ts):
    return local_date(now_ts)
