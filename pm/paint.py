"""Windows-muisautomatisering (SendInput/ctypes) en Paint-detectie."""
import sys, os, time, ctypes, subprocess

IS_WIN = sys.platform == "win32"

if IS_WIN:
    from ctypes import wintypes as wt
    user32 = ctypes.windll.user32
    winmm = ctypes.windll.winmm
    WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    user32.EnumWindows.argtypes = [WNDENUMPROC, wt.LPARAM]
    user32.IsWindow.argtypes = [wt.HWND]
    user32.IsIconic.argtypes = [wt.HWND]
    user32.IsWindowVisible.argtypes = [wt.HWND]
    user32.GetWindowTextLengthW.argtypes = [wt.HWND]
    user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
    user32.SetForegroundWindow.argtypes = [wt.HWND]
    user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
    user32.GetForegroundWindow.restype = wt.HWND
    user32.GetAncestor.argtypes = [wt.HWND, wt.UINT]
    user32.GetAncestor.restype = wt.HWND

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD), ("dwFlags", wt.DWORD),
                    ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wt.DWORD), ("u", _U)]


def _need_win():
    if not IS_WIN:
        raise RuntimeError("Paint-automatisering werkt alleen op Windows.")


def list_paint_windows():
    if not IS_WIN:
        return []
    found = []

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                t = buf.value
                tl = t.lower()
                if "paint" in tl and "paintmaster" not in tl and "3d" not in tl:
                    found.append((int(hwnd), t))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found


def open_paint():
    _need_win()
    try:
        subprocess.Popen(["mspaint.exe"])
    except Exception:
        os.startfile("mspaint")


def is_alive(hwnd):
    return IS_WIN and bool(user32.IsWindow(hwnd)) and not user32.IsIconic(hwnd)


def get_rect(hwnd):
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return (r.left, r.top, r.right, r.bottom)


def foreground_ok(hwnd):
    fg = user32.GetForegroundWindow()
    if not fg:
        return False
    return fg == hwnd or user32.GetAncestor(fg, 2) == user32.GetAncestor(hwnd, 2)


def bring_to_front(hwnd):
    _need_win()
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)


def cursor_pos():
    if not IS_WIN:
        return (0, 0)
    p = wt.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return (p.x, p.y)


def key_down(vk):
    return IS_WIN and bool(user32.GetAsyncKeyState(vk) & 0x8000)


def set_cursor(x, y):
    """Echte absolute muisbeweging via SendInput (Paint registreert dit betrouwbaarder dan SetCursorPos)."""
    vx, vy = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
    vw, vh = max(2, user32.GetSystemMetrics(78)), max(2, user32.GetSystemMetrics(79))
    nx = int(round((x - vx) * 65535 / (vw - 1)))
    ny = int(round((y - vy) * 65535 / (vh - 1)))
    inp = INPUT(0, _U(MOUSEINPUT(nx, ny, 0, 0x0001 | 0x8000 | 0x4000, 0, 0)))
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def _mouse(flag):
    inp = INPUT(0, _U(MOUSEINPUT(0, 0, 0, flag, 0, 0)))
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def mouse_down():
    _mouse(0x0002)


def mouse_up():
    if IS_WIN:
        _mouse(0x0004)


def click(x, y):
    set_cursor(x, y)
    time.sleep(0.05)
    mouse_down()
    time.sleep(0.04)
    mouse_up()
    time.sleep(0.05)


def begin_timer():
    if IS_WIN:
        winmm.timeBeginPeriod(1)


def end_timer():
    if IS_WIN:
        winmm.timeEndPeriod(1)
