"""Build mi_live's base model: the best model type from tools/compare_models.py (best mean accuracy on
2b people the model never saw), trained on ALL 9 subjects of BCI IV 2b. -> models/base_2b_live.json
    C:\\Python313\\python.exe tools\\build_live_model.py [model name from milive/train2b.SPECS]"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import milive  # noqa: E402,F401
from milive import settings as S  # noqa: E402
from milive.train2b import SPECS, train  # noqa: E402

cmp_file = S.OUT_DIR / "compare_models.json"
cmp = json.loads(cmp_file.read_text()) if cmp_file.exists() else None
spec = sys.argv[1] if len(sys.argv) > 1 else (cmp["ranking"][0] if cmp else "csp_svm")
assert spec in SPECS, f"unknown model {spec}"
m = train(spec)
if cmp:
    m.meta["unseen_accuracy"] = cmp["summary"][spec]["mean"]
    m.meta["unseen_accuracy_per_subject"] = cmp["per_subject"][spec]
    m.meta["compared_with"] = {k: round(v["mean"], 4) for k, v in cmp["summary"].items()}
m.meta["how_chosen"] = ("best mean accuracy over 9 BCI IV 2b subjects, each decoded live-style by a model "
                        "trained on the other 8 (tools/compare_models.py)")
out = S.LIVE_DIR / "models" / "base_2b_live.json"
m.save(out)
print("saved", out, "|", m.name, "| rows", m.meta["n_rows"], "| unseen accuracy", m.meta.get("unseen_accuracy"))
