import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np, cv2
from pm.analysis import build_plan, estimate_seconds, render_preview, Plan
from pm.config import MODES, DEFAULTS, SPEEDS

img = np.full((400, 600, 3), 235, np.uint8)
cv2.rectangle(img, (60, 80), (300, 320), (40, 60, 200), -1)
cv2.circle(img, (430, 200), 110, (30, 160, 40), -1)
cv2.line(img, (20, 380), (580, 30), (0, 0, 0), 5)
cv2.putText(img, "TEST", (330, 380), cv2.FONT_HERSHEY_SIMPLEX, 2, (10, 10, 10), 4)
img = cv2.GaussianBlur(img, (3, 3), 0)
ok = True
for m in MODES:
    s = dict(DEFAULTS, mode=m)
    t = time.time()
    p = build_plan(img, s)
    est = {sp: round(estimate_seconds(p, sp)) for sp in ("Supersnel", "Normaal")}
    p2 = Plan.from_dict(p.to_dict())
    prev = render_preview(p2)
    good = len(p.strokes) > 0 and p2.actions == p.actions and prev.shape[:2] == (p.H, p.W)
    ok &= good
    print(f"{m:18s} lijnen={len(p.strokes):5d} acties={p.actions:7d} kleuren={p.colors} est_s={est} analyse={time.time()-t:.1f}s {'OK' if good else 'FAIL'}")
sys.exit(0 if ok else 1)
