"""Fill a journal with five weeks of made-up history so the dashboard can be tried out.
Every entry carries "demo": true. Never used unless you pass --demo (or run --selftest)."""
import random
import time

DAY = 86400


def seed(journal, weeks=5, now=None, rng_seed=7):
    rng = random.Random(rng_seed)
    now = time.time() if now is None else now
    start = now - weeks * 7 * DAY
    journal.record_consent()
    for d in range(weeks * 7):
        day = start + d * DAY
        weekday = time.localtime(day).tm_wday
        drift = d / (weeks * 7)                       # strain creeps up over the weeks
        if weekday < 5:
            work = rng.uniform(380, 470) + 120 * drift
            breaks = max(0, round(rng.uniform(3, 5) - 3 * drift))
            prompts = rng.randint(3, 6)
            journal.add("session", ts=day + 10 * 3600, demo=True, simulated=True, work_min=round(work),
                        break_min=breaks * 6, breaks=breaks, real_breaks=breaks,
                        prompts={"prompts": prompts, "accept": max(0, prompts - 1 - int(3 * drift)),
                                 "skip": min(prompts, 1 + int(3 * drift)), "snooze": 0, "later": 0, "ignored": 0},
                        fatigue_mean=50 + 15 * drift + rng.uniform(-5, 5), tension_mean=50 + rng.uniform(-6, 6),
                        attention_mean=55 + rng.uniform(-8, 8), artifact_fraction=0.03, recoveries=1)
            journal.add("kss", ts=day + 10.2 * 3600, demo=True, score=rng.choice([3, 4, 5, 6]) + int(2 * drift))
            journal.add("day_checkin", ts=day + 18 * 3600, demo=True, energy=max(0, round(6 - 4 * drift + rng.uniform(-1, 1))),
                        strain=min(10, round(4 + 4 * drift + rng.uniform(-1, 1))), breaks_ok="Partly")
            if rng.random() < 0.6:
                journal.add("recovery", ts=day + 15 * 3600, demo=True, id=rng.choice(["cyclic_sigh", "mobility"]),
                            minutes=4, rating=rng.choice([3, 4, 4, 5]), alpha_change_pct=round(rng.uniform(-5, 20), 1))
        if weekday == 0:
            score = round(min(5, 1.9 + 1.2 * drift + rng.uniform(-0.15, 0.15)) * 4) / 4
            journal.add("questionnaire", ts=day + 9 * 3600, demo=True, instrument="BAT4", score=score, zone=None,
                        detail={"scale": "1-5 mean, no cut-off"})
    return journal
