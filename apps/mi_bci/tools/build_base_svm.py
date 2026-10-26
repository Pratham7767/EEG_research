"""Build the base SVM from all 9 BCI IV 2b subjects -> apps/mi_bci/models/base_2b_svm.json
(and the feature cache in _out/base_2b_cache, used every time a subject is trained)."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mibci.svm_trainer import BASE_JSON, build_base, runs_2b  # noqa: E402

t0 = time.time()
for s in range(1, 10):
    r = runs_2b(s)
    print(f"B{s:02d}: {len(r)} runs, {sum(len(x.cues) for x in r)} trials cached ({time.time() - t0:.0f} s)", flush=True)
dec = build_base()
print("base model saved:", BASE_JSON, f"({time.time() - t0:.0f} s)")
print("CSP filters:", dec.p["W"].tolist(), "SVM coef:", dec.p["coef"].tolist())
