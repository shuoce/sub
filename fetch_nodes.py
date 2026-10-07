#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
节点全流程脚本（GitHub Actions 版）

API拉取
→ 名称加"丨峰"后缀
→ 合并 share/fixed.txt
→ nodes_new.txt
→ Base64订阅 sub.txt
→ 同步到 share/a.txt
→ clash.yaml
→ 同步到 share/clash.yaml

凭证从环境变量读取（GitHub Secrets），不硬编码
"""

import base64
import json
import os
import shutil
import urllib.request
import urllib.parse
import yaml


# =========================
# API 配置（凭证来自 GitHub Secrets）
# =========================

API = "http://8.210.52.158:8020/app/subscribe"

TOKEN = os.environ["SUB_TOKEN"]
AUTHTOKEN = os.environ["SUB_AUTHTOKEN"]


# =========================
# GitHub 固定节点
# =========================

FIXED_URL = "https://raw.githubusercontent.com/shuoce/sub/main/share/fixed.txt"


# =========================
# 输出文件
# =========================

nodes_file = "nodes.txt"
nodes_new_file = "nodes_new.txt"
sub_file = "sub.txt"
clash_file = "clash.yaml"


# =========================
# share 订阅文件
# =========================

share_dir = "share"

share_sub_file = os.path.join(share_dir, "a.txt")
share_clash_file = os.path.join(share_dir, "clash.yaml")


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
        if grp.get("status") == 1:
            continue
        if "免费" in (grp.get("name") or ""):
            continue
        for n in grp.get("node") or []:
            if n.strip():
                nodes.append(n.strip())

    # 去重
    seen = set()
    unique_nodes = []

    for n in nodes:
        if n not in seen:
            seen.add(n)
            unique_nodes.append(n)

    return unique_nodes


# =========================
# 2. VMess 名称处理
# =========================

def process_vmess(line):
    try:
        data = line[8:]

        data += "=" * (-len(data) % 4)

        obj = json.loads(
            base64.b64decode(data).decode("utf-8")
        )

        name = obj.get("ps", "")

        if not name.endswith("丨峰"):
            obj["ps"] = name + "丨峰"

        new = base64.b64encode(
            json.dumps(
                obj,
                ensure_ascii=False,
                separators=(",", ":")
            ).encode("utf-8")
        ).decode("utf-8")

        return "vmess://" + new

    except Exception:
        return line


# =========================
# 3. 普通节点名称处理
# =========================

def process_line(line):

    if line.startswith("vmess://"):
        return process_vmess(line)

    if "#" in line:
        url, name = line.rsplit("#", 1)

        name = urllib.parse.unquote(name)

        if not name.endswith("丨峰"):
            name += "丨峰"

        return url + "#" + urllib.parse.quote(name)

    return line


# =========================
# 4. 生成 nodes_new.txt
#    生成 Base64 sub.txt
# =========================

def gen_sub(nodes):

    result = [
        process_line(n)
        for n in nodes
    ]

    # -------------------------
    # 合并固定节点
    # -------------------------

    fixed = ""

    try:
        with urllib.request.urlopen(
            FIXED_URL,
            timeout=15
        ) as r:

            fixed = r.read().decode("utf-8").strip()

        if fixed:
            result.append(fixed)

    except Exception as e:
        print(f"读取 fixed.txt 失败: {e}")


    # -------------------------
    # 生成最终节点文本
    # -------------------------

    final_text = "\n".join(result)


    # -------------------------
    # nodes_new.txt
    # -------------------------

    with open(
        nodes_new_file,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(final_text)


    # -------------------------
    # sub.txt
    # Base64 编码
    # -------------------------

    encoded = base64.b64encode(
        final_text.encode("utf-8")
    ).decode("utf-8")


    with open(
        sub_file,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(encoded)


    return len(result)


# =========================
# 5. Clash 参数读取
# =========================

def get(params, key, default=None):

    return (
        params.get(key, [default])[0]
        if key in params
        else default
    )


# =========================
# 6. VLESS 解析
# =========================

def decode_vless(line):

    try:

        u = urllib.parse.urlparse(line)

        p = urllib.parse.parse_qs(u.query)

        proxy = {
            "name": (
                urllib.parse.unquote(u.fragment)
                if u.fragment
                else "VLESS节点"
            ),
            "type": "vless",
            "server": u.hostname,
            "port": u.port,
            "uuid": u.username,
            "udp": True,
        }


        security = get(p, "security")


        if security == "tls":
            proxy["tls"] = True


        if security == "reality":

            proxy["tls"] = True

            proxy["reality-opts"] = {
                "public-key": get(p, "pbk", ""),
                "short-id": get(p, "sid", ""),
            }


        sni = get(p, "sni")

        if sni:
            proxy["servername"] = sni


        flow = get(p, "flow")

        if flow:
            proxy["flow"] = flow


        fp = get(p, "fp")

        if fp:
            proxy["client-fingerprint"] = fp


        net = (
            get(p, "type")
            or get(p, "net")
        )


        if net == "ws":

            proxy["network"] = "ws"

            proxy["ws-opts"] = {
                "path": get(p, "path", "/"),
                "headers": {
                    "Host": get(
                        p,
                        "host",
                        u.hostname
                    )
                },
            }


        elif net == "grpc":

            proxy["network"] = "grpc"

            proxy["grpc-opts"] = {
                "grpc-service-name":
                    get(p, "serviceName", "")
            }


        return proxy


    except Exception as e:

        print(f"VLESS解析失败: {e}")

        return None


# =========================
# 7. VMess 解析
# =========================

def decode_vmess(line):

    try:

        data = line.replace(
            "vmess://",
            ""
        )

        data += "=" * (-len(data) % 4)


        obj = json.loads(
            base64.b64decode(data).decode("utf-8")
        )


        proxy = {
            "name": obj.get(
                "ps",
                "VMess节点"
            ),
            "type": "vmess",
            "server": obj["add"],
            "port": int(obj["port"]),
            "uuid": obj["id"],
            "alterId": int(
                obj.get("aid", 0)
            ),
            "cipher": obj.get(
                "scy",
                "auto"
            ),
            "udp": True,
        }


        if obj.get("tls") == "tls":
            proxy["tls"] = True


        if obj.get("net") == "ws":

            proxy["network"] = "ws"

            proxy["ws-opts"] = {
                "path": obj.get(
                    "path",
                    "/"
                ),
                "headers": {
                    "Host": obj.get(
                        "host",
                        obj["add"]
                    )
                },
            }


        return proxy


    except Exception as e:

        print(f"VMess解析失败: {e}")

        return None


# =========================
# 8. Trojan 解析
# =========================

def decode_trojan(line):

    try:

        u = urllib.parse.urlparse(line)

        p = urllib.parse.parse_qs(
            u.query
        )


        proxy = {
            "name": (
                urllib.parse.unquote(
                    u.fragment
                )
                if u.fragment
                else "Trojan节点"
            ),
            "type": "trojan",
            "server": u.hostname,
            "port": u.port,
            "password": u.username,
            "udp": True,
            "tls": True,
        }


        sni = get(
            p,
            "sni"
        )

        if sni:
            proxy["sni"] = sni


        return proxy


    except Exception as e:

        print(f"Trojan解析失败: {e}")

        return None


# =========================
# 9. 生成 Clash 配置
# =========================

def gen_clash():

    proxies = []


    with open(
        nodes_new_file,
        "r",
        encoding="utf-8"
    ) as f:

        for line in f:

            line = line.strip()

            if not line:
                continue

            if line.startswith("#"):
                continue


            if line.startswith("vmess://"):

                pr = decode_vmess(line)


            elif line.startswith("vless://"):

                pr = decode_vless(line)


            elif line.startswith("trojan://"):

                pr = decode_trojan(line)


            else:

                pr = None


            if pr:
                proxies.append(pr)


    names = [
        p["name"]
        for p in proxies
    ]


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

                "url":
                    "https://www.gstatic.com/generate_204",

                "interval": 300,

                "proxies":
                    list(names),
            },

            {
                "name": "手动选择",

                "type": "select",

                "proxies":
                    ["自动选择"] + list(names),
            },
        ],

        "rules": [
            "MATCH,自动选择"
        ],
    }


    with open(
        clash_file,
        "w",
        encoding="utf-8"
    ) as f:

        yaml.dump(
            config,
            f,
            allow_unicode=True,
            sort_keys=False
        )


    return len(proxies)


# =========================
# 10. 同步订阅到 share/
# =========================

def sync_share():

    # 确保 share 目录存在
    os.makedirs(
        share_dir,
        exist_ok=True
    )


    # -------------------------
    # sub.txt → share/a.txt
    # -------------------------

    shutil.copyfile(
        sub_file,
        share_sub_file
    )


    # -------------------------
    # clash.yaml → share/clash.yaml
    # -------------------------

    shutil.copyfile(
        clash_file,
        share_clash_file
    )


    print(
        f"已同步: {sub_file} → {share_sub_file}"
    )

    print(
        f"已同步: {clash_file} → {share_clash_file}"
    )


# =========================
# 主程序
# =========================

if __name__ == "__main__":

    # 1. API 拉取
    nodes = fetch_nodes()

    print(
        f"API拉取: {len(nodes)} 个节点"
    )


    # 2. 保存原始节点
    with open(
        nodes_file,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(
            "\n".join(nodes) + "\n"
        )


    # 3. 生成 sub.txt
    total = gen_sub(nodes)


    # 4. 生成 clash.yaml
    n_clash = gen_clash()


    # 5. 同步到 share/
    sync_share()


    # 6. 输出结果
    print(
        f"nodes_new.txt: {total} 行"
    )

    print(
        f"sub.txt / share/a.txt 已生成"
    )

    print(
        f"clash.yaml / share/clash.yaml "
        f"已生成, clash 代理数: {n_clash}"
        )
