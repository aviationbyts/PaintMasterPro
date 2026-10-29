import json, os, copy

APP_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "PaintMasterPro")
PROJECT_DIR = os.path.join(APP_DIR, "projects")
THUMB_DIR = os.path.join(APP_DIR, "thumbs")
for _d in (APP_DIR, PROJECT_DIR, THUMB_DIR):
    os.makedirs(_d, exist_ok=True)
SETTINGS_FILE = os.path.join(APP_DIR, "settings.json")
HISTORY_FILE = os.path.join(APP_DIR, "history.json")
LOG_FILE = os.path.join(APP_DIR, "log.txt")

# Standaardpalet Microsoft Paint (RGB), 2 rijen x 10 kolommen
PALETTE = [(0, 0, 0), (127, 127, 127), (136, 0, 21), (237, 28, 36), (255, 127, 39), (255, 242, 0),
           (34, 177, 76), (0, 162, 232), (63, 72, 204), (163, 73, 164),
           (255, 255, 255), (195, 195, 195), (185, 122, 87), (255, 174, 201), (255, 201, 14),
           (239, 228, 176), (181, 230, 29), (153, 217, 234), (112, 146, 190), (200, 191, 231)]
PALETTE_NAMES = ["Zwart", "Donkergrijs", "Donkerrood", "Rood", "Oranje", "Geel", "Groen", "Turkoois", "Indigo",
                 "Paars", "Wit", "Lichtgrijs", "Bruin", "Roze", "Goud", "Lichtgeel", "Limoen", "Lichtturkoois",
                 "Blauwgrijs", "Lavendel"]
WHITE = 10

MODES = ["Quick Sketch", "Precision Drawing", "Full Color", "Artist Mode", "Pixel Art", "Outline Only", "Blueprint"]
# step = pixels per muisstap, delay = seconden per stap, lift = pauze na losse lijn, color = pauze bij kleurwissel
SPEEDS = {
    "Supersnel": dict(step=12.0, delay=0.0, lift=0.0, jitter=0.0, color=0.05),
    "Snel": dict(step=6.0, delay=0.0004, lift=0.004, jitter=0.0, color=0.1),
    "Normaal": dict(step=4.0, delay=0.002, lift=0.02, jitter=0.0, color=0.25),
    "Rustig": dict(step=2.5, delay=0.005, lift=0.08, jitter=0.0, color=0.5),
    "Realistisch handmatig": dict(step=2.0, delay=0.009, lift=0.25, jitter=0.6, color=0.9),
}
PRIORITIES = ["Snelheid", "Balans", "Nauwkeurigheid"]
PRIO_EPS = {"Snelheid": 1.5, "Balans": 1.0, "Nauwkeurigheid": 0.7}
PRIO_STEP = {"Snelheid": 1.5, "Balans": 1.0, "Nauwkeurigheid": 0.7}
HOTKEYS = {f"F{i}": 0x6F + i for i in range(1, 13)}
HOTKEYS.update({"ESC": 0x1B, "PAUSE": 0x13, "INSERT": 0x2D, "HOME": 0x24, "END": 0x23})

DEFAULTS = {
    "mode": "Precision Drawing", "speed": "Normaal", "detail": 55, "line_width": 1,
    "canvas_w": 800, "canvas_h": 600, "max_colors": 8, "edge_strength": 55, "shadow": 40,
    "pause_ms": 0, "priority": "Balans", "crop_l": 0, "crop_t": 0, "crop_r": 0, "crop_b": 0,
    "hk_pause": "F6", "hk_resume": "F7", "hk_stop": "ESC", "hk_calib": "F8",
    "calib": None, "profiles": {}, "last_dir": "",
}
PLAN_KEYS = ["mode", "detail", "line_width", "canvas_w", "canvas_h", "max_colors", "edge_strength", "shadow",
             "priority", "crop_l", "crop_t", "crop_r", "crop_b"]
PROFILE_KEYS = ["mode", "speed", "detail", "line_width", "max_colors", "edge_strength", "shadow", "priority"]
DEFAULT_PROFILES = {
    "Vliegtuig": dict(mode="Blueprint", speed="Normaal", detail=60, line_width=1, max_colors=4, edge_strength=60, shadow=30, priority="Balans"),
    "Logo": dict(mode="Full Color", speed="Snel", detail=70, line_width=2, max_colors=6, edge_strength=65, shadow=0, priority="Nauwkeurigheid"),
    "Foto": dict(mode="Full Color", speed="Snel", detail=45, line_width=2, max_colors=12, edge_strength=40, shadow=40, priority="Snelheid"),
    "Schets": dict(mode="Artist Mode", speed="Realistisch handmatig", detail=60, line_width=1, max_colors=2, edge_strength=50, shadow=55, priority="Balans"),
    "Pixelart": dict(mode="Pixel Art", speed="Snel", detail=40, line_width=2, max_colors=10, edge_strength=50, shadow=0, priority="Balans"),
}


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def load_settings():
    s = copy.deepcopy(DEFAULTS)
    s.update(load_json(SETTINGS_FILE, {}))
    return s


def save_settings(s):
    save_json(SETTINGS_FILE, s)
