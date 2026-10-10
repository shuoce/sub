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
# 白名单过滤（本机网络代理级实测存活）
# =========================

alive_file = os.path.join(share_dir, "alive.txt")


def _strip_tag_suffix(name: str) -> str:
    return name[:-2] if name.endswith("丨峰") else name


def _node_key(line: str):
    """归一化键 (host, port, 名称)：忽略 uuid 等会轮换的字段"""
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
    """只保留 share/alive.txt 白名单内（本机网络实测可用）的节点
    返回 None 表示白名单不可用，退回 TCP 测活"""
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

def gen_sub(api_alive_nodes: list