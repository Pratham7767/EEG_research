"""Which model ran a recorded test, and how would the personal model score that run offline?
Also: accuracy if LEFT and RIGHT were swapped (a channel / headset-orientation check).
    C:\\Python313\\python.exe tools\\check_test_run.py <run folder> [<model json>]"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import milive  # noqa: E402,F401
from mibci import config as C  # noqa: E402
from mibci.recorder import load_run  # noqa: E402
from milive.models import LinearCovModel, load_model  # noqa: E402
from milive.personal import UserRun, _score  # noqa: E402

run = Path(sys.argv[1])
r = load_run(run)
m = r["meta"]
dec = (m.get("decoder") or {})
print("run:", run.name, "| model shown in the window:", m.get("model"))
print("model that actually ran:", (dec.get("meta") or {}).get("name"), "| verdict", (dec.get("meta") or {}).get("verdict"))
out = r["outputs"]
cues = [(s, c) for s, n, c in r["events"] if n in ("cue_left", "cue_right")]
if out is not None and len(out):
    I, D, B = out[:, 0].astype(int), out[:, 1], out[:, 3].astype(bool)
    k = kf = n = 0
    for s, c in cues:
        mm = (I >= s + 1.5 * 250) & (I <= s + 4.0 * 250) & ~B
        if mm.any():
            pred = C.RIGHT if np.mean(np.sign(D[mm])) >= 0 else C.LEFT
            k += pred == c
            kf += pred != c
            n += 1
    print(f"live outputs: {k}/{n} correct | if left/right swapped: {kf}/{n}")
u = UserRun(run)
models = sys.argv[2:] or []
if dec.get("kind"):
    models.append(None)
for mp in models:
    mod = LinearCovModel.from_dict(dec) if mp is None else load_model(mp)
    kk, nn = _score(mod, u)
    print(f"offline re-score with {'the model that ran' if mp is None else Path(mp).name}: {kk}/{nn}")
