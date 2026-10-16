#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""试用节点拉取与验证入口"""
import base64, sys, urllib.parse
from refresh_nodes import fetch_details, resolve_entrance, full_link_ok

def main():
    details = fetch_details()
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
        print("[FAIL] 无存活试用节点", file=sys.stderr)
        sys.exit(1)
    txt = "\n".join(out) + "\n"
    with open("refresh_nodes_uris.txt", "w", encoding="utf-8") as f:
        f.write(txt)
    print(f"共 {len(out)} 条已写入 refresh_nodes_uris.txt")

if __name__ == "__main__":
    main()
