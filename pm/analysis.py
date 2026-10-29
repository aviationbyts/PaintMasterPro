"""Beeldanalyse: afbeelding -> tekeninstructies (lijnen/paden). Geen GUI, geen Windows nodig."""
import math
import cv2
import numpy as np
from .config import PALETTE, WHITE, SPEEDS, PRIO_EPS

_LAB = None


def _pal_lab():
    global _LAB
    if _LAB is None:
        bgr = np.array(PALETTE, np.uint8)[:, ::-1].reshape(1, -1, 3).copy()
        _LAB = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
    return _LAB


class Plan:
    def __init__(self, W, H, strokes, mode, line_width, warnings=None):
        self.W, self.H, self.strokes, self.mode = W, H, strokes, mode
        self.line_width, self.warnings = line_width, warnings or []

    @property
    def actions(self):
        return int(sum(max(1, len(p) - 1) for _, p in self.strokes))

    @property
    def colors(self):
        return sorted({c for c, _ in self.strokes})

    def to_dict(self):
        return {"W": self.W, "H": self.H, "mode": self.mode, "line_width": self.line_width,
                "warnings": self.warnings, "strokes": [[int(c), p.tolist()] for c, p in self.strokes]}

    @staticmethod
    def from_dict(d):
        st = [(int(c), np.array(p, np.int32)) for c, p in d["strokes"]]
        return Plan(d["W"], d["H"], st, d["mode"], d["line_width"], d.get("warnings", []))


# ---------- laden / voorbereiden ----------
def load_image(path):
    data = np.fromfile(path, np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError("Afbeelding kon niet worden gelezen.")
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.shape[2] == 4:
        a = img[:, :, 3:4].astype(np.float32) / 255.0
        img = (img[:, :, :3] * a + 255 * (1 - a)).astype(np.uint8)
    if img.dtype != np.uint8:
        img = cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    return img


def crop_image(img, l, t, r, b):
    h, w = img.shape[:2]
    x0, x1, y0, y1 = int(w * l / 100), w - int(w * r / 100), int(h * t / 100), h - int(h * b / 100)
    if x1 - x0 < 8 or y1 - y0 < 8:
        return img
    return img[y0:y1, x0:x1]


def quality_check(orig, scale, im):
    w = []
    h0, w0 = orig.shape[:2]
    if min(h0, w0) < 160:
        w.append("De afbeelding is erg klein; het resultaat kan korrelig of onscherp worden.")
    if scale < 0.3:
        w.append(f"De afbeelding wordt sterk verkleind ({scale:.0%}); kleine details gaan verloren.")
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    if g.std() < 18:
        w.append("Weinig contrast: er worden mogelijk weinig lijnen gevonden. Verhoog de contoursterkte.")
    if max(h0, w0) / max(1, min(h0, w0)) > 4:
        w.append("Extreme beeldverhouding; overweeg bij te snijden.")
    return w


# ---------- kleur ----------
def smooth_colors(im, d):
    k = 3 if d > 0.66 else 5 if d > 0.33 else 7
    return cv2.medianBlur(cv2.bilateralFilter(im, 7, 35, 7), k)


def quantize(img, max_colors):
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
    pal = _pal_lab()
    d = np.stack([((lab - pal[i]) ** 2).sum(1) for i in range(len(pal))], 1)
    idx = d.argmin(1)
    counts = np.bincount(idx, minlength=len(pal))
    keep = np.argsort(-counts)[:max(1, int(max_colors))]
    idx = keep[d[:, keep].argmin(1)]
    return idx.reshape(img.shape[:2]).astype(np.uint8)


# ---------- lijnen ----------
def edge_mask(im, strength, d, fine=False):
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    k = 5 if d < 0.35 else 3
    g = cv2.GaussianBlur(g, (k, k), 0)
    hi = float(np.interp(strength, [0, 100], [230, 40])) * (0.7 if fine else 1.0)
    return cv2.Canny(g, hi * 0.45, hi)


def chaikin(p, it=1):
    for _ in range(it):
        if len(p) < 3:
            break
        q = [p[0]]
        for a, b in zip(p[:-1], p[1:]):
            q.append(a * 0.75 + b * 0.25)
            q.append(a * 0.25 + b * 0.75)
        q.append(p[-1])
        p = np.array(q, np.float32)
    return p


def densify(p, step):
    out = [p[0]]
    for a, b in zip(p[:-1], p[1:]):
        n = max(1, int(np.linalg.norm(b - a) / step))
        for i in range(1, n + 1):
            out.append(a + (b - a) * i / n)
    return np.array(out, np.float32)


def snap(p, tol=0.09):
    p = p.copy()
    for i in range(1, len(p)):
        dx, dy = p[i, 0] - p[i - 1, 0], p[i, 1] - p[i - 1, 1]
        if abs(dy) <= max(1.5, tol * abs(dx)):
            p[i, 1] = p[i - 1, 1]
        elif abs(dx) <= max(1.5, tol * abs(dy)):
            p[i, 0] = p[i - 1, 0]
    return p


def mask_to_paths(mask, eps, min_len):
    cs, hier = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    out = []
    if hier is None:
        return out
    for c, h in zip(cs, hier[0]):
        if h[3] != -1:  # binnenrand van dunne ring = dubbel
            continue
        pts = c[:, 0, :].astype(np.float32)
        n = len(pts)
        closed = n > 2 and np.linalg.norm(pts[0] - pts[-1]) <= 1.5
        if n >= 4:
            half = n // 2
            if np.linalg.norm(pts[:half] - pts[::-1][:half], axis=1).mean() < 2.0:  # heen-en-terug
                pts = pts[:half + 1]
                closed = False
        if len(pts) < min_len:
            continue
        ap = cv2.approxPolyDP(pts.reshape(-1, 1, 2), float(eps), False)[:, 0, :].astype(np.float32)
        if closed:
            ap = np.vstack([ap, ap[:1]])
        if len(ap) >= 2:
            out.append(ap)
    return out


def _outline(im, s, d, color=0, smooth=False, wobble=0.0, fine=False, do_snap=False, eps_mul=1.0, limit=None):
    eps = float(np.interp(d, [0, 1], [4.5, 0.9])) * eps_mul * PRIO_EPS[s["priority"]]
    minlen = int(np.interp(d, [0, 1], [40, 6]))
    paths = mask_to_paths(edge_mask(im, s["edge_strength"], d, fine), eps, minlen)
    if limit:
        paths.sort(key=lambda p: -np.linalg.norm(np.diff(p, axis=0), axis=1).sum())
        paths = paths[:limit]
    res = []
    rng = np.random.default_rng(7)
    for p in paths:
        if do_snap:
            p = snap(p)
        if wobble:
            p = densify(p, 6)
            p[1:-1] += rng.normal(0, wobble, p[1:-1].shape).astype(np.float32)
        if smooth:
            p = chaikin(p, 1)
        res.append((color, p))
    return res


def fill_strokes(idx, spacing, skip=(WHITE,), min_run=2):
    H, W = idx.shape
    out = []
    for y in range(0, H, max(1, int(spacing))):
        row = idx[y]
        ch = np.flatnonzero(row[1:] != row[:-1]) + 1
        st = np.concatenate(([0], ch))
        en = np.concatenate((ch, [W])) - 1
        for a, b in zip(st, en):
            c = int(row[a])
            if c in skip or b - a + 1 < min_run:
                continue
            out.append((c, np.array([[a, y], [b, y]], np.float32)))
    return out


def hatch_strokes(mask, spacing, color, flip=False):
    if flip:
        mask = mask[:, ::-1]
    H, W = mask.shape
    xs = np.arange(W)
    out = []
    for c in range(-W + 1, H, max(2, int(spacing))):
        ys = xs + c
        ok = (ys >= 0) & (ys < H)
        if not ok.any():
            continue
        x, y = xs[ok], ys[ok]
        v = mask[y, x].astype(np.int8)
        dd = np.diff(np.concatenate(([0], v, [0])))
        for a, b in zip(np.flatnonzero(dd == 1), np.flatnonzero(dd == -1) - 1):
            if b - a >= 3:
                xa, xb = (W - 1 - x[a], W - 1 - x[b]) if flip else (x[a], x[b])
                out.append((color, np.array([[xa, y[a]], [xb, y[b]]], np.float32)))
    return out


# ---------- tekenvolgorde ----------
def _nn(ps, cur):
    n = len(ps)
    if n > 4000:
        ps = sorted(ps, key=lambda p: (int(p[0][1]) // 24, p[0][0] if (int(p[0][1]) // 24) % 2 == 0 else -p[0][0]))
        return ps, ps[-1][-1]
    S = np.array([p[0] for p in ps], np.float32)
    E = np.array([p[-1] for p in ps], np.float32)
    alive = np.ones(n, bool)
    out = []
    for _ in range(n):
        ds = ((S - cur) ** 2).sum(1)
        de = ((E - cur) ** 2).sum(1)
        ds[~alive] = np.inf
        de[~alive] = np.inf
        i, j = int(ds.argmin()), int(de.argmin())
        if ds[i] <= de[j]:
            k, p = i, ps[i]
        else:
            k, p = j, ps[j][::-1]
        alive[k] = False
        out.append(p)
        cur = p[-1]
    return out, cur


def order_layer(strokes, cur):
    groups = {}
    for c, p in strokes:
        groups.setdefault(c, []).append(p)
    out = []
    for c in sorted(groups, key=lambda c: -sum(len(p) for p in groups[c])):
        seq, cur = _nn(groups[c], np.asarray(cur, np.float32))
        out += [(c, p) for p in seq]
    return out


def estimate_seconds(plan, speed, pause_ms=0, priority="Balans"):
    from .config import PRIO_STEP
    sp = SPEEDS[speed]
    step = max(1.0, sp["step"] * PRIO_STEP[priority])
    per = sp["delay"] + 0.0012
    t, last, prev = 2.0, None, None
    for c, p in plan.strokes:
        seg = float(np.linalg.norm(np.diff(p.astype(float), axis=0), axis=1).sum())
        t += seg / step * per + sp["lift"] + pause_ms / 1000.0
        if prev is not None:
            t += float(np.linalg.norm(p[0] - prev)) / (step * 4) * per
        if c != last:
            t += sp["color"] + 0.3
            last = c
        prev = p[-1]
    return t


# ---------- hoofdfunctie ----------
def build_plan(img, s):
    img = crop_image(img, s["crop_l"], s["crop_t"], s["crop_r"], s["crop_b"])
    h0, w0 = img.shape[:2]
    W, H = int(s["canvas_w"]), int(s["canvas_h"])
    sc = min(W / w0, H / h0)
    nw, nh = max(8, int(round(w0 * sc))), max(8, int(round(h0 * sc)))
    im = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA if sc < 1 else cv2.INTER_CUBIC)
    warnings = quality_check(img, sc, im)
    mode, d, lw = s["mode"], s["detail"] / 100.0, max(1, int(s["line_width"]))
    mc = int(s["max_colors"])

    if mode == "Quick Sketch":
        d2 = min(d, 0.45)
        layers = [_outline(im, s, d2, limit=int(60 + d * 140))]
    elif mode == "Precision Drawing":
        d2 = max(d, 0.7)
        layers = [_outline(im, s, d2, fine=True, smooth=True)]
    elif mode == "Outline Only":
        layers = [_outline(im, s, d)]
    elif mode == "Blueprint":
        layers = [_outline(im, s, d, color=8, do_snap=True, eps_mul=1.6)]
    elif mode == "Full Color":
        q = quantize(smooth_colors(im, d), mc)
        layers = [fill_strokes(q, lw, min_run=int(2 + (1 - d) * 8))]
        if d > 0.2:
            layers.append(_outline(im, s, d * 0.8))
    elif mode == "Pixel Art":
        cell = max(2, int(round(np.interp(d, [0, 1], [20, 3]))))
        small = cv2.resize(im, (max(1, nw // cell), max(1, nh // cell)), interpolation=cv2.INTER_AREA)
        q = cv2.resize(quantize(small, mc), (nw, nh), interpolation=cv2.INTER_NEAREST)
        layers = [fill_strokes(q, lw, min_run=2)]
    elif mode == "Artist Mode":
        g = cv2.GaussianBlur(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY), (5, 5), 0)
        sh = s["shadow"] / 100.0
        layers = []
        if sh > 0:
            light = cv2.medianBlur(((g < 70 + sh * 130) * 255).astype(np.uint8), 5) > 0
            layers.append(hatch_strokes(light, max(4, int(9 - 4 * d)), 1))
            if sh > 0.25:
                dark = cv2.medianBlur(((g < 40 + sh * 70) * 255).astype(np.uint8), 5) > 0
                layers.append(hatch_strokes(dark, max(4, int(8 - 3 * d)), 0, flip=True))
        layers.append(_outline(im, s, max(0.3, d), smooth=True, wobble=0.6))
    else:
        raise ValueError(f"Onbekende modus: {mode}")

    strokes, cur = [], (0, 0)
    for L in layers:
        o = order_layer(L, cur)
        strokes += o
        if o:
            cur = o[-1][1][-1]
    strokes = [(c, np.rint(p).astype(np.int32)) for c, p in strokes if len(p) >= 2]
    plan = Plan(nw, nh, strokes, mode, lw, warnings)
    if not strokes:
        plan.warnings.append("Er zijn geen tekenacties gevonden. Verhoog detail of contoursterkte.")
    if plan.actions > 300000:
        plan.warnings.append("Zeer veel tekenacties; het tekenen duurt lang. Verlaag het detailniveau.")
    return plan


def render_preview(plan):
    """Verwacht resultaat, getekend uit de instructies (niet uit de originele afbeelding)."""
    cv = np.full((plan.H, plan.W, 3), 255, np.uint8)
    for c, p in plan.strokes:
        cv2.polylines(cv, [p.reshape(-1, 1, 2).astype(np.int32)], False, PALETTE[c][::-1], max(1, plan.line_width), cv2.LINE_8)
    return cv
