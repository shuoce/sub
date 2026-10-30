#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
shuoce/sub 核心订阅流水线（修订版）

相对旧版的修复：
1. fetch_api_nodes 按真实 API 返回解析：code==1 严格校验、data[i].node 字符串数组、
   跳过 status==1 / 组名含"免费"；拉取失败直接报错退出（绝不静默发布空/旧内容）
2. 白名单 share/alive.txt 解耦为 (host,port) 键，不再绑定节点名称；
   白名单不再是排他准入 —— 全部 API 节点都参与测活，白名单节点测活失败时
   按"高信任降级"处理（见 main 中注释），需定期用 local_probe.py 刷新白名单
3. 测活：1.5s × 2 次重试，消除瞬时抖动误杀
4. 熔断：0 存活时回退上一版 nodes_new.txt 快照（而非全量发布未测活节点）
5. (type,host,port) 全局去重；公告节点最多保留 1 条；修正 fixed.txt 第 3 条
   pbk 疑似 typo（42 字符，比正确值少 1 位）
6. gen_clash 补齐 ss:// 解析；保留原 mixed-port 键与 https 探测地址

凭证：GitHub Secrets → SUB_TOKEN / SUB_AUTHTOKEN
"""

import base64
import json
import os
import re
import shutil
import socket
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

import yaml

# =========================
# 配置（凭证来自 GitHub Secrets）
# =========================
API = os.environ.get("SUB_API_URL", "http://8.210.52.158:8020/app/subscribe")
TOKEN = os.environ["SUB_TOKEN"]
AUTHTOKEN = os.environ["SUB_AUTHTOKEN"]

TCP_TIMEOUT = 1.5     # 单次 TCP 握手超时（秒）
TCP_RETRIES = 2        # 每节点探测次数（≥1 次成功即存活）
MAX_WORKERS = 30

FIXED_FILE = os.path.join("share", "fixed.txt")   # 改为本地读取（CI 已 checkout）
alive_file = os.path.join("share", "alive.txt")

nodes_file = "nodes.txt"
nodes_new_file = "nodes_new.txt"
sub_file = "sub.txt"
clash_file = "clash.yaml"
share_dir = "share"
share_sub_file = os.path.join(share_dir, "a.txt")
share_clash_file = os.path.join(share_dir, "clash.yaml")


ANNOUNCE_KEYWORDS = ("请在各代理", "谢谢大家", "tg：", "tg留言", "公告", "通知")

# fixed.txt 中 pbk 为 42 字符的疑似 typo（正确 43 字符），按同文件其他行的值修正
PBK_TYPO_42 = "1jkizvy42aHc-um3C7LgmBYRn6HFJomyk0F2T_iPwA"
PBK_CANON = "1jkizvy42aHc-um3C7LgmBYRn6HFJomyk0F2T_i2PwA"


# =========================
# 辅助
# =========================

def safe_b64decode(s: str) -> str:
    s = s.strip().replace("-", "+").replace("_", "/")
    s += "=" * (-len(s) % 4)
    return base64.b64decode(s).decode("utf-8", errors="ignore")


def _strip_tag_suffix(name: str) -> str:
    return name[:-2] if name.endswith("丨峰") else name


def is_announcement(name: str) -> bool:
    n = name or ""
    return any(k in n for k in ANNOUNCE_KEYWORDS)


# =========================
# 1. API 拉取（按真实返回结构）
# =========================

def fetch_nodes() -> list:
    """真实结构：{"code":1,"data":[{"id","status","name","node":[str,...],"type"}]}
    code!=1 或结构异常 → 直接抛错，让 Actions 失败（禁止静默发布旧内容）"""
    req = urllib.request.Request(API)
    req.add_header("token", TOKEN)
    req.add_header("authtoken", AUTHTOKEN)
    req.add_header("User-Agent", "okhttp/4.9.0")

    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode())

    if data.get("code") != 1:
        raise RuntimeError(f"API返回异常: {data.get('code')} {data.get('message')}")

    raw = data.get("data")
    if not isinstance(raw, list):
        raise RuntimeError(f"API data 结构异常: 期望 list，实际 {type(raw).__name__}")

    nodes = []
    for grp in raw:
        if not isinstance(grp, dict):
            continue
        if grp.get("status") == 1 or "免费" in (grp.get("name") or ""):
            continue
        for n in grp.get("node") or []:       # ← 真实字段名是 node，元素为字符串
            if isinstance(n, str) and n.strip():
                nodes.append(n.strip())
            elif isinstance(n, dict):
                link = n.get("link") or n.get("url")
                if link:
                    nodes.append(link.strip())

    return list(dict.fromkeys(nodes))         # 保序去重


# =========================
# 2. 白名单（参考池，非排他准入）
# =========================

def _node_key(line: str):
    """(host, port) 键；名称不参与匹配（防机场改名失配）"""
    line = line.strip()
    try:
        if line.startswith("vmess://"):
            obj = json.loads(safe_b64decode(line[8:]))
            return (str(obj.get("add")).lower(), int(obj.get("port")))
        u = urllib.parse.urlparse(line)
        if u.hostname and u.port:
            return (u.hostname.lower(), int(u.port))
    except Exception:
        return None
    return None


def load_whitelist() -> set:
    if not os.path.exists(alive_file):
        print("[白名单] share/alive.txt 不存在，全部节点按测活结果处理")
        return set()
    keys = set()
    with open(alive_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                k = _node_key(line)
                if k:
                    keys.add(k)
    print(f"[白名单] 参考键 {len(keys)} 个（需定期 local_probe.py 刷新，否则死节点会被保留）")
    return keys


# =========================
# 3. TCP 测活（重试抗抖动）
# =========================

def extract_host_port(line: str):
    line = line.strip()
    try:
        if line.startswith("vmess://"):
            obj = json.loads(safe_b64decode(line[8:]))
            return obj.get("add"), int(obj.get("port"))
        if line.startswith(("vless://", "trojan://", "ss://")):
            u = urllib.parse.urlparse(line)
            if u.hostname and u.port:
                return u.hostname, u.port
    except Exception:
        pass
    return None, None


def check_node_alive(line: str) -> bool:
    """TCP 握手 × TCP_RETRIES 次，任一次成功即存活"""
    host, port = extract_host_port(line)
    if not host or not port:
        # 解析不出 host/port：按公告/特殊节点处理，保留（去重阶段另行归类）
        return True
    for _ in range(max(1, TCP_RETRIES)):
        try:
            with socket.create_connection((host, int(port)), timeout=TCP_TIMEOUT):
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            continue
    return False


def filter_alive_nodes(nodes: list, whitelist: set) -> list:
    """全量候选并发测活；白名单节点测活失败时降级保留（高信任池）。
    注意：白名单必须定期刷新，否则已死白名单节点会一直被保留。"""
    if not nodes:
        return []
    print(f"[测活] 探测 {len(nodes)} 个节点 (并发 {MAX_WORKERS}, {TCP_TIMEOUT}s × {TCP_RETRIES}) ...")

    tested = {}   # line -> bool
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        fmap = {ex.submit(check_node_alive, n): n for n in nodes}
        for fut in as_completed(fmap):
            try:
                tested[fmap[fut]] = fut.result()
            except Exception:
                tested[fmap[fut]] = False

    alive = [n for n in nodes if tested.get(n)]
    white_kept = [n for n in nodes if not tested.get(n) and _node_key(n) in whitelist]
    if white_kept:
        print(f"[白名单保底] {len(white_kept)} 个白名单节点本次测活未通过，按高信任保留")
    result = alive + white_kept

    # 熔断：0 存活 → 回退上一版快照（禁止把未测活的全量原样发布）
    if not result and nodes:
        print("[警告] 本轮 0 存活，回退上一版 nodes_new.txt 快照（Runner 网络可能异常）")
        try:
            with open(nodes_new_file, encoding="utf-8") as f:
                prev = [l.strip() for l in f if l.strip() and not l.startswith("#")]
            if prev:
                return prev
        except FileNotFoundError:
            pass
        print("[警告] 无历史快照，本轮输出仅保留 fixed.txt 公告/固定节点")
        return []

    print(f"[测活] 完成：{len(alive)}/{len(nodes)} 通过，白名单保底 {len(white_kept)}，最终 {len(result)}")
    return result


# =========================
# 4. 改名与去重
# =========================

def process_vmess(line: str) -> str:
    try:
        obj = json.loads(safe_b64decode(line[8:]))
        name = obj.get("ps", "")
        if not name.endswith("丨峰"):
            obj["ps"] = f"{name}丨峰"
        new_b64 = base64.b64encode(
            json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).decode("utf-8")
        return f"vmess://{new_b64}"
    except Exception:
        return line


def process_line(line: str) -> str:
    line = line.strip()
    if not line:
        return ""
    if line.startswith("vmess://"):
        return process_vmess(line)
    if "#" in line:
        url, name = line.rsplit("#", 1)
        name = urllib.parse.unquote(name)
        if not name.endswith("丨峰"):
            name += "丨峰"
        return f"{url}#{urllib.parse.quote(name)}"
    return line


def fix_pbk_typo(line: str) -> str:
    if PBK_TYPO_42 in line and PBK_CANON not in line:
        print("[修正] fixed.txt 公告节点 pbk typo (42→43 字符)")
        return line.replace(PBK_TYPO_42, PBK_CANON)
    return line


def _announce_name(line: str) -> str:
    u = urllib.parse.urlparse(line)
    return urllib.parse.unquote(u.fragment) if u.fragment else ""


# =========================
# 5. 生成 nodes_new.txt / sub.txt
# =========================

def _load_fixed() -> list:
    """读本地 share/fixed.txt（不再走 raw.githubusercontent，少一个故障点）"""
    if not os.path.exists(FIXED_FILE):
        print(f"[警告] {FIXED_FILE} 不存在，跳过固定节点合并")
        return []
    out = []
    with open(FIXED_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                out.append(fix_pbk_typo(line))
    return out


def gen_sub(api_alive_nodes: list) -> int:
    # 候选顺序：API 存活在前，fixed 追加（公告 + 固定代理）
    candidates = [process_line(n) for n in api_alive_nodes if n.strip()]
    candidates += [process_line(l) for l in _load_fixed()]

    # (type,host,port) 去重；公告节点最多保留 1 条
    result, seen, announce_kept = [], set(), False
    for line in candidates:
        if not line:
            continue
        if is_announcement(_announce_name(line)):
            if announce_kept:
                continue
            announce_kept = True
            result.append(line)
            continue
        scheme = line.split("://", 1)[0].lower()
        hp = extract_host_port(line)
        key = (scheme,) + hp
        if hp[0] is None:
            result.append(line)   # 解析不了的特殊行不去重、不丢弃
            continue
        if key in seen:
            continue
        seen.add(key)
        result.append(line)

    final_text = "\n".join(result)
    with open(nodes_new_file, "w", encoding="utf-8") as f:
        f.write(final_text + "\n")
    encoded = base64.b64encode(final_text.encode("utf-8")).decode("utf-8")
    with open(sub_file, "w", encoding="utf-8") as f:
        f.write(encoded)
    return len(result)


# =========================
# 6. Clash 配置生成（含 ss 补齐）
# =========================

def get_param(params, key, default=None):
    return params.get(key, [default])[0] if key in params else default


def decode_vless(line):
    try:
        u = urllib.parse.urlparse(line)
        p = urllib.parse.parse_qs(u.query)
        proxy = {
            "name": urllib.parse.unquote(u.fragment) if u.fragment else "VLESS节点",
            "type": "vless",
            "server": u.hostname,
            "port": int(u.port),
            "uuid": u.username,
            "udp": True,
        }
        security = get_param(p, "security")
        if security in ("tls", "reality"):
            proxy["tls"] = True
            if security == "reality":
                proxy["reality-opts"] = {
                    "public-key": get_param(p, "pbk", ""),
                    "short-id": get_param(p, "sid", ""),
                }
        sni = get_param(p, "sni")
        if sni:
            proxy["servername"] = sni
        flow = get_param(p, "flow")
        if flow:
            proxy["flow"] = flow
        fp = get_param(p, "fp")
        if fp:
            proxy["client-fingerprint"] = fp
        net = get_param(p, "type") or get_param(p, "net")
        if net == "ws":
            proxy["network"] = "ws"
            proxy["ws-opts"] = {
                "path": get_param(p, "path", "/"),
                "headers": {"Host": get_param(p, "host", u.hostname)},
            }
        elif net == "grpc":
            proxy["network"] = "grpc"
            proxy["grpc-opts"] = {"grpc-service-name": get_param(p, "serviceName", "")}
        return proxy
    except Exception:
        return None


def decode_vmess(line):
    try:
        obj = json.loads(safe_b64decode(line[8:]))
        proxy = {
            "name": obj.get("ps", "VMess节点"),
            "type": "vmess",
            "server": obj["add"],
            "port": int(obj["port"]),
            "uuid": obj["id"],
            "alterId": int(obj.get("aid", 0)),
            "cipher": obj.get("scy", "auto"),
            "udp": True,
        }
        if obj.get("tls") in ("tls", "1"):
            proxy["tls"] = True
        if obj.get("net") == "ws":
            proxy["network"] = "ws"
            proxy["ws-opts"] = {
                "path": obj.get("path", "/"),
                "headers": {"Host": get_param({"host": [obj.get("host", obj["add"])]}, "host")},
            }
        return proxy
    except Exception:
        return None


def decode_trojan(line):
    try:
        u = urllib.parse.urlparse(line)
        p = urllib.parse.parse_qs(u.query)
        proxy = {
            "name": urllib.parse.unquote(u.fragment) if u.fragment else "Trojan节点",
            "type": "trojan",
            "server": u.hostname,
            "port": u.port,
            "password": u.username,
            "udp": True,
            "tls": True,
        }
        sni = get_param(p, "sni")
        if sni:
            proxy["sni"] = sni
        return proxy
    except Exception:
        return None


def decode_ss(line):
    """补齐 ss://：SIP002 (userinfo@host:port) 与旧版整体 base64 两种格式"""
    try:
        u = urllib.parse.urlparse(line)
        p = urllib.parse.parse_qs(u.query)
        name = urllib.parse.unquote(u.fragment) if u.fragment else "SS节点"
        cipher, password, host, port = "", "", None, None

        if "@" in (u.netloc or ""):
            userinfo = u.netloc.split("@", 1)[0]
            try:
                raw = userinfo.replace("-", "+").replace("_", "/")
                raw += "=" * (-len(raw) % 4)
                dec = base64.b64decode(raw).decode("utf-8", errors="ignore")
                cipher, password = dec.split(":", 1)
            except Exception:
                pass
            host, port = u.hostname, int(u.port or 0)
        else:
            # 旧版: ss://base64(method:password@host:port)?plugin=...
            payload = (u.netloc or "").split("/")[0].split("?")[0]
            raw = payload.replace("-", "+").replace("_", "/")
            raw += "=" * (-len(raw) % 4)
            dec = base64.b64decode(raw).decode("utf-8", errors="ignore")
            cred, _, hp = dec.rpartition("@")
            cipher, password = cred.split(":", 1)
            host, _, pstr = hp.partition(":")
            port = int(pstr)

        if not (cipher and password and host and port):
            return None
        proxy = {"name": name, "type": "ss", "server": host, "port": int(port),
                 "cipher": cipher, "password": password, "udp": True}
        plug = get_param(p, "plugin")
        if plug and "v2ray" in plug:
            opts = {}
            for kv in plug.split(";")[1:]:
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    opts[k] = v
            if opts:
                proxy["plugin"] = "v2ray-plugin"
                proxy["plugin-opts"] = opts
        return proxy
    except Exception:
        return None


def gen_clash() -> int:
    proxies = []
    with open(nodes_new_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            pr = None
            if line.startswith("vmess://"):
                pr = decode_vmess(line)
            elif line.startswith("vless://"):
                pr = decode_vless(line)
            elif line.startswith("trojan://"):
                pr = decode_trojan(line)
            elif line.startswith("ss://"):
                pr = decode_ss(line)
            if pr:
                proxies.append(pr)

    used_names = {}
    for p in proxies:
        base_name = p["name"]
        if base_name in used_names:
            used_names[base_name] += 1
            p["name"] = f"{base_name} {used_names[base_name]}"
        else:
            used_names[base_name] = 1

    names = [p["name"] for p in proxies]
    default_proxy = names if names else ["DIRECT"]

    config = {
        "mixed-port": 7890,
        "allow-lan": True,
        "mode": "rule",
        "log-level": "info",
        "proxies": proxies,
        "proxy-groups": [
            {"name": "自动选择", "type": "url-test",
             "url": "https://www.gstatic.com/generate_204", "interval": 300,
             "proxies": list(default_proxy)},
            {"name": "手动选择", "type": "select",
             "proxies": ["自动选择"] + list(default_proxy)},
        ],
        "rules": ["MATCH,自动选择"],
    }
    with open(clash_file, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, sort_keys=False)
    return len(proxies)


# =========================
# 7. 同步与主入口
# =========================

def sync_share():
    os.makedirs(share_dir, exist_ok=True)
    shutil.copyfile(sub_file, share_sub_file)
    shutil.copyfile(clash_file, share_clash_file)
    print(f"已同步: {sub_file} → {share_sub_file}")
    print(f"已同步: {clash_file} → {share_clash_file}")


if __name__ == "__main__":
    # 1. API 拉取（失败即崩溃，禁止静默发布）
    nodes = fetch_nodes()
    print(f"API 获取原始节点: {len(nodes)} 个")

    with open(nodes_file, "w", encoding="utf-8") as f:
        f.write("\n".join(nodes) + "\n")

    # 2. 白名单参考 + 全量测活（非排他）
    whitelist = load_whitelist()
    alive_nodes = filter_alive_nodes(nodes, whitelist)

    # 3. 生成 sub（合并 fixed、改名、去重）
    total = gen_sub(alive_nodes)


    # 4. 生成 Clash（含 ss）
    n_clash = gen_clash()

    # 5. 同步 share/
    sync_share()

    print("========================================")
    print(f"执行完毕！最终节点（含 fixed/公告）: {total}")
    print(f"Clash 代理列表数: {n_clash}")
