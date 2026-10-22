"""Wait until the gateway answers. Usage: wait_for_stack.py [seconds]"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pos  # noqa: E402

seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 90.0
if pos.wait_for(seconds):
    print("stack is up:", pos.URL)
else:
    print("gateway did not answer /health within", seconds, "seconds:", pos.URL)
    sys.exit(1)
