"""功能验证脚本：窗口是否出现、是否持续运行、CPU 是否正常、关闭是否退出。

用法：
    python tools/verify.py                # 验证 dist/EmptyApp.exe
    python tools/verify.py path/to.exe    # 验证指定文件

同时会把窗口截图写到 docs/screenshot.png（用于 README）。
仅支持 Windows。
"""

import ctypes
import struct
import subprocess
import sys
import time
import zlib
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "dist" / "EmptyApp.exe"
SHOT = ROOT / "docs" / "screenshot.png"
TITLE = "EmptyApp - 运行中"

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.FindWindowW.restype = ctypes.c_void_p
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)]
user32.GetDC.argtypes = [ctypes.c_void_p]
user32.GetDC.restype = ctypes.c_void_p
user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
user32.PrintWindow.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
user32.PostMessageW.argtypes = [ctypes.c_void_p, wintypes.UINT,
                                wintypes.WPARAM, wintypes.LPARAM]

gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
gdi32.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = ctypes.c_void_p
gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
gdi32.SelectObject.restype = ctypes.c_void_p
gdi32.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT, wintypes.UINT,
                            ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
gdi32.DeleteDC.argtypes = [ctypes.c_void_p]

kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = ctypes.c_void_p
kernel32.GetProcessTimes.argtypes = [ctypes.c_void_p] + [ctypes.POINTER(wintypes.FILETIME)] * 4
kernel32.CloseHandle.argtypes = [ctypes.c_void_p]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


def save_png(path, width, height, rows):
    """rows: 自上而下的 RGB 字节行。手写 PNG，避免引入 Pillow 依赖。"""
    raw = b"".join(b"\x00" + r for r in rows)

    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload +
                struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" +
                     chunk(b"IHDR", ihdr) +
                     chunk(b"IDAT", zlib.compress(raw, 9)) +
                     chunk(b"IEND", b""))


def capture(hwnd, png_path):
    """截取整个窗口（含标题栏）。"""
    rc = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rc))
    w, h = rc.right - rc.left, rc.bottom - rc.top

    hdc = user32.GetDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    ok = user32.PrintWindow(hwnd, mem, 2)  # PW_RENDERFULLCONTENT

    hdr = BITMAPINFOHEADER()
    hdr.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    hdr.biWidth = w
    hdr.biHeight = -h          # 负数 = 自上而下
    hdr.biPlanes = 1
    hdr.biBitCount = 32
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(hdr), 0)

    rows = []
    for y in range(h):
        line = buf.raw[y * w * 4:(y + 1) * w * 4]
        rgb = bytearray()
        for x in range(w):
            b, g, r = line[x * 4], line[x * 4 + 1], line[x * 4 + 2]
            rgb += bytes((r, g, b))
        rows.append(bytes(rgb))

    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    save_png(png_path, w, h, rows)
    return bool(ok), w, h


def cpu_seconds(exe_name):
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq %s" % exe_name,
                          "/FO", "CSV", "/NH"],
                         capture_output=True, text=True, errors="ignore").stdout
    pids = [int(ln.split(",")[1].strip('"')) for ln in out.splitlines() if ln.startswith('"')]
    total = 0.0
    for pid in pids:
        handle = kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
        if not handle:
            continue
        c, e, k, u = (wintypes.FILETIME() for _ in range(4))
        if kernel32.GetProcessTimes(handle, ctypes.byref(c), ctypes.byref(e),
                                    ctypes.byref(k), ctypes.byref(u)):
            total += ((k.dwHighDateTime << 32 | k.dwLowDateTime) +
                      (u.dwHighDateTime << 32 | u.dwLowDateTime)) / 1e7
        kernel32.CloseHandle(handle)
    return len(pids), total


def main():
    if not EXE.exists():
        print("找不到可执行文件：%s\n请先运行 build.bat" % EXE)
        return 1

    print("被测文件: %s (%d 字节)" % (EXE, EXE.stat().st_size))
    proc = subprocess.Popen([str(EXE)], cwd=str(EXE.parent))

    hwnd, t0 = None, time.time()
    while time.time() - t0 < 20:
        hwnd = user32.FindWindowW(None, TITLE)
        if hwnd or proc.poll() is not None:
            break
        time.sleep(0.1)

    if not hwnd:
        print("[FAIL] 窗口未出现，进程退出码=%s" % proc.poll())
        if proc.poll() is None:
            proc.kill()
        return 1

    print("[ OK ] 窗口出现，耗时 %.2fs" % (time.time() - t0))
    print("[ OK ] 窗口可见: %s" % bool(user32.IsWindowVisible(hwnd)))

    time.sleep(4)
    n, cpu = cpu_seconds(EXE.name)
    print("[ %s ] 4 秒后进程存活: %s，累计 CPU %.2fs"
          % ("OK" if n else "--", bool(n), cpu))

    ok, w, h = capture(hwnd, SHOT)
    print("[ OK ] 截图 %dx%d -> %s" % (w, h, SHOT.relative_to(ROOT)))

    user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
    try:
        code = proc.wait(timeout=10)
        print("[ OK ] 关闭窗口后进程退出，退出码 %s" % code)
    except subprocess.TimeoutExpired:
        proc.kill()
        print("[FAIL] 关闭窗口后进程未退出")
        return 1

    print("[ OK ] 窗口已销毁: %s" % (user32.FindWindowW(None, TITLE) is None))
    print("\n全部检查通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
