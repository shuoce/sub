#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""试用节点拉取与验证入口"""
import base64, os, sys, time, urllib.parse
from refresh_nodes import fetch_details, resolve_entrance, full_link_ok

def main():
    details = None
    for i in range(4):
        try:
            details = fetch_details()
            break
        except Exception as e:
            print(f"[retry {i + 1}/4] {e}", file=sys.stderr)
            time.sleep(3 * (i + 1))
    if details is None:
        # 拉取持续失败：保留上一轮已验证产物，不让流水线停摆
        if os.path.exists("refresh_nodes_uris.txt") and os.path.getsize("refresh_nodes_uris.txt"):
            print("[warn] 拉取失败，沿用上一轮 refresh_nodes_uris.txt")
            return
        print("[FAIL] 拉取失败且无历史产物", file=sys.stderr)
        sys.exit(2)
    entrance, _ = resolve_entrance(details[0]["server"])
    out = []
    for d in details:
        res, ip = full_link_ok(entrance, int(d["port"]), d)
        if res is True:
            print(f"[ALIVE] {d['name']} 204 exit={ip}")
        elif res is None:
            print("[FAIL] 缺 sslocal/v2ray-plugin，无法验证", file=sys.stderr)
            sys.exit(2)
        else:
            print(f"[DEAD ] {d['name']}")
            continue
        pw = base64.urlsafe_b64encode(
            f"{d['cipher']}:{d['password']}".encode()).decode().rstrip("=")
        plugin = urllib.parse.quote("v2ray-plugin;" + d["pluginOpts"].rstrip(";"), safe="")
        tag = urllib.parse.quote(d["name"], safe="")
        out.append(f"ss://{pw}@{entrance}:{d['port']}?plugin={plugin}#{tag}")
    if not out:
        # 0 存活大概率是 Runner 网络抖动：按熔断回退上一轮快照
        if os.path.exists("refresh_nodes_uris.txt") and os.path.getsize("refresh_nodes_uris.txt"):
            print("[warn] 本轮 0 存活，沿用上一轮 refresh_nodes_uris.txt")
            return
        print("[FAIL] 无存活试用节点且无历史产物", file=sys.stderr)
        sys.exit(1)
    txt = "\n".join(out) + "\n"
    with open("refresh_nodes_uris.txt", "w", encoding="utf-8") as f:
        f.write(txt)
    print(f"共 {len(out)} 条已写入 refresh_nodes_uris.txt")

if __name__ == "__main__":
    main()
