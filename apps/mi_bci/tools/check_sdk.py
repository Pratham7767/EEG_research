"""Does the headphone SDK load? Creates the NeuroSDK scanner object only; no Bluetooth search."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mibci.sources import HeadphonesSource  # noqa: E402

try:
    Scanner, SensorFamily, SensorCommand = HeadphonesSource._import()
    print("import ok:", Scanner.__module__, "LEHeadPhones2 =", SensorFamily.LEHeadPhones2)
    s = Scanner([SensorFamily.LEHeadPhones2])
    print("scanner created ok:", type(s).__name__)
    print("commands available:", [c for c in ("StartSignal", "StopSignal", "StartResist", "StopResist")
                                  if hasattr(SensorCommand, c)])
    del s
except Exception as e:
    import traceback
    traceback.print_exc()
    print("SDK FAILED:", e)
    sys.exit(1)
