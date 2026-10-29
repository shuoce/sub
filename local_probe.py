#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【仅本机运行 · 勿提交到 GitHub Actions】
share/alive.txt 白名单刷新脚本：从你当前网络做 TCP 级实测，写入本机实测存活节点。

设计说明（诚实版）：
- 只做 TCP 握手（1.5s 超时 × 2 次重试），不声称 HTTP 204：
  纯 Python 无法对 vless-reality / ss+plugin 做真实代理级 HTTP 204 探测，
  任何"204 探活"声明都不成立。真正协议级验证 = 在客户端里跑测速。
- 本脚本的价值：让白名单反映**你的网络视角**，纠正 GitHub Runner 视角的误判
  （Runner 测不通但你这通的节点，被白名单保底保留）。
- 安全：输出文件只含节点链接（仓库里本来就有），绝不写入本机 IP/设备名/内网信息。
"""
import os
import socket
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

SOURCE = "nodes.txt"          # 以 API 原始快照为探测源
TARGET = "share/alive.txt"    # 写回白名单
TIMEOUT = 2.5
RETRIES = 3
WORKERS = 15


def extract_host_port(line: str):
    """与 fetch_nodes.py 保持一致的 host:port 提取"""
    line = line.strip()
    try:
        if line.startswith("vmess://"):
            import base64, json
            s = line[8:].replace("-", "+").replace("_", "/")
            s += "=" * (-len(s) % 4)
            obj = json.loads(base64.b64decode(s).decode("utf-8", errors="ignore"))
            return obj.get("add"), int(obj.get("port"))
        if line.startswith(("vless://", "trojan://", "ss://")):
            u = urllib.parse.urlparse(line)
            return u.hostname, u.port
    except Exception:
        pass
    return None, None


def probe(line: str) -> bool:
    host, port = extract_host_port(line)
    if not host or not port:
        return False
    for _ in range(RETRIES):
        try:
            with socket.create_connection((host, int(port)), timeout=TIMEOUT):
                return True
        except Exception:
            continue
    return False


def main():
    if not os.path.exists(SOURCE):
        print(f"[错误] 未找到 {SOURCE}，请先拉取仓库或运行 fetch_nodes.py")
        raise SystemExit(1)

    with open(SOURCE, encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]

    print(f"[探测] 从本机网络实测 {len(lines)} 个节点 (TCP {TIMEOUT}s x {RETRIES}) ...")
    ok = set()
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(probe, l): l for l in lines}
        for fut in as_completed(futs):
            try:
                if fut.result():
                    ok.add(futs[fut])
            except Exception:
                pass

    kept = [l for l in lines if l in ok]   # 按原顺序输出，便于 diff 审阅
    os.makedirs(os.path.dirname(TARGET), exist_ok=True)
    with open(TARGET, "w", encoding="utf-8") as f:
        f.write("\n".join(kept) + "\n")

    print(f"[完成] 本机实测存活 {len(kept)} / {len(lines)}，已写入 {TARGET}")
    print("[提示] 确认无误后手动提交：git add share/alive.txt && git commit")


if __name__ == "__main__":
    main()
