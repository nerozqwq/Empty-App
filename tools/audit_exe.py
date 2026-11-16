"""静态审计：解析 PE 导入表、检查联网/文件/进程能力、扫描密钥特征。

用法：
    python tools/audit_exe.py                # 审计 dist/EmptyApp.exe
    python tools/audit_exe.py path/to.exe    # 审计指定文件

这个脚本不运行程序，只读文件字节，可用于审查任意 PE 文件的依赖与敏感字符串。
"""

import os
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "dist" / "EmptyApp.exe"

NET_DLLS = {"ws2_32", "wsock32", "wininet", "winhttp", "urlmon", "dnsapi",
            "mswsock", "iphlpapi", "secur32", "crypt32", "ncrypt"}
RISKY_APIS = {
    "网络": ["socket", "connect", "send", "recv", "WSAStartup", "getaddrinfo",
             "gethostbyname", "InternetOpenW", "InternetOpenUrlW", "HttpOpenRequestW",
             "HttpSendRequestW", "WinHttpOpen", "WinHttpConnect", "URLDownloadToFileW",
             "DnsQuery_W"],
    "动态加载": ["LoadLibraryW", "LoadLibraryA", "LoadLibraryExW", "GetProcAddress"],
    "文件读写": ["CreateFileW", "WriteFile", "ReadFile", "fopen", "_wfopen", "DeleteFileW"],
    "注册表": ["RegOpenKeyW", "RegCreateKeyW", "RegSetValueW", "RegSetValueExW"],
    "进程/Shell": ["CreateProcessW", "ShellExecuteW", "WinExec", "CreateThread"],
}
KEY_MARKS = ["sk-", "sk_", "api_key", "apikey", "api-key", "API_KEY", "APIKEY",
             "access_token", "auth_token", "client_secret", "secret_key",
             "password", "passwd", "Bearer", "Authorization",
             "AKIA", "ghp_", "AIza", "xoxb-", "-----BEGIN",
             "http://", "https://", "www."]


def parse_pe(data):
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if data[e_lfanew:e_lfanew + 4] != b"PE\0\0":
        raise ValueError("不是有效的 PE 文件")
    coff = e_lfanew + 4
    nsec = struct.unpack_from("<H", data, coff + 2)[0]
    opt_size = struct.unpack_from("<H", data, coff + 16)[0]
    opt = coff + 20
    pe32p = struct.unpack_from("<H", data, opt)[0] == 0x20B
    subsystem = struct.unpack_from("<H", data, opt + 68)[0]
    dd = opt + (112 if pe32p else 96)
    imp_rva = struct.unpack_from("<I", data, dd + 8)[0]

    secs = []
    sec_off = opt + opt_size
    for i in range(nsec):
        s = sec_off + i * 40
        name = data[s:s + 8].rstrip(b"\0").decode("ascii", "replace")
        vsize, vaddr, rawsize, rawptr = struct.unpack_from("<IIII", data, s + 8)
        secs.append((name, vaddr, vsize, rawptr, rawsize))
    return pe32p, subsystem, imp_rva, secs


def imports(data, pe32p, imp_rva, secs):
    def off(rva):
        for _n, vaddr, vsize, rawptr, rawsize in secs:
            if vaddr <= rva < vaddr + max(vsize, rawsize):
                return rawptr + (rva - vaddr)
        return None

    def cstr(o):
        return data[o:data.index(b"\0", o)].decode("ascii", "replace")

    result = {}
    base = off(imp_rva)
    if base is None:
        return result
    step = 8 if pe32p else 4
    idx = 0
    while True:
        oft, _ts, _fc, name_rva, ft = struct.unpack_from("<IIIII", data, base + idx * 20)
        if name_rva == 0:
            break
        dll = cstr(off(name_rva))
        thunk = off(oft or ft)
        funcs, j = [], 0
        while True:
            val = struct.unpack_from("<Q" if pe32p else "<I", data, thunk + j * step)[0]
            if val == 0:
                break
            if not (val >> (63 if pe32p else 31)):
                funcs.append(cstr(off((val & 0x7FFFFFFF) + 2)))
            else:
                funcs.append("Ordinal#%d" % (val & 0xFFFF))
            j += 1
        result[dll] = funcs
        idx += 1
    return result


def main():
    if not PATH.exists():
        print("找不到文件：%s" % PATH)
        return 1
    data = PATH.read_bytes()
    pe32p, subsystem, imp_rva, secs = parse_pe(data)
    deps = imports(data, pe32p, imp_rva, secs)

    print("=" * 66)
    print("文件: %s" % PATH)
    print("大小: %d 字节 (%.1f KB)   架构: %s   子系统: %s"
          % (len(data), len(data) / 1024,
             "x86-64" if pe32p else "x86",
             {2: "GUI（无控制台）", 3: "CONSOLE（带黑框）"}.get(subsystem, subsystem)))
    print("=" * 66)

    print("\n[1] 导入的 DLL（运行时依赖）")
    for dll, funcs in sorted(deps.items()):
        print("  %-36s %2d 个: %s" % (dll, len(funcs), ", ".join(funcs)))

    print("\n[2] 能力审查")
    all_funcs = {f for fs in deps.values() for f in fs}
    net_dll = [d for d in deps if d.lower().replace(".dll", "") in NET_DLLS]
    for label, names in RISKY_APIS.items():
        hit = [n for n in names if n in all_funcs]
        print("  %-10s %s" % (label, ("存在 -> " + ", ".join(hit)) if hit else "无"))
    if net_dll:
        print("  %-10s 存在 -> %s" % ("网络 DLL", ", ".join(net_dll)))
    else:
        print("  %-10s 无" % "网络 DLL")

    print("\n[3] 密钥 / 凭据 / 网址特征（ASCII + UTF-16 双通道）")
    hits = 0
    for mark in KEY_MARKS:
        n = (len(re.findall(re.escape(mark.encode()), data)) +
             len(re.findall(re.escape(mark.encode("utf-16-le")), data)))
        if n:
            hits += n
            print("  [!] %-16s %d 处" % (mark, n))
    if not hits:
        print("  0 处命中 —— 不含 API Key、令牌、密码或网址")

    print("\n[4] 是否夹带其他可执行体")
    inner = [m.start() for m in re.finditer(b"MZ", data) if m.start() != 0]
    zips = [m.start() for m in re.finditer(b"PK\x03\x04", data)]
    print("  内嵌 MZ 头: %d 处   内嵌 ZIP: %d 处" % (len(inner), len(zips)))
    if inner:
        print("  提示: MZ 多出现在 mingw 启动代码的 PE 头校验指令中（cmp ax,5A4Dh），"
              "需结合上下文判断")

    print("\n[5] 系统依赖是否本机自带")
    sysdir = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    missing = [d for d in deps if not (sysdir / d).exists()]
    print("  缺失: %s" % (", ".join(missing) if missing else "无（全部为系统自带）"))
    print("=" * 66)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
