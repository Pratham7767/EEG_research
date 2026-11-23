"""Real monitor size, and covering it.

Tk under customtkinter reports the *scaled* screen size on Windows (1536x864 on a 1920x1080 display at
125 %) although the process is DPI-aware, so "-fullscreen" and winfo_screenwidth/height cover only 80 %
of the screen. Windows' monitor info is in real pixels, which is what wm_geometry uses.
"""
import ctypes
import sys
import tkinter as tk


def monitor_rect(win):
    """(x, y, width, height) of the monitor showing `win`, in real pixels."""
    if sys.platform == "win32":
        try:
            from ctypes import wintypes

            class MONITORINFO(ctypes.Structure):
                _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                            ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

            user32 = ctypes.windll.user32
            user32.MonitorFromWindow.restype = ctypes.c_void_p
            user32.MonitorFromWindow.argtypes = [ctypes.c_void_p, wintypes.DWORD]
            user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MONITORINFO)]
            win.update_idletasks()
            hwnd = int(win.wm_frame(), 16)
            monitor = user32.MonitorFromWindow(hwnd, 2)                  # MONITOR_DEFAULTTONEAREST
            info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
            if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                r = info.rcMonitor
                return r.left, r.top, r.right - r.left, r.bottom - r.top
        except Exception:
            pass
    return 0, 0, win.winfo_screenwidth(), win.winfo_screenheight()


def window_rect(win):
    """(x, y, width, height) of the window as Windows sees it (for checks); Tk values elsewhere."""
    if sys.platform == "win32":
        from ctypes import wintypes
        r = wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(int(win.wm_frame(), 16), ctypes.byref(r))
        return r.left, r.top, r.right - r.left, r.bottom - r.top
    return win.winfo_rootx(), win.winfo_rooty(), win.winfo_width(), win.winfo_height()


def cover(win, rect=None):
    """Borderless, on top, exactly covering the monitor (plain Tk calls: no customtkinter scaling)."""
    x, y, w, h = rect or monitor_rect(win)
    tk.Wm.wm_overrideredirect(win, True)
    tk.Wm.wm_geometry(win, f"{w}x{h}+{x}+{y}")
    return x, y, w, h
