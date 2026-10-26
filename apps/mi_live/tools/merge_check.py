"""Merges _out/check_2b_live_B0x.json (parallel runs) into _out/check_2b_live.json and prints the table."""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import milive  # noqa: E402,F401
from milive import settings as S  # noqa: E402

res = {}
for f in sorted(S.OUT_DIR.glob("check_2b_live_B0*.json")):
    res.update(json.loads(f.read_text()))
subs = {k: v for k, v in res.items() if k.startswith("B")}
print("model:", res.get("model"))
for k, v in subs.items():
    s = v["sessions"]
    print(f"{k}: acc {100 * v['accuracy']:.1f} % ({v['trials']} trials) | max kappa S4 {s['4']['max_kappa']:.2f} "
          f"S5 {s['5']['max_kappa']:.2f} | identical to offline {s['4']['identical_to_offline'] and s['5']['identical_to_offline']}")
cm = np.sum([np.array(x["confusion"]) for v in subs.values() for x in v["sessions"].values()], 0)
print(f"MEAN accuracy {100 * np.mean([v['accuracy'] for v in subs.values()]):.1f} % | mean max kappa "
      f"{np.mean([v['max_kappa_mean'] for v in subs.values()]):.3f} | pooled confusion {cm.tolist()} | n = {len(subs)}")
(S.OUT_DIR / "check_2b_live.json").write_text(json.dumps(res, indent=1))
