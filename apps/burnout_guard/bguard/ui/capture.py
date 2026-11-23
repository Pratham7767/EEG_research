"""Capture a Tk window's own pixels with Win32 PrintWindow (used by --selftest --screenshots).

Unlike a screen grab, this renders only the window itself, so overlapping windows, the Alt+Tab
switcher or notifications can never end up in the screenshots.
"""
import ctypes
from ctypes import wintypes

from PIL import Image

PW_CLIENTONLY, PW_RENDERFULLCONTENT = 0x1, 0x2


class _BitmapInfoHeader(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


def _api():
    user32, gdi32 = ctypes.WinDLL("user32"), ctypes.WinDLL("gdi32")
    H = ctypes.c_void_p
    user32.GetClientRect.argtypes = [H, ctypes.POINTER(wintypes.RECT)]
    user32.GetDC.argtypes, user32.GetDC.restype = [H], H
    user32.ReleaseDC.argtypes = [H, H]
    user32.PrintWindow.argtypes, user32.PrintWindow.restype = [H, H, wintypes.UINT], wintypes.BOOL
    gdi32.CreateCompatibleDC.argtypes, gdi32.CreateCompatibleDC.restype = [H], H
    gdi32.CreateCompatibleBitmap.argtypes, gdi32.CreateCompatibleBitmap.restype = [H, ctypes.c_int, ctypes.c_int], H
    gdi32.SelectObject.argtypes, gdi32.SelectObject.restype = [H, H], H
    gdi32.GetDIBits.argtypes = [H, H, wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
                                ctypes.POINTER(_BitmapInfoHeader), wintypes.UINT]
    gdi32.DeleteObject.argtypes = [H]
    gdi32.DeleteDC.argtypes = [H]
    return user32, gdi32


def grab_window(win):
    """Client area of a Tk toplevel as a PIL image."""
    user32, gdi32 = _api()
    hwnd = int(win.wm_frame(), 16)
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    hdc = user32.GetDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    old = gdi32.SelectObject(mdc, bmp)
    try:
        if not user32.PrintWindow(hwnd, mdc, PW_CLIENTONLY | PW_RENDERFULLCONTENT):
            raise OSError("PrintWindow failed")
        header = _BitmapInfoHeader(ctypes.sizeof(_BitmapInfoHeader), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(header), 0)
        return Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)
    finally:
        gdi32.SelectObject(mdc, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mdc)
        user32.ReleaseDC(hwnd, hdc)
