#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
节点全流程脚本（GitHub Actions 优化版）

1. API拉取节点
2. 白名单过滤（share/alive.txt，本机网络实测可用才保留；白名单不可用时退回 TCP 测活）
3. 名称自动追加"丨峰"后缀
4. 合并 fixed.txt（固定节点跳过测活，强制保留）
5. 生成 nodes_new.txt 与 Base64 订阅 sub.txt
6. 生成 clash.yaml（包含节点重名自动编号）
7. 同步文件到 share/ 目录

凭证从 GitHub Secrets 读取：
  - SUB_TOKEN
  - SUB_AUTHTOKEN
"""

import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import shutil
import socket
import urllib.parse
import urllib.request
import yaml

# =========================
# API 配置（凭证来自 GitHub Secrets）
# =========================

API = os.environ.get("SUB_API_URL", "http://8.210.52.158:8020/app/subscribe")
TOKEN = os.environ["SUB_TOKEN"]
AUTHTOKEN = os.environ["SUB_AUTHTOKEN"]

# =========================
# 测活配置（GitHub Actions 适用）
# =========================

# GitHub 服务器网络好，3.0s 足以判断 TCP 是否响应
TCP_TIMEOUT = 3.0    # 单节点超时时间（秒）
MAX_WORKERS = 30     # 并发线程数

# =========================
# GitHub 固定节点
# =========================

FIXED_URL = "https://raw.githubusercontent.com/shuoce/sub/main/share/fixed.txt"

# =========================
# 输出文件路径
# =========================

nodes_file = "nodes.txt"
nodes_new_file = "nodes_new.txt"
sub_file = "sub.txt"
clash_file = "clash.yaml"

share_dir = "share"
share_sub_file = os.path.join(share_dir, "a.txt")
share_clash_file = os.path.join(share_dir, "clash.yaml")


# =========================
# 辅助函数：安全 Base64 解码
# =========================

def safe_b64decode(s: str) -> str:
    """自动补全 padding 并兼容 URL safe base64"""
    s = s.strip().replace("-", "+").replace("_", "/")
    s += "=" * (-len(s) % 4)
    return base64.b64decode(s).decode("utf-8", errors="ignore")


# =========================
# 1. API 拉取节点
# =========================

def fetch_nodes():
    req = urllib.request.Request(API)
    req.add_header("token", TOKEN)
    req.add_header("authtoken", AUTHTOKEN)
    req.add_header("User-Agent", "okhttp/4.9.0")

    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode())

    if data.get("code") != 1:
        raise RuntimeError(
            f"API返回异常: {data.get('code')} {data.get('message')}"
        )

    nodes = []
    for grp in data.get("data") or []:
        # 跳过免费节点分组（status==1 或组名含"免费"）
        if grp.get("status") == 1 or "免费" in (grp.get("name") or ""):
            continue
        for n in grp.get("node") or []:
            n = n.strip()
            if n:
                nodes.append(n)

    # 保持顺序去重
    return list(dict.fromkeys(nodes))


# =========================
# 白名单过滤（本机网络实测存活）
# =========================

alive_file = os.path.join(share_dir, "alive.txt")


def _strip_tag_suffix(name: str) -> str:
    return name[:-2] if name.endswith("丨峰") else name


def _node_key(line: str):
    """归一化键 (host, port, 名称)：忽略会轮换的 uuid 等字段"""
    line = line.strip()
    try:
        if line.startswith("vmess://"):
            obj = json.loads(safe_b64decode(line[8:]))
            return (obj.get("add"), int(obj.get("port")), _strip_tag_suffix(obj.get("ps", "")))
        u = urllib.parse.urlparse(line)
        if u.hostname and u.port:
            tag = urllib.parse.unquote(u.fragment) if u.fragment else ""
            return (u.hostname, int(u.port), _strip_tag_suffix(tag))
    except Exception:
        return None
    return None


def filter_alive_whitelist(nodes: list):
    """仅保留 share/alive.txt 白名单内节点；返回 None 表示白名单不可用，退回 TCP 测活"""
    if not os.path.exists(alive_file):
        print("[白名单] share/alive.txt 不存在，退回 TCP 测活")
        return None
    keys = set()
    with open(alive_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                k = _node_key(line)
                if k:
                    keys.add(k)
    if not keys:
        print("[白名单] 白名单为空，退回 TCP 测活")
        return None
    kept = [n for n in nodes if _node_key(n) in keys]
    if not kept:
        print("[警告] 白名单匹配为 0（可能已过期），退回 TCP 测活")
        return None
    print(f"[白名单] 本机实测可用：保留 {len(kept)} / {len(nodes)}")
    return kept


# =========================
# 2. TCP 测活与超时剔除
# =========================

def extract_host_port(line: str):
    """解析节点的目标主机与端口"""
    line = line.strip()
    try:
        if line.startswith("vmess://"):
            data = line[8:]
            obj = json.loads(safe_b64decode(data))
            return obj.get("add"), int(obj.get("port"))

        if line.startswith(("vless://", "trojan://", "ss://")):
            u = urllib.parse.urlparse(line)
            if u.hostname and u.port:
                return u.hostname, int(u.port)
    except Exception:
        pass
    return None, None


def check_node_alive(line: str, timeout: float = TCP_TIMEOUT) -> bool:
    """对单节点进行 TCP 握手检测"""
    host, port = extract_host_port(line)
    if not host or not port:
        # 解析不出 host/port 时默认保留，防止误杀特殊格式节点
        return True

    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def filter_alive_nodes(nodes: list) -> list:
    """并发检测并剔除超时节点（带 Actions 熔断保护）"""
    if not nodes:
        return []

    print(f"[测活] 开始探测 {len(nodes)} 个 API 节点 (并发: {MAX_WORKERS}, 超时: {TCP_TIMEOUT}s)...")
    alive_nodes = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {executor.submit(check_node_alive, node): node for node in nodes}
        for future in as_completed(future_map):
            node = future_map[future]
            try:
                if future.result():
                    alive_nodes.append(node)
            except Exception:
                pass

    # 熔断安全机制：
    # 如果检测出来存活节点为 0（大概率是 GitHub Actions 容器的网络策略或 IP 被封锁）
    # 此时不剔除任何节点，全量保留，避免推送一个空配置
    if len(alive_nodes) == 0 and len(nodes) > 0:
        print("[警告] 存活节点检测为 0，触发熔断保护：跳过剔除，保留所有原始节点！")
        return nodes

    print(f"[测活] 完成：可用 {len(alive_nodes)} / {len(nodes)}，已剔除 {len(nodes) - len(alive_nodes)} 个超时节点")
    return alive_nodes


# =========================
# 3. 节点重命名处理
# =========================

def process_vmess(line: str) -> str:
    try:
        raw_b64 = line[8:]
        obj = json.loads(safe_b64decode(raw_b64))

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


# =========================
# 4. 生成 nodes_new.txt / sub.txt
# =========================

def gen_sub(api_alive_nodes: list) -> int:
    # 1. API 存活节点加后缀
    result = [process_line(n) for n in api_alive_nodes if n.strip()]

    # 2. 合并固定节点（fixed.txt 跳过测活，无论是否超时均强制保留）
    fixed_count = 0
    try:
        req = urllib.request.Request(FIXED_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            lines = r.read().decode("utf-8").splitlines()
            for line in lines:
                line = line.strip()
                if line and not line.startswith("#"):
                    result.append(process_line(line))
                    fixed_count += 1
        print(f"[固定节点] 成功读取并合并 fixed.txt: {fixed_count} 个")
    except Exception as e:
        print(f"[警告] 读取 fixed.txt 失败: {e}")

    final_text = "\n".join(result)

    # 写入 nodes_new.txt
    with open(nodes_new_file, "w", encoding="utf-8") as f:
        f.write(final_text + "\n")

    # 写入 Base64 sub.txt
    encoded = base64.b64encode(final_text.encode("utf-8")).decode("utf-8")
    with open(sub_file, "w", encoding="utf-8") as f:
        f.write(encoded)

    return len(result)


# =========================
# 5. Clash 配置解析转换
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
            proxy["grpc-opts"] = {
                "grpc-service-name": get_param(p, "serviceName", "")
            }

        return proxy
    except Exception as e:
        return None


def decode_vmess(line):
    try:
        data = line.replace("vmess://", "")
        obj = json.loads(safe_b64decode(data))

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

        if obj.get("tls") == "tls":
            proxy["tls"] = True

        if obj.get("net") == "ws":
            proxy["network"] = "ws"
            proxy["ws-opts"] = {
                "path": obj.get("path", "/"),
                "headers": {"Host": get_param({"host": [obj.get("host", obj["add"])]}, "host")},
            }

        return proxy
    except Exception as e:
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
    except Exception as e:
        return None


def gen_clash():
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

            if pr:
                proxies.append(pr)

    # 节点防重名处理（Clash 规定 name 必须唯一，否则客户端报错）
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
            {
                "name": "自动选择",
                "type": "url-test",
                "url": "https://www.gstatic.com/generate_204",
                "interval": 300,
                "proxies": list(default_proxy),
            },
            {
                "name": "手动选择",
                "type": "select",
                "proxies": ["自动选择"] + list(default_proxy),
            },
        ],
        "rules": [
            "MATCH,自动选择"
        ],
    }

    with open(clash_file, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, sort_keys=False)

    return len(proxies)


# =========================
# 6. 同步与主程序入口
# =========================

def sync_share():
    os.makedirs(share_dir, exist_ok=True)
    shutil.copyfile(sub_file, share_sub_file)
    shutil.copyfile(clash_file, share_clash_file)
    print(f"已同步: {sub_file} → {share_sub_file}")
    print(f"已同步: {clash_file} → {share_clash_file}")


if __name__ == "__main__":
    # 1. API 拉取
    nodes = fetch_nodes()
    print(f"API 获取原始节点: {len(nodes)} 个")

    # 2. 保存原始拉取记录
    with open(nodes_file, "w", encoding="utf-8") as f:
        f.write("\n".join(nodes) + "\n")

    # 3. 优先白名单过滤（本机网络实测存活），白名单不可用时退回 TCP 测活
    alive_nodes = filter_alive_whitelist(nodes)
    if alive_nodes is None:
        alive_nodes = filter_alive_nodes(nodes)

    # 4. 生成 sub 文本（在此处合并 fixed.txt，固定节点免检直通）
    total = gen_sub(alive_nodes)

    # 5. 生成 Clash 配置
    n_clash = gen_clash()

    # 6. 同步到 share 目录
    sync_share()

    print("========================================")
    print(f"执行完毕！最终有效节点总计（含固定节点）: {total}")
    print(f"Clash 代理列表数: {n_clash}")
