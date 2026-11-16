/* EmptyApp —— 一个只负责"打开、常驻、关掉"的空白窗口程序。
 *
 * 纯 Win32 API，无第三方依赖。不联网、不读写文件、不创建子进程。
 * 编译产物约 74 KB，双击即用，不需要任何运行时（无 .NET、无 Python）。
 *
 * 构建（Windows 原生，或在 Linux / macOS 上交叉编译出 exe）：
 *   zig cc -target x86_64-windows-gnu -O2 -DUNICODE -D_UNICODE \
 *          -Wl,--subsystem,windows -s -o dist/EmptyApp.exe app.c -luser32 -lgdi32
 *
 * 三个必须注意的点：
 *   1. 必须加 -DUNICODE，否则 IDC_ARROW 会展开为 ANSI 版，LoadCursorW 类型不匹配直接编译报错。
 *   2. 必须用 -Wl,--subsystem,windows 指定 GUI 子系统；zig cc 的 -mwindows 参数无效
 *      （只报警告、不生效，产出的仍是 console 版，双击会带一个黑框）。
 *   3. 本文件为 UTF-8 编码（含中文界面文案），请勿用 GBK 另存。
 *
 * 许可证：MIT
 */

#include <windows.h>

static int g_seconds = 0;
static HFONT g_font = NULL;

static LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp)
{
    switch (msg) {
    case WM_CREATE:
        SetTimer(hwnd, 1, 1000, NULL);
        return 0;

    case WM_TIMER:
        if (wp == 1) {
            g_seconds++;
            InvalidateRect(hwnd, NULL, FALSE);
        }
        return 0;

    case WM_ERASEBKGND:
        return 1;  /* 背景在 WM_PAINT 里自己画，避免闪烁 */

    case WM_PAINT: {
        PAINTSTRUCT ps;
        HDC hdc = BeginPaint(hwnd, &ps);
        RECT rc;
        GetClientRect(hwnd, &rc);

        HBRUSH bg = CreateSolidBrush(RGB(255, 255, 255));
        FillRect(hdc, &rc, bg);
        DeleteObject(bg);

        SetBkMode(hdc, TRANSPARENT);
        SetTextColor(hdc, RGB(64, 64, 64));
        HFONT old = (HFONT)SelectObject(hdc, g_font);

        wchar_t elapsed[32];
        wsprintfW(elapsed, L"%d:%02d:%02d",
                  g_seconds / 3600, (g_seconds % 3600) / 60, g_seconds % 60);

        wchar_t text[512];
        lstrcpyW(text, L"程序已启动，正在运行\n\n已运行 ");
        lstrcatW(text, elapsed);
        lstrcatW(text, L"\n\n本程序不执行任何任务，仅保持常驻\n"
                        L"点击右上角 X 关闭窗口即可退出");

        RECT calc = { 0, 0, rc.right, 0 };
        DrawTextW(hdc, text, -1, &calc, DT_CENTER | DT_WORDBREAK | DT_CALCRECT);
        int top = (rc.bottom - calc.bottom) / 2;
        if (top < 0) top = 0;
        RECT box = { 0, top, rc.right, top + calc.bottom };
        DrawTextW(hdc, text, -1, &box, DT_CENTER | DT_WORDBREAK);

        SelectObject(hdc, old);
        EndPaint(hwnd, &ps);
        return 0;
    }

    case WM_DESTROY:
        KillTimer(hwnd, 1);
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(hwnd, msg, wp, lp);
}

int WINAPI WinMain(HINSTANCE hInst, HINSTANCE hPrev, LPSTR cmd, int show)
{
    (void)hPrev; (void)cmd;

    SetProcessDPIAware();

    LOGFONTW lf;
    ZeroMemory(&lf, sizeof(lf));
    lf.lfHeight = -20;
    lf.lfWeight = FW_NORMAL;
    lf.lfCharSet = DEFAULT_CHARSET;
    lstrcpyW(lf.lfFaceName, L"Microsoft YaHei");
    g_font = CreateFontIndirectW(&lf);

    WNDCLASSEXW wc;
    ZeroMemory(&wc, sizeof(wc));
    wc.cbSize = sizeof(wc);
    wc.style = CS_HREDRAW | CS_VREDRAW;
    wc.lpfnWndProc = WndProc;
    wc.hInstance = hInst;
    wc.hCursor = LoadCursorW(NULL, IDC_ARROW);
    wc.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
    wc.lpszClassName = L"EmptyAppWindowClass";
    if (!RegisterClassExW(&wc))
        return 1;

    const int w = 480, h = 300;
    int x = (GetSystemMetrics(SM_CXSCREEN) - w) / 2;
    int y = (GetSystemMetrics(SM_CYSCREEN) - h) / 2;
    if (x < 0) x = 0;
    if (y < 0) y = 0;

    HWND hwnd = CreateWindowExW(0, wc.lpszClassName, L"EmptyApp - 运行中",
                                WS_OVERLAPPEDWINDOW | WS_VISIBLE,
                                x, y, w, h, NULL, NULL, hInst, NULL);
    if (!hwnd)
        return 1;

    ShowWindow(hwnd, show);
    UpdateWindow(hwnd);

    MSG msg;
    while (GetMessageW(&msg, NULL, 0, 0) > 0) {
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }

    if (g_font) DeleteObject(g_font);
    return 0;
}
