"""Validated short self-report instruments, embedded only where the licence allows it.

Research basis: research_notes/questionnaires_trends.md.
    BAT4  Burnout Assessment Tool, 4-item version (Hadzibajramovic, Schaufeli & De Witte 2024,
          PLoS ONE 19(2):e0297843). The BAT is non-proprietary and free to use if the items are
          not modified and the source is cited. No cut-off exists -> used for personal trends only.
    CBI   Copenhagen Burnout Inventory, personal + work-related burnout (Kristensen et al. 2005;
          NFA first edition 2004). Free. 0-100, >= 50 = "high".
    WHO5  WHO-5 Well-Being Index (Topp et al. 2015, Psychother Psychosom). Free with attribution.
          0-100; <= 50 suggests checking in with a professional.
    KSS   Karolinska Sleepiness Scale (Akerstedt & Gillberg 1990). Momentary sleepiness, 1-9.
    DAY   End-of-day check-in (energy, strain, breaks). Our own items, NOT a validated scale.

Not embedded: the Maslach Burnout Inventory (paid, research-only licence, no individual
feedback) and the PSS (needs a permission request). These are statements of fact for the
user, never a diagnosis: burnout is an occupational phenomenon, not a medical condition (ICD-11 QD85).
"""
import math

FREQ_5 = ["Never", "Rarely", "Sometimes", "Often", "Always"]                     # BAT, scored 1-5
CBI_FREQ = ["Always", "Often", "Sometimes", "Seldom", "Never / almost never"]     # 100 … 0
CBI_DEGREE = ["To a very high degree", "To a high degree", "Somewhat", "To a low degree",
              "To a very low degree"]                                            # 100 … 0
WHO5_SCALE = ["All of the time", "Most of the time", "More than half of the time",
              "Less than half of the time", "Some of the time", "At no time"]    # 5 … 0

INSTRUMENTS = {
    "BAT4": {
        "title": "Weekly burnout pulse (BAT4)",
        "intro": "How often does each statement apply to you? Think about the past week.",
        "items": [
            ("At work, I feel mentally exhausted", FREQ_5),
            ("I struggle to find any enthusiasm for my work", FREQ_5),
            ("When I'm working, I have trouble concentrating", FREQ_5),
            ("At work I may overreact unintentionally", FREQ_5),
        ],
        "every_days": 7,
        "source": "Burnout Assessment Tool, 4-item version. Hadzibajramović, Schaufeli & De Witte (2024), "
                  "PLoS ONE 19(2):e0297843. Used unmodified, free of charge (burnoutassessmenttool.be).",
    },
    "CBI": {
        "title": "Monthly burnout check (Copenhagen Burnout Inventory)",
        "intro": "Please answer every question. There are no right or wrong answers.",
        "items": [
            # personal burnout (6)
            ("How often do you feel tired?", CBI_FREQ),
            ("How often are you physically exhausted?", CBI_FREQ),
            ("How often are you emotionally exhausted?", CBI_FREQ),
            ("How often do you think: “I can't take it anymore”?", CBI_FREQ),
            ("How often do you feel worn out?", CBI_FREQ),
            ("How often do you feel weak and susceptible to illness?", CBI_FREQ),
            # work-related burnout (7)
            ("Is your work emotionally exhausting?", CBI_DEGREE),
            ("Do you feel burnt out because of your work?", CBI_DEGREE),
            ("Does your work frustrate you?", CBI_DEGREE),
            ("Do you feel worn out at the end of the working day?", CBI_FREQ),
            ("Are you exhausted in the morning at the thought of another day at work?", CBI_FREQ),
            ("Do you feel that every working hour is tiring for you?", CBI_FREQ),
            ("Do you have enough energy for family and friends during leisure time?", CBI_FREQ),
        ],
        "every_days": 28,
        "source": "Copenhagen Burnout Inventory (Kristensen, Borritz, Villadsen & Christensen 2005, "
                  "Work & Stress 19:192-207; NFA first edition 2004).",
    },
    "WHO5": {
        "title": "Two-weekly wellbeing check (WHO-5)",
        "intro": "Over the past two weeks…",
        "items": [
            ("I have felt cheerful and in good spirits", WHO5_SCALE),
            ("I have felt calm and relaxed", WHO5_SCALE),
            ("I have felt active and vigorous", WHO5_SCALE),
            ("I woke up feeling fresh and rested", WHO5_SCALE),
            ("My daily life has been filled with things that interest me", WHO5_SCALE),
        ],
        "every_days": 14,
        "source": "WHO-5 Well-Being Index. Topp, Østergaard, Søndergaard & Bech (2015), "
                  "Psychother Psychosom 84:167-176.",
    },
}

CBI_PERSONAL = range(0, 6)
CBI_WORK = range(6, 13)
CBI_REVERSED = {12}            # "enough energy for family and friends" is reverse-scored


def score(instrument, answers):
    """answers: list of option indices (0 = first option shown), None = skipped.
    Returns {"score": …, "zone": …, "detail": {...}} or raises ValueError if too few answers."""
    items = INSTRUMENTS[instrument]["items"]
    if len(answers) != len(items):
        raise ValueError(f"{instrument}: expected {len(items)} answers, got {len(answers)}")
    if instrument == "BAT4":
        vals = [a + 1 for a in answers if a is not None]                 # Never=1 … Always=5
        if len(vals) < 4:
            raise ValueError("BAT4 needs all 4 answers")
        mean = sum(vals) / 4
        return {"score": round(mean, 2), "zone": None, "detail": {"scale": "1-5 mean, no cut-off"}}
    if instrument == "CBI":
        def item_value(i, a):
            v = 100 - 25 * a                                             # first option = 100
            return 100 - v if i in CBI_REVERSED else v
        personal = [item_value(i, answers[i]) for i in CBI_PERSONAL if answers[i] is not None]
        work = [item_value(i, answers[i]) for i in CBI_WORK if answers[i] is not None]
        if len(personal) < 3 or len(work) < 4:                           # CBI non-responder rule
            raise ValueError("CBI needs at least 3 personal and 4 work answers")
        p, w = sum(personal) / len(personal), sum(work) / len(work)
        zone = "high" if max(p, w) >= 50 else "ok"
        return {"score": round(w, 1), "zone": zone,
                "detail": {"personal": round(p, 1), "work": round(w, 1), "high_from": 50}}
    if instrument == "WHO5":
        if any(a is None for a in answers):
            raise ValueError("WHO-5 needs all 5 answers")
        raw = sum(5 - a for a in answers)                                # first option = 5
        pct = raw * 4
        return {"score": pct, "zone": "low" if pct <= 50 else "ok", "detail": {"raw": raw, "check_from": 50}}
    raise KeyError(instrument)


def due(instrument, last_ts, now, first_use_ts=None):
    """True when the instrument has never been answered or its interval has passed.
    The very first BAT4 waits until the user has had the app for a day, so day one is not a survey."""
    every = INSTRUMENTS[instrument]["every_days"] * 86400
    if last_ts is None:
        if instrument != "BAT4" and first_use_ts is not None and now - first_use_ts < 86400:
            return False                         # day one: only the weekly pulse
        return True
    return now - last_ts >= every - 3600         # an hour of slack so "weekly" can be the same weekday


def describe(instrument, result):
    """One plain sentence about a result. Never diagnostic."""
    if instrument == "BAT4":
        return (f"Burnout pulse {result['score']:.2f} on a 1-5 scale. There is no cut-off for this short "
                f"version; the app compares it with your own earlier weeks.")
    if instrument == "CBI":
        d = result["detail"]
        if result["zone"] == "high":
            return (f"Work-related {d['work']:.0f}, personal {d['personal']:.0f} (0-100). A score of 50 or more "
                    f"is called 'high' by the authors. Consider talking to someone you trust or a professional.")
        return f"Work-related {d['work']:.0f}, personal {d['personal']:.0f} (0-100). Below the 'high' level of 50."
    if instrument == "WHO5":
        if result["zone"] == "low":
            return (f"Wellbeing {result['score']}/100. A score of 50 or less is a sign to check in with a "
                    f"doctor or counsellor; it is not a diagnosis.")
        return f"Wellbeing {result['score']}/100."
    return ""


def is_finite(x):
    return isinstance(x, (int, float)) and math.isfinite(x)
