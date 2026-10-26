"""Headless commands (no window). Run from apps/mi_bci:

  python -m mibci.cli simulate --subject sim01 --skill 0.5     full pipeline on the simulator
  python -m mibci.cli train    --subject P01                   train on that subject's screening/feedback runs
  python -m mibci.cli erdcheck --subject P01 --types movement  milestone M0 check
  python -m mibci.cli alpha    --run <run folder>              eyes-closed alpha check
  python -m mibci.cli runs     --subject P01                   list recorded runs
"""
import argparse
import json
import sys
import time
from pathlib import Path

from . import config as C
from .analysis import alpha_check, erd_check
from .decoder import Decoder
from .engine import Engine
from .paradigm import BaselineParadigm, Paradigm, make_schedule
from .recorder import Recorder, list_runs
from .sources import SimulatedSource
from .trainer import train


def run_session(source, run_type, subject, n_per_class=None, decoder=None, seed=None, root=C.DATA_DIR,
                record=True, baseline_scale=1.0, on_event=None):
    """Run one run to the end without a window. Returns (summary, run folder)."""
    if run_type == "baseline":
        par = BaselineParadigm(scale=baseline_scale)
    else:
        n = n_per_class or C.DEFAULT_TRIALS_PER_CLASS[run_type]
        par = Paradigm(run_type, make_schedule(n, seed), seed=seed)
    rec = Recorder(subject, run_type, root=root) if record else None
    eng = Engine(source, par, decoder, rec, on_event)
    source.start()
    while eng.pump():
        if source.realtime:
            time.sleep(0.01)
    source.stop()
    summ = eng.finish()
    return summ, (rec.dir if rec else None)


def cmd_simulate(a):
    root = Path(a.root) if a.root else C.DATA_DIR
    src = lambda k: SimulatedSource(skill=a.skill, seed=a.seed + k, realtime=False)
    out = {}
    s, d = run_session(src(0), "movement", a.subject, a.trials, seed=a.seed, root=root)
    out["movement"] = str(d)
    screen = []
    for r in range(a.screening_runs):
        s, d = run_session(src(10 + r), "screening", a.subject, a.trials, seed=a.seed + 10 + r, root=root)
        screen.append(d)
    out["erd_check"] = erd_check([out["movement"]] + [str(p) for p in screen], n_perm=1000)
    if C.MODEL == "svm":
        from .svm_trainer import train_svm
        dec, rep = train_svm(screen, a.subject, out_dir=root / a.subject / "decoders")
    else:
        dec, rep = train(screen, a.subject, out_dir=root / a.subject / "decoders", n_perm=a.perm)
    out["training"] = rep
    fb = []
    for r in range(a.feedback_runs):
        s, d = run_session(src(100 + r), "feedback", a.subject, a.trials, decoder=dec, seed=a.seed + 100 + r,
                           root=root)
        fb.append(s)
    out["feedback"] = fb
    print(json.dumps(out, indent=2, default=float))
    return out


def cmd_train(a):
    root = Path(a.root) if a.root else C.DATA_DIR
    runs = list_runs(a.subject, a.types.split(","), root)
    if not runs:
        sys.exit(f"no runs of type {a.types} for {a.subject} in {root}")
    if C.MODEL == "svm":
        from .svm_trainer import train_svm
        dec, rep = train_svm(runs, a.subject, out_dir=root / a.subject / "decoders")
    else:
        dec, rep = train(runs, a.subject, out_dir=root / a.subject / "decoders", n_perm=a.perm)
    print(json.dumps(rep, indent=2, default=float))


def cmd_erd(a):
    root = Path(a.root) if a.root else C.DATA_DIR
    runs = list_runs(a.subject, a.types.split(","), root)
    print(json.dumps(erd_check([str(r) for r in runs]), indent=2))


def cmd_alpha(a):
    print(json.dumps(alpha_check(a.run), indent=2))


def cmd_runs(a):
    root = Path(a.root) if a.root else C.DATA_DIR
    for r in list_runs(a.subject, None, root):
        m = json.loads((r / "run.json").read_text())
        print(r.name, m.get("run_type"), m.get("summary"))


def main(argv=None):
    p = argparse.ArgumentParser(prog="mibci")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("simulate")
    s.add_argument("--subject", default="sim01")
    s.add_argument("--skill", type=float, default=0.5)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--trials", type=int, default=10)
    s.add_argument("--screening-runs", type=int, default=3)
    s.add_argument("--feedback-runs", type=int, default=1)
    s.add_argument("--perm", type=int, default=100)
    s.add_argument("--root")
    s.set_defaults(f=cmd_simulate)
    for name, f in (("train", cmd_train), ("erdcheck", cmd_erd), ("runs", cmd_runs)):
        q = sub.add_parser(name)
        q.add_argument("--subject", required=True)
        q.add_argument("--types", default="screening,feedback" if name == "train" else "movement,screening")
        q.add_argument("--perm", type=int, default=200)
        q.add_argument("--root")
        q.set_defaults(f=f)
    q = sub.add_parser("alpha")
    q.add_argument("--run", required=True)
    q.set_defaults(f=cmd_alpha)
    a = p.parse_args(argv)
    return a.f(a)


if __name__ == "__main__":
    main()
