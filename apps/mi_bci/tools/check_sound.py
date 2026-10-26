"""Which device do beeps go to, and are they fully played? Plays 5 beeps 1 s apart on the chosen output
and counts how many were completely rendered by the audio stream (it cannot know if a person heard it)."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mibci.sound import Sound, list_outputs  # noqa: E402

print("outputs:", [n for _, n in list_outputs()])
s = Sound(sys.argv[1] if len(sys.argv) > 1 else None)
print("chosen output:", s.device, "| error:", s.error)
for k in range(5):
    s.play("beep")
    time.sleep(1.0)
print(f"beeps fully played: {s.played}/5")
s.close()
