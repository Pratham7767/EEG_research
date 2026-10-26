"""Are LEFT and RIGHT swapped on the headset? For each run: the 2b base model's accuracy as recorded and with
the headset's left and right sides swapped (A1<->A2, C3<->C4), plus the ERD lateralisation both ways.
The 2b model never saw this person, so it cannot have learned a reversed mapping from them.
    C:\\Python313\\python.exe tools\\swap_check.py <run folder> [...]"""
import sys
from pathlib import Path

import numpy as np
from scipy.stats import binomtest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import milive  # noqa: E402,F401
from mibci import config as C  # noqa: E402
from milive import settings as S  # noqa: E402
from milive.models import load_model  # noqa: E402
from milive.personal import UserRun, _score  # noqa: E402

base = load_model(S.LIVE_DIR / "models" / "base_2b_live.json")
tot = {False: [0, 0], True: [0, 0]}
for p in sys.argv[1:]:
    line = f"{Path(p).name:30s}"
    for swap in (False, True):
        u = UserRun(p, swap=swap)
        k, n = _score(base, u)
        tot[swap][0] += k
        tot[swap][1] += n
        lat = np.mean([d for c, d in u.erd["mu"] if c == C.RIGHT]) - np.mean([d for c, d in u.erd["mu"] if c == C.LEFT])
        line += f" | {'SWAPPED' if swap else 'as worn'}: 2b model {k:2d}/{n}, mu lateralisation {lat:+.2f}"
    print(line)
for swap in (False, True):
    k, n = tot[swap]
    print(f"TOTAL {'with sides swapped' if swap else 'as recorded'}: {k}/{n} = {100 * k / n:.0f} %, "
          f"p = {binomtest(k, n, 0.5, alternative='greater').pvalue:.4f}")
