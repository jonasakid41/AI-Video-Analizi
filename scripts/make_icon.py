"""Uygulama simgesinin kaynak görselini üretir (1024×1024 PNG). Ardından: npx tauri icon <png>"""

import sys
from pathlib import Path

import cv2
import numpy as np

S = 1024
img = np.zeros((S, S, 4), np.uint8)
# Yuvarlatılmış koyu kare
mask = np.zeros((S, S), np.uint8)
r = 210
cv2.rectangle(mask, (r, 40), (S - r, S - 40), 255, -1)
cv2.rectangle(mask, (40, r), (S - 40, S - r), 255, -1)
for cx, cy in ((r, r), (S - r, r), (r, S - r), (S - r, S - r)):
    cv2.circle(mask, (cx, cy), r - 40, 255, -1)
grad = np.linspace(0, 1, S)[:, None]
bg = np.dstack([(52 + 30 * grad) * np.ones((S, S)), (33 + 18 * grad) * np.ones((S, S)), (17 + 10 * grad) * np.ones((S, S))])
img[..., :3] = bg.astype(np.uint8)
img[..., 3] = mask
# Kamera merceği + tarama çerçevesi
cyan = (230, 200, 60, 255)
amber = (40, 180, 255, 255)
c = (S // 2, S // 2 + 10)
cv2.circle(img, c, 250, cyan, 38, cv2.LINE_AA)
cv2.circle(img, c, 120, cyan, -1, cv2.LINE_AA)
cv2.circle(img, (c[0] - 40, c[1] - 40), 34, (255, 255, 255, 255), -1, cv2.LINE_AA)
L, m = 150, 160
for (x, y, dx, dy) in ((m, m, 1, 1), (S - m, m, -1, 1), (m, S - m, 1, -1), (S - m, S - m, -1, -1)):
    cv2.line(img, (x, y), (x + dx * L, y), amber, 36, cv2.LINE_AA)
    cv2.line(img, (x, y), (x, y + dy * L), amber, 36, cv2.LINE_AA)
img[mask == 0] = 0
out = Path(sys.argv[1] if len(sys.argv) > 1 else "icon-source.png")
ok, buf = cv2.imencode(".png", img)
out.write_bytes(buf.tobytes())
print(out)
