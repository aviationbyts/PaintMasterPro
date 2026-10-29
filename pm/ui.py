import os, time, logging
import cv2, numpy as np
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QSize, Signal
from PySide6.QtGui import QPixmap, QImage, QIcon
from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QLabel, QPushButton, QFrame,
    QComboBox, QSlider, QSpinBox, QProgressBar, QPlainTextEdit, QFileDialog, QMessageBox, QStackedWidget, QListWidget,
    QListWidgetItem, QDialog, QInputDialog, QSizePolicy, QFormLayout, QSpacerItem)
from . import paint as P
from .analysis import load_image, estimate_seconds, render_preview, Plan
from .config import *
from .logo import make_logo
from .project import *
from .worker import AnalysisWorker, DrawWorker

log = logging.getLogger("pm")
EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")

STYLE = """
QWidget{background:#0f1020;color:#e6e8f5;font-family:'Segoe UI';font-size:13px}
QLabel{background:transparent}
QFrame#side{background:#0b0b18;border-right:1px solid #24264a}
QFrame#card{background:#171932;border:1px solid #2a2d5a;border-radius:14px}
QLabel#h1{font-size:22px;font-weight:700}
QLabel#h2{font-size:14px;font-weight:600;color:#a9b4ff}
QLabel#dim{color:#8e93c4}
QPushButton{background:#23264d;border:1px solid #34387a;border-radius:10px;padding:8px 14px}
QPushButton:hover{background:#2e3270;border-color:#5b6cff}
QPushButton:disabled{color:#666a99;background:#1a1c38;border-color:#25285a}
QPushButton#primary{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #3b82f6,stop:1 #8b5cf6);border:none;font-weight:700}
QPushButton#primary:disabled{background:#2a2d5a}
QPushButton#danger{background:#b3243b;border:none;font-weight:700}
QPushButton#danger:disabled{background:#3a2030}
QPushButton#nav{text-align:left;padding:11px 16px;border:none;background:transparent;border-radius:0}
QPushButton#nav:checked{background:#23264d;border-left:3px solid #8b5cf6;font-weight:600}
QComboBox,QSpinBox,QPlainTextEdit,QListWidget{background:#10112a;border:1px solid #34387a;border-radius:8px;padding:5px}
QComboBox QAbstractItemView{background:#10112a;selection-background-color:#3b3f8f}
QProgressBar{background:#10112a;border:1px solid #34387a;border-radius:11px;height:22px;text-align:center;font-weight:600}
QProgressBar::chunk{border-radius:10px;background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #3b82f6,stop:1 #8b5cf6)}
QSlider::groove:horizontal{height:6px;background:#10112a;border-radius:3px}
QSlider::handle:horizontal{background:#8b5cf6;width:16px;margin:-6px 0;border-radius:8px}
QSlider::sub-page:horizontal{background:#3b82f6;border-radius:3px}
"""


def np_to_pix(a):
    rgb = cv2.cvtColor(a, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    return QPixmap.fromImage(QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy())


def fmt_t(sec):
    sec = int(max(0, sec))
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}" if sec >= 3600 else f"{sec // 60}:{sec % 60:02d}"


class ImageView(QLabel):
    def __init__(self, text):
        super().__init__(text)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(200, 160)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.setStyleSheet("background:#10112a;border:1px dashed #34387a;border-radius:10px;color:#6f74b0")
        self._pix = None

    def set_pix(self, p):
        self._pix = p
        self._fit()

    def clear_pix(self, text):
        self._pix = None
        self.clear()
        self.setText(text)

    def resizeEvent(self, e):
        self._fit()
        super().resizeEvent(e)

    def _fit(self):
        if self._pix:
            self.setPixmap(self._pix.scaled(self.size() - QSize(8, 8), Qt.KeepAspectRatio, Qt.SmoothTransformation))


def card(title=None):
    f = QFrame()
    f.setObjectName("card")
    l = QVBoxLayout(f)
    l.setContentsMargins(16, 14, 16, 14)
    l.setSpacing(8)
    if title:
        t = QLabel(title)
        t.setObjectName("h2")
        l.addWidget(t)
    return f, l


class Calibrator(QDialog):
    done = Signal(dict)
    STEPS = [("canvas0", "Stap 1/6: beweeg de muis naar de LINKERBOVENHOEK van het witte tekenvlak en druk {k}."),
             ("canvas1", "Stap 2/6: beweeg de muis naar de RECHTERONDERHOEK van het witte tekenvlak (zichtbaar deel) en druk {k}."),
             ("pal0", "Stap 3/6: beweeg de muis precies op de ZWARTE kleur (bovenste rij, helemaal links) en druk {k}."),
             ("pal1", "Stap 4/6: beweeg de muis op de PAARSE kleur (bovenste rij, helemaal rechts, de 10e) en druk {k}."),
             ("pal2", "Stap 5/6: beweeg de muis op de WITTE kleur (onderste rij, helemaal links) en druk {k}."),
             ("tool", "Stap 6/6: beweeg de muis op het knopje van je gereedschap (potlood/penseel) en druk {k}. (Of klik 'Overslaan'.)")]

    def __init__(self, parent, vk, keyname, hwnd):
        super().__init__(parent)
        self.vk, self.hwnd, self.keyname, self.i, self.data, self.prev = vk, hwnd, keyname, 0, {}, True
        self.setWindowTitle("Kalibreren")
        self.setWindowFlags(Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setMinimumWidth(520)
        l = QVBoxLayout(self)
        self.lbl = QLabel()
        self.lbl.setWordWrap(True)
        l.addWidget(self.lbl)
        row = QHBoxLayout()
        self.skip = QPushButton("Overslaan")
        self.skip.clicked.connect(self._skip)
        self.skip.setVisible(False)
        cancel = QPushButton("Annuleren")
        cancel.clicked.connect(self.reject)
        row.addWidget(self.skip)
        row.addStretch()
        row.addWidget(cancel)
        l.addLayout(row)
        self._show()
        self.t = QTimer(self)
        self.t.timeout.connect(self._poll)
        self.t.start(30)
        sg = self.screen().availableGeometry()
        self.move(sg.right() - 560, sg.bottom() - 200)

    def _show(self):
        self.lbl.setText(self.STEPS[self.i][1].format(k=self.keyname))
        self.skip.setVisible(self.i == len(self.STEPS) - 1)

    def _poll(self):
        d = P.key_down(self.vk)
        if d and not self.prev:
            self.data[self.STEPS[self.i][0]] = P.cursor_pos()
            self._next()
        self.prev = d

    def _skip(self):
        self.data["tool"] = None
        self._next(force=True)

    def _next(self, force=False):
        self.i += 1
        if self.i >= len(self.STEPS) or force:
            self.t.stop()
            d = self.data
            (x0, y0), (x1, y1) = d["canvas0"], d["canvas1"]
            if x1 - x0 < 50 or y1 - y0 < 50:
                QMessageBox.warning(self, "Kalibreren", "Het tekenvlak is te klein of de hoeken staan verkeerd om. Probeer opnieuw.")
                return self.reject()
            self.done.emit({"canvas": [x0, y0, x1, y1], "pal0": list(d["pal0"]), "pal1": list(d["pal1"]), "pal2": list(d["pal2"]),
                            "tool": list(d["tool"]) if d.get("tool") else None, "pal_cols": 10, "pal_rows": 2,
                            "win_rect": list(P.get_rect(self.hwnd))})
            self.accept()
        else:
            self._show()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PaintMaster Pro")
        self.setWindowIcon(QIcon(make_logo(256)))
        self.resize(1320, 840)
        self.setAcceptDrops(True)
        self.s = load_settings()
        self.image = self.image_path = self.plan = self.preview = None
        self.dirty, self.worker, self.analyzer = True, None, None
        self.pid, self.resume_pos, self.pending_start, self.pos = None, None, False, (0, 0, 0)
        self.w, self.prev_keys, self.state = {}, {}, "idle"
        self._build()
        self.apply_settings(self.s)
        self.refresh_profiles()
        self.refresh_paint()
        self.refresh_history()
        self.set_buttons()
        self.hk = QTimer(self)
        self.hk.timeout.connect(self.poll_keys)
        self.hk.start(40)
        self.st = QTimer(self)
        self.st.timeout.connect(self.update_paint_status)
        self.st.start(1000)
        self.log_msg("Welkom bij PaintMaster Pro. Kies een afbeelding om te beginnen.")

    # ---------- opbouw ----------
    def _ctl(self, key, w, plan=True):
        self.w[key] = w
        sig = w.currentTextChanged if isinstance(w, QComboBox) else w.valueChanged
        sig.connect(self.mark_dirty if plan else self.update_estimate)
        return w

    def spin(self, key, lo, hi, suffix="", plan=True):
        w = QSpinBox()
        w.setRange(lo, hi)
        w.setSuffix(suffix)
        return self._ctl(key, w, plan)

    def combo(self, key, items, plan=True):
        w = QComboBox()
        w.addItems(items)
        return self._ctl(key, w, plan)

    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        side = QFrame()
        side.setObjectName("side")
        side.setFixedWidth(210)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 18, 0, 12)
        logo = QLabel()
        logo.setPixmap(make_logo(84).scaled(84, 84, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo.setAlignment(Qt.AlignCenter)
        sl.addWidget(logo)
        t = QLabel("PaintMaster Pro")
        t.setObjectName("h2")
        t.setAlignment(Qt.AlignCenter)
        sl.addWidget(t)
        sl.addSpacing(14)
        self.stack = QStackedWidget()
        self.navs = []
        for i, name in enumerate(["  Dashboard", "  Instellingen", "  Geschiedenis"]):
            b = QPushButton(name)
            b.setObjectName("nav")
            b.setCheckable(True)
            b.clicked.connect(lambda _, i=i: self.goto(i))
            sl.addWidget(b)
            self.navs.append(b)
        sl.addStretch()
        v = QLabel("v1.0  ·  lokaal, geen cloud")
        v.setObjectName("dim")
        v.setAlignment(Qt.AlignCenter)
        sl.addWidget(v)
        h.addWidget(side)
        h.addWidget(self.stack, 1)
        self.stack.addWidget(self._dashboard())
        self.stack.addWidget(self._settings_page())
        self.stack.addWidget(self._history_page())
        self.goto(0)

    def goto(self, i):
        self.stack.setCurrentIndex(i)
        for k, b in enumerate(self.navs):
            b.setChecked(k == i)
        if i == 2:
            self.refresh_history()

    def _dashboard(self):
        page = QWidget()
        h = QHBoxLayout(page)
        h.setContentsMargins(18, 18, 18, 18)
        h.setSpacing(14)
        left = QVBoxLayout()
        pc, pl = card("Voorbeeld  ·  A/B-vergelijking")
        row = QHBoxLayout()
        self.v_orig, self.v_prev = ImageView("Sleep een afbeelding hierheen\nof klik op 'Afbeelding kiezen'"), ImageView("Hier verschijnt het\nverwachte resultaat")
        for cap, v in (("Origineel", self.v_orig), ("Verwacht resultaat (uit tekeninstructies)", self.v_prev)):
            c = QVBoxLayout()
            lb = QLabel(cap)
            lb.setObjectName("dim")
            c.addWidget(lb)
            c.addWidget(v, 1)
            row.addLayout(c, 1)
        pl.addLayout(row, 1)
        self.info = QLabel("Nog geen afbeelding.")
        self.info.setWordWrap(True)
        pl.addWidget(self.info)
        br = QHBoxLayout()
        b1 = QPushButton("Afbeelding kiezen…")
        b1.clicked.connect(self.choose_image)
        self.b_an = QPushButton("Analyseer / preview")
        self.b_an.clicked.connect(lambda: self.analyze())
        br.addWidget(b1)
        br.addWidget(self.b_an)
        br.addStretch()
        pl.addLayout(br)
        left.addWidget(pc, 1)
        sc, sl = card("Tekenstijl")
        g = QGridLayout()
        g.addWidget(QLabel("Modus"), 0, 0)
        g.addWidget(self.combo("mode", MODES), 0, 1)
        g.addWidget(QLabel("Snelheid"), 0, 2)
        g.addWidget(self.combo("speed", list(SPEEDS), plan=False), 0, 3)
        g.addWidget(QLabel("Detail"), 1, 0)
        sd = QSlider(Qt.Horizontal)
        sd.setRange(0, 100)
        self._ctl("detail", sd)
        self.lbl_detail = QLabel("55")
        sd.valueChanged.connect(lambda v: self.lbl_detail.setText(f"{v}  ({'schets' if v < 35 else 'gedetailleerd' if v > 70 else 'gemiddeld'})"))
        g.addWidget(sd, 1, 1, 1, 2)
        g.addWidget(self.lbl_detail, 1, 3)
        g.addWidget(QLabel("Profiel"), 2, 0)
        self.cb_prof = QComboBox()
        self.cb_prof.activated.connect(self.load_profile)
        g.addWidget(self.cb_prof, 2, 1, 1, 2)
        bp = QPushButton("Profiel opslaan")
        bp.clicked.connect(self.save_profile)
        g.addWidget(bp, 2, 3)
        sl.addLayout(g)
        left.addWidget(sc)
        h.addLayout(left, 3)

        right = QVBoxLayout()
        c1, l1 = card("Microsoft Paint")
        r = QHBoxLayout()
        self.cb_win = QComboBox()
        self.cb_win.setMinimumWidth(200)
        r.addWidget(self.cb_win, 1)
        for txt, fn in (("↻", self.refresh_paint), ("Paint openen", self.open_paint), ("Kalibreren", self.calibrate), ("Kleurtest", self.color_test)):
            b = QPushButton(txt)
            b.clicked.connect(lambda _, f=fn: f())
            r.addWidget(b)
        l1.addLayout(r)
        self.lbl_paint = QLabel("Paint: niet verbonden")
        self.lbl_calib = QLabel("Kalibratie: ontbreekt")
        l1.addWidget(self.lbl_paint)
        l1.addWidget(self.lbl_calib)
        right.addWidget(c1)
        c2, l2 = card("Live tekenmonitor")
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setFormat("%p%")
        self.bar.setTextVisible(True)
        self.anim = QPropertyAnimation(self.bar, b"value", self)
        self.anim.setDuration(180)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        l2.addWidget(self.bar)
        gm = QGridLayout()
        self.m = {}
        for i, (k, name) in enumerate([("fase", "Fase"), ("acties", "Acties"), ("tijd", "Verstreken"), ("rest", "Resterend"),
                                       ("kleur", "Kleur"), ("modus", "Modus"), ("paint", "Paint"), ("status", "Status")]):
            a = QLabel(name)
            a.setObjectName("dim")
            b = QLabel("–")
            self.m[k] = b
            gm.addWidget(a, i // 2, (i % 2) * 2)
            gm.addWidget(b, i // 2, (i % 2) * 2 + 1)
        l2.addLayout(gm)
        right.addWidget(c2)
        c3, l3 = card("Besturing")
        rb = QHBoxLayout()
        self.btn = {}
        for key, txt, name in (("start", "▶ Start", "primary"), ("pause", "⏸ Pauze", ""), ("resume", "⏵ Hervat", ""),
                               ("stop", "■ Stop", ""), ("estop", "⚠ Noodstop", "danger")):
            b = QPushButton(txt)
            if name:
                b.setObjectName(name)
            b.setMinimumHeight(38)
            self.btn[key] = b
            rb.addWidget(b)
        self.btn["start"].clicked.connect(self.start)
        self.btn["pause"].clicked.connect(self.pause)
        self.btn["resume"].clicked.connect(self.resume)
        self.btn["stop"].clicked.connect(self.stop)
        self.btn["estop"].clicked.connect(self.stop)
        l3.addLayout(rb)
        self.lbl_keys = QLabel()
        self.lbl_keys.setObjectName("dim")
        l3.addWidget(self.lbl_keys)
        right.addWidget(c3)
        c4, l4 = card("Logboek")
        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumBlockCount(500)
        l4.addWidget(self.log_box)
        right.addWidget(c4, 1)
        h.addLayout(right, 2)
        return page

    def _settings_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(24, 20, 24, 20)
        t = QLabel("Instellingen")
        t.setObjectName("h1")
        v.addWidget(t)
        c, l = card()
        f = QFormLayout()
        f.addRow("Lijndikte (px, zoals in Paint ingesteld)", self.spin("line_width", 1, 30, " px"))
        f.addRow("Canvasafmetingen breedte", self.spin("canvas_w", 100, 4000, " px"))
        f.addRow("Canvasafmetingen hoogte", self.spin("canvas_h", 100, 4000, " px"))
        f.addRow("Maximaal aantal kleuren", self.spin("max_colors", 1, 20))
        f.addRow("Contoursterkte", self.spin("edge_strength", 0, 100))
        f.addRow("Schaduwniveau (Artist Mode)", self.spin("shadow", 0, 100))
        f.addRow("Pauze tussen acties", self.spin("pause_ms", 0, 5000, " ms", plan=False))
        f.addRow("Voorkeur", self.combo("priority", PRIORITIES))
        f.addRow("Bijsnijden links / boven / rechts / onder (%)", self._crop_row())
        keys = list(HOTKEYS)
        f.addRow("Sneltoets pauze", self.combo("hk_pause", keys, plan=False))
        f.addRow("Sneltoets hervatten", self.combo("hk_resume", keys, plan=False))
        f.addRow("Sneltoets noodstop", self.combo("hk_stop", keys, plan=False))
        f.addRow("Sneltoets kalibreren", self.combo("hk_calib", keys, plan=False))
        l.addLayout(f)
        v.addWidget(c)
        note = QLabel("Wijzigingen worden automatisch opgeslagen. Wijzig je plan-instellingen, dan wordt de preview opnieuw berekend bij Start.")
        note.setObjectName("dim")
        note.setWordWrap(True)
        v.addWidget(note)
        v.addStretch()
        return page

    def _crop_row(self):
        w = QWidget()
        r = QHBoxLayout(w)
        r.setContentsMargins(0, 0, 0, 0)
        for k in ("crop_l", "crop_t", "crop_r", "crop_b"):
            r.addWidget(self.spin(k, 0, 45, " %"))
        return w

    def _history_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(24, 20, 24, 20)
        t = QLabel("Tekenhistorie")
        t.setObjectName("h1")
        v.addWidget(t)
        self.hist = QListWidget()
        self.hist.setIconSize(QSize(72, 72))
        self.hist.setSpacing(4)
        self.hist.itemDoubleClicked.connect(lambda _: self.open_project())
        v.addWidget(self.hist, 1)
        r = QHBoxLayout()
        b1 = QPushButton("Project openen / hervatten")
        b1.setObjectName("primary")
        b1.clicked.connect(self.open_project)
        b2 = QPushButton("Verwijderen")
        b2.clicked.connect(self.del_project)
        r.addWidget(b1)
        r.addWidget(b2)
        r.addStretch()
        v.addLayout(r)
        return page

    # ---------- instellingen ----------
    def collect(self):
        for k, w in self.w.items():
            self.s[k] = w.currentText() if isinstance(w, QComboBox) else w.value()
        return self.s

    def apply_settings(self, s):
        for k, w in self.w.items():
            if k in s:
                w.blockSignals(True)
                w.setCurrentText(s[k]) if isinstance(w, QComboBox) else w.setValue(int(s[k]))
                w.blockSignals(False)
        self.lbl_detail.setText(str(self.w["detail"].value()))
        self.s.update({k: v for k, v in s.items() if k not in self.w})
        self.update_keys_label()

    def update_keys_label(self):
        self.lbl_keys.setText(f"Sneltoetsen: {self.w['hk_pause'].currentText()} pauze · {self.w['hk_resume'].currentText()} hervat · {self.w['hk_stop'].currentText()} noodstop")

    def mark_dirty(self, *_):
        self.dirty = True
        self.update_keys_label()
        if self.plan is not None and self.state == "idle":
            self.info.setText("Instellingen gewijzigd – klik op 'Analyseer / preview' om het voorbeeld te vernieuwen.")

    def update_estimate(self, *_):
        self.update_keys_label()
        if self.plan:
            self.show_summary()

    def profiles(self):
        p = dict(DEFAULT_PROFILES)
        p.update(self.s.get("profiles", {}))
        return p

    def refresh_profiles(self):
        self.cb_prof.clear()
        self.cb_prof.addItem("— kies profiel —")
        self.cb_prof.addItems(list(self.profiles()))

    def load_profile(self, i):
        if i <= 0:
            return
        self.apply_settings(self.profiles()[self.cb_prof.currentText()])
        self.mark_dirty()

    def save_profile(self):
        name, ok = QInputDialog.getText(self, "Profiel opslaan", "Naam van het profiel:")
        if ok and name.strip():
            self.collect()
            self.s.setdefault("profiles", {})[name.strip()] = {k: self.s[k] for k in PROFILE_KEYS}
            save_settings(self.s)
            self.refresh_profiles()
            self.log_msg(f"Profiel '{name.strip()}' opgeslagen.")

    # ---------- afbeelding ----------
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            self.load_image_path(u.toLocalFile())
            break

    def choose_image(self):
        p, _ = QFileDialog.getOpenFileName(self, "Kies afbeelding", self.s.get("last_dir", ""), "Afbeeldingen (*.png *.jpg *.jpeg *.bmp *.webp)")
        if p:
            self.load_image_path(p)

    def load_image_path(self, p):
        if not p.lower().endswith(EXTS):
            return QMessageBox.warning(self, "Bestandstype", "Alleen PNG, JPG, JPEG, BMP en WEBP worden ondersteund.")
        try:
            self.image = load_image(p)
        except Exception as e:
            return QMessageBox.critical(self, "Fout", f"Kon afbeelding niet laden:\n{e}")
        self.image_path, self.s["last_dir"] = p, os.path.dirname(p)
        self.plan = self.preview = self.resume_pos = None
        self.pid, self.dirty = new_id(), True
        self.v_orig.set_pix(np_to_pix(self.image))
        self.v_prev.clear_pix("Analyseren…")
        self.log_msg(f"Afbeelding geladen: {os.path.basename(p)} ({self.image.shape[1]}x{self.image.shape[0]})")
        self.analyze()

    # ---------- analyse ----------
    def analyze(self, then_start=False):
        if self.image is None:
            return QMessageBox.information(self, "PaintMaster Pro", "Kies eerst een afbeelding.")
        if self.analyzer and self.analyzer.isRunning():
            return
        self.collect()
        self.pending_start = then_start
        self.b_an.setEnabled(False)
        self.info.setText("Afbeelding wordt geanalyseerd…")
        self.analyzer = AnalysisWorker(self.image, self.s)
        self.analyzer.done.connect(self.on_plan)
        self.analyzer.failed.connect(self.on_plan_failed)
        self.analyzer.start()

    def on_plan(self, plan, prev):
        self.plan, self.preview, self.dirty, self.resume_pos = plan, prev, False, None
        self.v_prev.set_pix(np_to_pix(prev))
        self.b_an.setEnabled(True)
        self.show_summary()
        for w in plan.warnings:
            self.log_msg("⚠ " + w)
        self.save_current("Geanalyseerd")
        self.set_buttons()
        if self.pending_start:
            self.pending_start = False
            self.start()

    def on_plan_failed(self, msg):
        self.b_an.setEnabled(True)
        self.pending_start = False
        self.info.setText("Analyse mislukt.")
        self.log_msg("Analyse mislukt: " + msg)
        QMessageBox.critical(self, "Analyse mislukt", msg)

    def show_summary(self):
        p, s = self.plan, self.collect()
        est = estimate_seconds(p, s["speed"], s["pause_ms"], s["priority"])
        txt = f"≈ {p.actions:,} tekenacties · {len(p.strokes):,} lijnen · {len(p.colors)} kleur(en) · geschatte tijd {fmt_t(est)}"
        if p.warnings:
            txt += "\n⚠ " + " ".join(p.warnings)
        self.info.setText(txt)
        self.m["acties"].setText(f"0 / {p.actions:,}")
        self.m["rest"].setText(fmt_t(est))
        self.m["modus"].setText(p.mode)

    # ---------- Paint ----------
    def refresh_paint(self):
        cur = self.cb_win.currentData()
        self.cb_win.clear()
        for hwnd, title in P.list_paint_windows():
            self.cb_win.addItem(title, hwnd)
        i = self.cb_win.findData(cur)
        if i >= 0:
            self.cb_win.setCurrentIndex(i)
        self.update_paint_status()

    def open_paint(self):
        try:
            P.open_paint()
            self.log_msg("Paint wordt geopend…")
            QTimer.singleShot(2500, self.refresh_paint)
        except Exception as e:
            QMessageBox.warning(self, "Paint", f"Paint kon niet worden geopend:\n{e}")

    def hwnd(self):
        return self.cb_win.currentData()

    def calib(self):
        return self.s.get("calib")

    def update_paint_status(self):
        h = self.hwnd()
        if h and P.is_alive(h):
            txt = "Paint: verbonden"
            self.lbl_paint.setStyleSheet("color:#6ee7a0")
        else:
            txt = "Paint: niet gevonden (open Paint en klik ↻)"
            self.lbl_paint.setStyleSheet("color:#ff8a8a")
        self.lbl_paint.setText(txt)
        self.m["paint"].setText("OK" if h and P.is_alive(h) else "niet verbonden")
        c = self.calib()
        self.lbl_calib.setText("Kalibratie: gereed" if c else "Kalibratie: ontbreekt (klik op Kalibreren)")
        self.lbl_calib.setStyleSheet("color:#6ee7a0" if c else "color:#ffd166")

    def calibrate(self):
        h = self.hwnd()
        if not h or not P.is_alive(h):
            return QMessageBox.information(self, "Kalibreren", "Open Paint en selecteer het Paint-venster in de lijst.")
        P.bring_to_front(h)
        dlg = Calibrator(self, HOTKEYS[self.w["hk_calib"].currentText()], self.w["hk_calib"].currentText(), h)
        dlg.done.connect(self.on_calibrated)
        dlg.show()

    def on_calibrated(self, d):
        self.s["calib"] = d
        save_settings(self.collect())
        self.log_msg("Kalibratie opgeslagen.")
        self.update_paint_status()

    # ---------- tekenen ----------
    def start(self):
        if self.worker and self.worker.isRunning():
            return
        if self.plan is None and self.image is None:
            return QMessageBox.information(self, "PaintMaster Pro", "Kies eerst een afbeelding.")
        h = self.hwnd()
        if not h or not P.is_alive(h):
            return QMessageBox.warning(self, "Paint", "Paint is niet verbonden. Open Paint en selecteer het venster.")
        if not self.calib():
            return QMessageBox.warning(self, "Kalibratie", "Kalibreer eerst (knop 'Kalibreren').")
        if P.get_rect(h) != tuple(self.calib()["win_rect"]):
            if max(abs(a - b) for a, b in zip(P.get_rect(h), self.calib()["win_rect"])) > 2:
                return QMessageBox.warning(self, "Kalibratie", "Het Paint-venster staat niet meer op de gekalibreerde plek/grootte. Kalibreer opnieuw.")
        if (self.plan is None or self.dirty) and self.image is not None:
            return self.analyze(then_start=True)
        start = (0, 0, 0)
        if self.resume_pos and self.resume_pos[2] > 0:
            pct = int(100 * self.resume_pos[2] / max(1, self.plan.actions))
            a = QMessageBox.question(self, "Hervatten", f"Doorgaan vanaf {pct}%? (Nee = opnieuw beginnen)", QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if a == QMessageBox.Cancel:
                return
            if a == QMessageBox.Yes:
                start = tuple(self.resume_pos)
        self.begin(start)

    def color_test(self):
        c, h = self.calib(), self.hwnd()
        if not c or not h or not P.is_alive(h):
            return QMessageBox.information(self, "Kleurtest", "Verbind Paint en kalibreer eerst.")
        if "pal2" not in c:
            return QMessageBox.information(self, "Kleurtest", "Kalibreer opnieuw (de kalibratie heeft nu 6 stappen).")
        if self.worker and self.worker.isRunning():
            return
        st = [(i, np.array([[100, 30 + i * 27], [700, 30 + i * 27]], np.int32)) for i in range(20)]
        self.log_msg("Kleurtest: 20 lijnen van boven naar onder: " + ", ".join(PALETTE_NAMES))
        self.begin((0, 0, 0), Plan(800, 600, st, "Kleurtest", 1))

    def begin(self, start, plan=None):
        s = self.collect()
        save_settings(s)
        self.testing = plan is not None
        self.run_plan = plan or self.plan
        est = estimate_seconds(self.run_plan, s["speed"], s["pause_ms"], s["priority"])
        self.worker = DrawWorker(self.run_plan, dict(s), self.hwnd(), self.calib(), start, est)
        self.worker.progress.connect(self.on_progress)
        self.worker.position.connect(lambda a, b, c: setattr(self, "pos", (a, b, c)))
        self.worker.state.connect(self.on_state)
        self.worker.message.connect(self.log_msg)
        self.worker.start()
        self.state = "running"
        self.m["modus"].setText(self.run_plan.mode)
        self.set_buttons()

    def pause(self):
        if self.worker and self.worker.isRunning():
            self.worker.request_pause()

    def resume(self):
        if self.worker and self.worker.isRunning():
            self.worker.request_resume()

    def stop(self):
        if self.worker and self.worker.isRunning():
            self.worker.request_stop()
            self.log_msg("Stop/noodstop gegeven.")

    def on_progress(self, done, total, el, rem, si, n, color):
        self.anim.stop()
        self.anim.setStartValue(self.bar.value())
        self.anim.setEndValue(int(1000 * done / max(1, total)))
        self.anim.start()
        self.bar.setFormat(f"{100 * done / max(1, total):.1f}%")
        self.m["acties"].setText(f"{done:,} / {total:,}")
        self.m["tijd"].setText(fmt_t(el))
        self.m["rest"].setText(fmt_t(rem))
        self.m["fase"].setText(f"{self.run_plan.mode}: lijn {min(si + 1, n):,} van {n:,}")
        r, g, b = PALETTE[color]
        self.m["kleur"].setText(PALETTE_NAMES[color])
        self.m["kleur"].setStyleSheet(f"border-left:14px solid rgb({r},{g},{b});padding-left:6px")

    def on_state(self, st):
        names = {"running": "Bezig", "paused": "Gepauzeerd", "stopped": "Gestopt", "done": "Voltooid", "error": "Fout"}
        self.state = "running" if st in ("running", "paused") else "idle"
        self.pstate = st
        self.m["status"].setText(names.get(st, st))
        self.log_msg(f"Status: {names.get(st, st)}")
        if getattr(self, "testing", False):
            if st in ("stopped", "done", "error"):
                self.bar.setValue(1000 if st == "done" else self.bar.value())
            self.set_buttons()
            return
        if st in ("stopped", "error"):
            self.resume_pos = self.pos if self.pos[2] > 0 else None
        if st == "done":
            self.resume_pos = None
        if st in ("paused", "stopped", "done", "error"):
            self.save_current(names[st])
        if st == "done":
            self.bar.setValue(1000)
        self.set_buttons()

    def set_buttons(self):
        running = self.state == "running"
        paused = running and getattr(self, "pstate", "") == "paused"
        self.btn["start"].setEnabled(not running)
        self.btn["pause"].setEnabled(running and not paused)
        self.btn["resume"].setEnabled(paused)
        self.btn["stop"].setEnabled(running)
        self.btn["estop"].setEnabled(running)

    def poll_keys(self):
        for key, fn in (("hk_pause", self.pause), ("hk_resume", self.resume), ("hk_stop", self.stop)):
            vk = HOTKEYS.get(self.w[key].currentText())
            d = P.key_down(vk)
            if d and not self.prev_keys.get(key) and self.worker and self.worker.isRunning():
                fn()
            self.prev_keys[key] = d

    # ---------- opslaan / historie ----------
    def save_current(self, status):
        if not self.plan or not self.pid:
            return
        try:
            s = self.collect()
            pct = int(100 * (self.pos[2] if status != "Geanalyseerd" else 0) / max(1, self.plan.actions))
            if status == "Voltooid":
                pct = 100
            save_project(self.pid, self.plan, s, self.image_path, self.pos if status != "Geanalyseerd" else (0, 0, 0), status)
            thumb = make_thumb(self.pid, self.image if self.image is not None else self.preview)
            upsert_history({"id": self.pid, "name": os.path.basename(self.image_path or "project"), "image": self.image_path,
                            "mode": self.plan.mode, "speed": s["speed"], "detail": s["detail"], "status": status, "progress": pct,
                            "date": time.strftime("%Y-%m-%d %H:%M"), "thumb": thumb})
        except Exception:
            log.exception("project opslaan mislukt")

    def refresh_history(self):
        self.hist.clear()
        for e in load_history():
            it = QListWidgetItem(QIcon(e.get("thumb", "")), f"{e['name']}\n{e['mode']} · {e['speed']} · detail {e.get('detail', '')}\n{e['status']} ({e.get('progress', 0)}%) · {e['date']}")
            it.setData(Qt.UserRole, e["id"])
            self.hist.addItem(it)

    def open_project(self):
        it = self.hist.currentItem()
        if not it:
            return
        pid = it.data(Qt.UserRole)
        try:
            d = load_project(project_path(pid))
        except Exception as e:
            return QMessageBox.warning(self, "Project", f"Project kon niet worden geladen:\n{e}")
        self.pid, self.plan, self.dirty = pid, Plan.from_dict(d["plan"]), False
        self.image_path = d.get("image")
        self.image = None
        if self.image_path and os.path.exists(self.image_path):
            try:
                self.image = load_image(self.image_path)
            except Exception:
                pass
        self.apply_settings({k: v for k, v in d["settings"].items() if k != "calib"})
        self.preview = render_preview(self.plan)
        self.v_prev.set_pix(np_to_pix(self.preview))
        if self.image is not None:
            self.v_orig.set_pix(np_to_pix(self.image))
        else:
            self.v_orig.clear_pix("Originele afbeelding niet meer gevonden")
        pos = d.get("position", [0, 0, 0])
        self.resume_pos = tuple(pos) if pos and pos[2] > 0 and d.get("status") != "Voltooid" else None
        self.pos = tuple(pos)
        self.show_summary()
        self.goto(0)
        self.log_msg(f"Project geopend ({d.get('status')}). Druk op Start om " + ("verder te gaan." if self.resume_pos else "te tekenen."))

    def del_project(self):
        it = self.hist.currentItem()
        if it and QMessageBox.question(self, "Verwijderen", "Dit project verwijderen?") == QMessageBox.Yes:
            delete_history(it.data(Qt.UserRole))
            self.refresh_history()

    # ---------- diversen ----------
    def log_msg(self, text):
        log.info(text)
        self.log_box.appendPlainText(f"[{time.strftime('%H:%M:%S')}] {text}")

    def closeEvent(self, e):
        try:
            save_settings(self.collect())
        except Exception:
            pass
        if self.worker and self.worker.isRunning():
            self.worker.request_stop()
            self.worker.wait(3000)
        e.accept()
