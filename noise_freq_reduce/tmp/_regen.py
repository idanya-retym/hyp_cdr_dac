import os
import re
import subprocess
import sys

here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src_path = os.path.join(here, "noise_freq_reduce.py")
src = open(src_path, encoding="utf-8").read()
for pct in (1, 5, 10):
    code = re.sub(r"^TARGET_NOISE_ERROR_PCT = .*$", f"TARGET_NOISE_ERROR_PCT = {pct}.0", src, flags=re.M)
    tmp = os.path.join(here, f"_run_{pct}.py")
    open(tmp, "w", encoding="utf-8").write(code)
    subprocess.run([sys.executable, tmp], stderr=subprocess.DEVNULL)
    os.remove(tmp)
    print(f"done {pct}%", flush=True)
