"""环境容错测试：在 %TEMP% 不可用的环境下验证程序仍能启动。

这是为了验证「原生 exe 不依赖临时目录解压」这一特性，
用打包器（PyInstaller / Nuitka onefile）产出的程序在此场景下会直接报
"Could not create temporary directory!" 而无法启动。

用法：
    python tools/test_tmp.py                # 测试 dist/EmptyApp.exe
    python tools/test_tmp.py path/to.exe    # 测试指定文件
"""

import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "dist" / "EmptyApp.exe"
TITLE = "EmptyApp - 运行中"

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.FindWindowW.restype = ctypes.c_void_p
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
user32.PostMessageW.argtypes = [ctypes.c_void_p, wintypes.UINT,
                                wintypes.WPARAM, wintypes.LPARAM]


def run_case(name, env_override):
    env = os.environ.copy()
    env.update(env_override)
    proc = subprocess.Popen([str(EXE)], env=env, cwd=str(EXE.parent))

    hwnd, t0 = None, time.time()
    while time.time() - t0 < 15:
        hwnd = user32.FindWindowW(None, TITLE)
        if hwnd or proc.poll() is not None:
            break
        time.sleep(0.1)

    if hwnd:
        print("  [ OK ] %-24s 窗口 %.2fs 出现，可见=%s"
              % (name, time.time() - t0, bool(user32.IsWindowVisible(hwnd))))
        time.sleep(1.0)
        user32.PostMessageW(hwnd, 0x0010, 0, 0)
        try:
            print("  [ OK ] %-24s 关闭后退出码 %s" % ("", proc.wait(timeout=10)))
        except subprocess.TimeoutExpired:
            proc.kill()
            print("  [FAIL] %-24s 关闭后未退出" % "")
        return True

    print("  [FAIL] %-24s 未出现窗口，进程退出码=%s" % (name, proc.poll()))
    if proc.poll() is None:
        proc.kill()
    return False


def main():
    if not EXE.exists():
        print("找不到可执行文件：%s\n请先运行 build.bat" % EXE)
        return 1

    print("被测文件: %s\n" % EXE)
    ok = True
    ok &= run_case("正常环境", {})
    ok &= run_case("TEMP 指向不存在目录",
                   {"TEMP": r"C:\__no_such_dir__\tmp", "TMP": r"C:\__no_such_dir__\tmp"})
    ok &= run_case("TEMP 为空", {"TEMP": "", "TMP": ""})

    leftover = [n for n in os.listdir(EXE.parent) if n.startswith("_MEI")]
    print("\n退出后残留解压目录: %s" % (leftover or "无"))
    print("结论: %s" % ("全部通过，不依赖临时目录" if ok else "存在失败项"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
