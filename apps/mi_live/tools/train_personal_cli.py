"""Train / score a personal model from recorded runs, without the window.
    C:\\Python313\\python.exe tools\\train_personal_cli.py <subject> [<subject> ...] [--all-days] [--save]
Several subjects = their runs pooled (e.g. P01 and Pratham are the same person)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import milive  # noqa: E402,F401
from mibci import config as C  # noqa: E402
from milive.personal import format_report, train_personal, user_runs  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith("--")]
all_days = "--all-days" in sys.argv
subs = args or ["Pratham"]
paths = [p for s in subs for p in user_runs(s, C.DATA_DIR, today_only=not all_days)]
print("runs:", [f"{p.parent.name}/{p.name}" for p in paths], flush=True)
out = C.DATA_DIR / subs[0] / "decoders_live" if "--save" in sys.argv else None
model, rep, _ = train_personal(paths, "+".join(subs), out_dir=out, progress=lambda m: print(" ", m, flush=True))
print(format_report(rep))
for k, v in rep.get("candidates", {}).items():
    print(f"  {k:26s} per run: " + ", ".join(f"{r['correct']}/{r['trials']}" for r in v["per_run"]))
