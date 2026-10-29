import gzip, json, os, time, uuid
import cv2
from .config import PROJECT_DIR, THUMB_DIR, HISTORY_FILE, load_json, save_json, PROFILE_KEYS
from .analysis import Plan


def new_id():
    return time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]


def project_path(pid):
    return os.path.join(PROJECT_DIR, pid + ".pmproj")


def save_project(pid, plan, settings, image_path, position, status):
    data = {"version": 1, "image": image_path, "settings": {k: v for k, v in settings.items() if k not in ("profiles",)},
            "plan": plan.to_dict(), "position": list(position), "status": status, "saved": time.strftime("%Y-%m-%d %H:%M:%S")}
    p = project_path(pid)
    with gzip.open(p + ".tmp", "wt", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(p + ".tmp", p)


def load_project(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def load_history():
    return load_json(HISTORY_FILE, [])


def upsert_history(entry):
    h = load_history()
    for i, e in enumerate(h):
        if e["id"] == entry["id"]:
            h[i].update(entry)
            break
    else:
        h.insert(0, entry)
    save_json(HISTORY_FILE, h[:200])


def delete_history(pid):
    save_json(HISTORY_FILE, [e for e in load_history() if e["id"] != pid])
    for p in (project_path(pid), os.path.join(THUMB_DIR, pid + ".png")):
        try:
            os.remove(p)
        except OSError:
            pass


def make_thumb(pid, img_bgr):
    h, w = img_bgr.shape[:2]
    s = 96 / max(h, w)
    t = cv2.resize(img_bgr, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA)
    path = os.path.join(THUMB_DIR, pid + ".png")
    cv2.imencode(".png", t)[1].tofile(path)
    return path
