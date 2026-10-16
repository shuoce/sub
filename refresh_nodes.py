#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""refresh_nodes.py — 节点拉取与测活"""
import argparse, base64, json, os, shutil, socket, struct, subprocess, sys, time
import urllib.parse, urllib.request

# 配置
EXPORT_DIRS = ["/storage/emulated/0/", os.path.dirname(os.path.abspath(__file__)), "/tmp/"]
EXPORT_FILENAME = "refresh_nodes_uris.txt"
BASE = "https://www.tw-2026.com/"
KEY = b"0123456789abcdef0123456789abcdef"
IV = b"0000000000000000"
ENTRANCE_FALLBACK = "202.189.10.146"
DEFAULT_NODE_IDS = [2, 7, 8, 9]
DNS_SERVERS = ["114.114.114.114", "223.5.5.5", "119.29.29.29"]
PROBE_PORT = 13579

def _find(name):
    here = os.path.dirname(os.path.abspath(__file__))
    for d in (here, "/usr/local/bin", "/usr/bin"):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return shutil.which(name) or name

SSLOCAL = _find("sslocal")
V2RAY_PLUGIN = _find("v2ray-plugin")

def _device_id():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".device_id")
    try:
        v = open(p).read().strip()
        if len(v) >= 8:
            return v
    except Exception:
        pass
    v = os.urandom(8).hex()
    try:
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.write(fd, v.encode())
        os.close(fd)
    except Exception:
        pass
    return v

DEVICE_ID = _device_id()

# 加密 / API
def aes_crypt(data, decrypt):
    mode = "-d" if decrypt else "-e"
    p = subprocess.run(
        ["openssl", "enc", mode, "-aes-256-cbc", "-iv", IV.hex(), "-K", KEY.hex()],
        input=data, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError("openssl: " + p.stderr.decode(errors="replace").strip())
    out = p.stdout
    if decrypt and out:
        pad = out[-1]
        if 1 <= pad <= 16 and out.endswith(bytes([pad]) * pad):
            out = out[:-pad]
    return out

def enc_payload(obj):
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode()
    return base64.b64encode(aes_crypt(raw, False)).decode()

def dec_data(s):
    return json.loads(aes_crypt(base64.b64decode(s), True).decode())

def call(path, payload, token=""):
    body = json.dumps({"data": enc_payload(payload)}).encode()
    req = urllib.request.Request(BASE + path, data=body, method="POST")
    req.add_header("Content-Type", "application/json; charset=UTF-8")
    req.add_header("User-Agent", "okhttp/4.12.0")
    req.add_header("device-id", DEVICE_ID)
    if token:
        req.add_header("token", token)
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read())
    if not data.get("data"):
        raise RuntimeError(path + " 无数据")
    return dec_data(data["data"])

def fetch_details():
    login = call("api/user/device_login", {})
    if isinstance(login.get("data"), dict):
        login = login["data"]
    token = login.get("token", "")
    if not token:
        raise RuntimeError("登录未返回 token")
    ids = []
    try:
        nd = call("api/node/node_data", {}, token)
        stack = [nd]
        while stack:
            x = stack.pop()
            if isinstance(x, dict):
                if isinstance(x.get("id"), int) and ("server" in x or "ip_address" in x or "port" in x):
                    ids.append(x["id"])
                stack.extend(x.values())
            elif isinstance(x, list):
                stack.extend(x)
    except Exception as e:
        print(f"      [warn] node_data: {e}")
    ids = sorted(set(ids)) or list(DEFAULT_NODE_IDS)
    details = []
    for i in ids:
        try:
            details.append(call("api/node/node_req", {"node_id": i}, token))
            time.sleep(0.2)
        except Exception as e:
            print(f"      [warn] node_req id={i}: {e}")
    if not details:
        raise RuntimeError("所有 node_req 都失败")
    return details

# DNS
def is_public(ip):
    parts = [int(p) for p in ip.split(".")]
    if parts[0] == 10: return False
    if parts[0] == 172 and 16 <= parts[1] <= 31: return False
    if parts[0] == 192 and parts[1] == 168: return False
    if parts[0] == 127 or parts[0] == 0: return False
    if parts[0] == 169 and parts[1] == 254: return False
    if parts[0] == 198 and parts[1] in (18, 19): return False
    if parts[0] == 100 and 64 <= parts[1] <= 127: return False
    return True

def dns_a(name, server, timeout=3.0):
    tid = int(time.time() * 1000) & 0xFFFF
    q = struct.pack(">HHHHHH", tid, 0x0100, 1, 0, 0, 0)
    for lab in name.split("."):
        q += bytes([len(lab)]) + lab.encode()
    q += b"\x00" + struct.pack(">HH", 1, 1)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(q, (server, 53))
        data, _ = s.recvfrom(1024)
    finally:
        s.close()
    ips, i = [], 12
    while data[i] != 0:
        i += data[i] + 1
    i += 5
    ancount = struct.unpack(">H", data[6:8])[0]
    for _ in range(ancount):
        if data[i] & 0xC0 == 0xC0:
            i += 2
        else:
            while data[i] != 0:
                i += data[i] + 1
            i += 1
        typ, _cls, _ttl, rdlen = struct.unpack(">HHIH", data[i:i + 10])
        i += 10
        rdata = data[i:i + rdlen]
        i += rdlen
        if typ == 1 and rdlen == 4:
            ips.append(socket.inet_ntoa(rdata))
    return ips

def resolve_entrance(server):
    for dns in DNS_SERVERS:
        try:
            for ip in dns_a(server, dns):
                if is_public(ip):
                    return ip, dns
        except Exception:
            continue
    return ENTRANCE_FALLBACK, "fallback"

# 测活
def full_link_ok(host, port, d, timeout=15):
    if not (os.path.exists(SSLOCAL) and os.path.exists(V2RAY_PLUGIN)):
        return None, None
    cfg = {"server": host, "server_port": int(port), "password": d["password"],
           "method": d["cipher"], "local_address": "127.0.0.1", "local_port": PROBE_PORT,
           "mode": "tcp_and_udp", "plugin": V2RAY_PLUGIN,
           "plugin_opts": d.get("pluginOpts", "mode=websocket;path=/admin;host=microsoft.com;").rstrip(";")}
    cf = "/tmp/refresh_cfg_%s.json" % port
    fd = os.open(cf, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.write(fd, json.dumps(cfg).encode())
    os.close(fd)
    try:
        for _ in range(2):
            p = subprocess.Popen([SSLOCAL, "-c", cf],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                time.sleep(2)
                if p.poll() is not None:
                    return False, None
                r = subprocess.run(
                    ["curl", "-s", "-m", str(timeout), "-x", f"socks5h://127.0.0.1:{PROBE_PORT}",
                     "https://www.gstatic.com/generate_204", "-o", "/dev/null", "-w", "%{http_code}"],
                    capture_output=True, text=True)
                if r.stdout.strip() == "204":
                    r2 = subprocess.run(
                        ["curl", "-s", "-m", "10", "-x", f"socks5h://127.0.0.1:{PROBE_PORT}",
                         "https://api.ipify.org"],
                        capture_output=True, text=True)
                    return True, r2.stdout.strip()
            finally:
                p.terminate()
                try:
                    p.wait(timeout=5)
                except Exception:
                    p.kill()
            time.sleep(0.5)
        return False, None
    finally:
        try:
            os.remove(cf)
        except Exception:
            pass

# 输出
def pick_export_dir():
    for d in EXPORT_DIRS:
        try:
            os.makedirs(d, exist_ok=True)
            probe = os.path.join(d, ".wtest")
            with open(probe, "w") as f:
                f.write("ok")
            os.remove(probe)
            return d
        except Exception:
            continue
    return "/tmp/"

def main():
    ap = argparse.ArgumentParser(description="一键刷新节点")
    ap.add_argument("--no-verify", action="store_true", help="跳过全链路验证")
    ap.add_argument("--include-dead", action="store_true", help="全挂时也覆盖写入")
    args = ap.parse_args()

    print("=== 1/3 拉取节点 ===")
    try:
        details = fetch_details()
    except Exception as e:
        print("  [FAIL] API 拉取失败:", e)
        sys.exit(2)
    for d in details:
        print(f"  {d['name']}: port={d['port']} server={d['server']}")

    print("=== 2/3 解析入口 IP ===")
    entrance, via = resolve_entrance(details[0]["server"])
    print(f"  {details[0]['server']} -> {entrance}  (via {via})")

    if args.no_verify:
        print("=== 3/3 跳过验证 ===")
        live = [(d, entrance, int(d["port"]), "-入口") for d in details]
    else:
        print("=== 3/3 全链路验证 ===")
        live = []
        for d in details:
            res, ip = full_link_ok(entrance, int(d["port"]), d)
            if res is None:
                print(f"  [skip] {d['name']} (缺验证工具)")
                live.append((d, entrance, int(d["port"]), "-入口"))
            elif res:
                print(f"  [ALIVE] {d['name']} 204 exit_ip={ip}")
                live.append((d, entrance, int(d["port"]), "-入口"))
            else:
                print(f"  [DEAD ] {d['name']} 不通")

    if not live and not args.include_dead:
        print("=== 全挂: 不覆盖已有节点文件 ===")
        sys.exit(1)

    export_dir = pick_export_dir()
    nodes_file = os.path.join(export_dir, EXPORT_FILENAME)

    uris = []
    for d, host, port, suffix in live:
        pw = base64.urlsafe_b64encode(
            f"{d['cipher']}:{d['password']}".encode()).decode().rstrip("=")
        plugin = urllib.parse.quote("v2ray-plugin;" + d["pluginOpts"].rstrip(";"), safe="")
        tag = urllib.parse.quote(d["name"] + suffix, safe="")
        uris.append(f"ss://{pw}@{host}:{port}?plugin={plugin}#{tag}")

    txt = "\n".join(uris) + "\n"
    with open(nodes_file, "w", encoding="utf-8") as f:
        f.write(txt)

    print(f"\n✅ 导出完成！\n📁 文件位置: {nodes_file}\n📋 节点数量: {len(uris)} 条\n")
    print("=" * 60)
    print(txt)
    print("=" * 60)

if __name__ == "__main__":
    main()
