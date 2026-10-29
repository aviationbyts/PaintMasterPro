import time, math, random, threading, logging
from PySide6.QtCore import QThread, Signal
from . import paint as P
from .analysis import build_plan, render_preview
from .config import SPEEDS, PRIO_STEP, HOTKEYS

log = logging.getLogger("pm")


class Stopped(Exception):
    pass


class AnalysisWorker(QThread):
    done = Signal(object, object)
    failed = Signal(str)

    def __init__(self, img, s):
        super().__init__()
        self.img, self.s = img, dict(s)

    def run(self):
        try:
            plan = build_plan(self.img, self.s)
            self.done.emit(plan, render_preview(plan))
        except Exception as e:
            log.exception("analyse mislukt")
            self.failed.emit(str(e))


class DrawWorker(QThread):
    progress = Signal(int, int, float, float, int, int, int)  # done,total,elapsed,remaining,stroke,nstrokes,color
    position = Signal(int, int, int)
    state = Signal(str)  # running/paused/stopped/done/error
    message = Signal(str)

    def __init__(self, plan, s, hwnd, calib, start, est_total):
        super().__init__()
        self.plan, self.s, self.hwnd, self.calib = plan, s, hwnd, calib
        self.start_pos, self.est_total = start, est_total
        sp = SPEEDS[s["speed"]]
        self.step = max(1.0, sp["step"] * PRIO_STEP[s["priority"]])
        self.delay, self.lift, self.jit, self.cpause = max(sp["delay"], 0.0015), sp["lift"], sp["jitter"], sp["color"]
        self.realistic = s["speed"].startswith("Realistisch")
        self.pause_s = s["pause_ms"] / 1000.0
        self.vk_stop = HOTKEYS.get(s["hk_stop"], 0x1B)
        self._pause, self._stop = threading.Event(), threading.Event()
        self.pen_down, self.cur_color, self.cur_xy = False, None, (0.0, 0.0)
        self.paused_total, self.t0, self.done = 0.0, 0.0, 0
        self.si, self.pi = 0, 0
        self._last_health = self._last_emit = 0.0
        x0, y0, x1, y1 = calib["canvas"]
        rw, rh = x1 - x0, y1 - y0
        self.sc = min(rw / plan.W, rh / plan.H)
        self.ox, self.oy = x0 + (rw - plan.W * self.sc) / 2, y0 + (rh - plan.H * self.sc) / 2

    # --- besturing vanuit de GUI ---
    def request_pause(self): self._pause.set()
    def request_resume(self): self._pause.clear()
    def request_stop(self): self._stop.set(); self._pause.clear()

    # --- helpers ---
    def scr(self, p): return (self.ox + p[0] * self.sc, self.oy + p[1] * self.sc)

    def _swatch(self, idx):
        c = self.calib
        (ax, ay), (bx, by) = c["pal0"], c["pal1"]
        cols = c.get("pal_cols", 10)
        col, row = idx % cols, idx // cols
        cvx, cvy = (bx - ax) / max(1, cols - 1), (by - ay) / max(1, cols - 1)
        if "pal2" in c:
            rvx, rvy = c["pal2"][0] - ax, c["pal2"][1] - ay
        else:
            rvx, rvy = 0.0, (by - ay) * 0 + 30.0
        return (ax + col * cvx + row * rvx, ay + col * cvy + row * rvy)

    def _health(self):
        if not P.is_alive(self.hwnd):
            return "Microsoft Paint is gesloten of geminimaliseerd. Open Paint weer en druk op Hervat."
        r = P.get_rect(self.hwnd)
        if max(abs(a - b) for a, b in zip(r, self.calib["win_rect"])) > 2:
            return "Het Paint-venster is verplaatst of vergroot. Zet het terug (of kalibreer opnieuw) en druk op Hervat."
        if not P.foreground_ok(self.hwnd):
            return "Paint is niet meer het actieve venster (ander venster aangeklikt?). Klik op Hervat om door te gaan."
        return None

    def _down(self): P.mouse_down(); self.pen_down = True
    def _up(self):
        if self.pen_down:
            P.mouse_up(); self.pen_down = False

    def _select_tool(self):
        t = self.calib.get("tool")
        if t:
            P.click(*t)
            time.sleep(0.1)

    def _click_color(self, c):
        P.click(*self._swatch(c))
        time.sleep(0.12 + self.cpause)
        self.cur_color = c

    def _cp(self):
        if self._stop.is_set() or P.key_down(self.vk_stop):
            self._stop.set()
            raise Stopped()
        if self._pause.is_set():
            self._handle_pause()
            return
        now = time.time()
        if now - self._last_health > 0.4:
            self._last_health = now
            prob = self._health()
            if prob:
                self.message.emit(prob)
                self._pause.set()
                self._handle_pause()

    def _handle_pause(self):
        was_down, xy = self.pen_down, self.cur_xy
        self._up()
        self._emit_pos()
        self.state.emit("paused")
        t = time.time()
        while True:
            while self._pause.is_set():
                if self._stop.is_set() or P.key_down(self.vk_stop):
                    self._stop.set()
                    raise Stopped()
                time.sleep(0.05)
            if self._stop.is_set():
                raise Stopped()
            P.bring_to_front(self.hwnd)
            time.sleep(0.4)
            prob = self._health()
            if prob:
                self.message.emit(prob)
                self._pause.set()
                continue
            break
        self.paused_total += time.time() - t
        self._select_tool()
        if self.cur_color is not None:
            self._click_color(self.cur_color)
        P.set_cursor(*xy)
        time.sleep(0.05)
        if was_down:
            self._down()
        self._last_health = time.time()
        self.state.emit("running")

    def _glide(self, tx, ty, step, jitter):
        x0, y0 = self.cur_xy
        n = max(1, int(math.hypot(tx - x0, ty - y0) / step))
        for i in range(1, n + 1):
            self._cp()
            f = i / n
            x, y = x0 + (tx - x0) * f, y0 + (ty - y0) * f
            if jitter and i < n:
                x += random.uniform(-jitter, jitter)
                y += random.uniform(-jitter, jitter)
            P.set_cursor(x, y)
            self.cur_xy = (x, y)
            if self.delay:
                time.sleep(self.delay)
        self.cur_xy = (tx, ty)

    def _emit_pos(self): self.position.emit(self.si, self.pi, self.done)

    def _tick(self, force=False):
        now = time.time()
        if not force and now - self._last_emit < 0.15:
            return
        self._last_emit = now
        total = max(1, self.plan.actions)
        el = now - self.t0 - self.paused_total
        if self.done > total * 0.02 and self.done:
            rem = el / self.done * (total - self.done)
        else:
            rem = max(0.0, self.est_total - el)
        c = self.plan.strokes[min(self.si, len(self.plan.strokes) - 1)][0]
        self.progress.emit(self.done, total, el, rem, self.si, len(self.plan.strokes), c)
        self._emit_pos()

    # --- hoofdlus ---
    def run(self):
        P.begin_timer()
        try:
            self._run()
        except Stopped:
            self._up()
            self._tick(True)
            self.state.emit("stopped")
        except Exception as e:
            log.exception("tekenfout")
            self._up()
            self.message.emit(f"Onverwachte fout: {e}")
            self._emit_pos()
            self.state.emit("error")
        finally:
            P.mouse_up()
            P.end_timer()

    def _run(self):
        self.message.emit("Tekenen start over 2 seconden. Raak de muis niet aan. ESC = noodstop.")
        P.bring_to_front(self.hwnd)
        time.sleep(2.0)
        prob = self._health()
        if prob:
            self.message.emit(prob)
            self.state.emit("error")
            return
        self._select_tool()
        strokes = self.plan.strokes
        self.si, self.pi, self.done = self.start_pos
        self.cur_xy = P.cursor_pos()
        self.t0 = time.time()
        self.state.emit("running")
        while self.si < len(strokes):
            c, pts = strokes[self.si]
            self._cp()
            if c != self.cur_color:
                self._up()
                self._click_color(c)
                self.cur_xy = P.cursor_pos()
            k = self.pi
            tx, ty = self.scr(pts[k])
            self._glide(tx, ty, self.step * 4, 0)
            self._down()
            time.sleep(0.03)
            for j in range(k + 1, len(pts)):
                tx, ty = self.scr(pts[j])
                self._glide(tx, ty, self.step, self.jit)
                self.pi = j
                self.done += 1
                self._tick()
            time.sleep(0.02)
            self._up()
            self.si += 1
            self.pi = 0
            pause = self.pause_s + self.lift * (random.uniform(0.4, 1.6) if self.realistic else 1.0)
            if pause:
                time.sleep(pause)
            self._tick()
        self.si = len(strokes)
        self._tick(True)
        self.state.emit("done")
