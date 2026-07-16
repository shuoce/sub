#!/usr/bin/env python3

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parent

# 手动维护的节点文件，只读取，不修改。
SUB_FILE = ROOT / "sub.txt"

# 机器人维护的节点数据库。
MANAGED_FILE = ROOT / "managed.txt"

# 机器人新收到的节点文件，处理完成后清空。
INBOX_FILE = ROOT / "inbox.txt"

# 最终生成的订阅文件。
SHARE_FILES = [
    ROOT / "share" / "a.txt",
    ROOT / "share" / "mao.txt",
]


SUPPORTED_SCHEMES = {
    "trojan",
    "vmess",
    "vless",
    "hysteria2",
    "hy2",
    "ss",
    "shadowsocks",
    "socks5",
}


# 国家顺序同时决定输出顺序。
# 每个国家的编号相互独立。
COUNTRIES = [
    {
        "code": "HK",
        "flag": "🇭🇰",
        "name": "香港",
        "aliases": (
            "香港",
            "hongkong",
            "hong kong",
            "hong-kong",
            "hk",
        ),
    },
    {
        "code": "JP",
        "flag": "🇯🇵",
        "name": "日本",
        "aliases": (
            "日本",
            "japan",
            "tokyo",
            "osaka",
            "nagoya",
            "okinawa",
            "sapporo",
            "jp",
        ),
    },
    {
        "code": "SG",
        "flag": "🇸🇬",
        "name": "新加坡",
        "aliases": (
            "新加坡",
            "狮城",
            "singapore",
            "sg",
        ),
    },
    {
        "code": "US",
        "flag": "🇺🇸",
        "name": "美国",
        "aliases": (
            "美国",
            "米国",
            "usa",
            "us",
            "united states",
            "america",
            "纽约",
            "洛杉矶",
            "旧金山",
            "西雅图",
            "芝加哥",
            "硅谷",
            "new york",
            "los angeles",
            "san francisco",
            "seattle",
            "chicago",
        ),
    },
    {
        "code": "TW",
        "flag": "🇹🇼",
        "name": "台湾",
        "aliases": (
            "台湾",
            "台灣",
            "taiwan",
            "taipei",
            "tw",
        ),
    },
    {
        "code": "KR",
        "flag": "🇰🇷",
        "name": "韩国",
        "aliases": (
            "韩国",
            "韓國",
            "korea",
            "south korea",
            "seoul",
            "busan",
            "kr",
        ),
    },
    {
        "code": "MY",
        "flag": "🇲🇾",
        "name": "马来西亚",
        "aliases": (
            "马来西亚",
            "馬來西亞",
            "malaysia",
            "kuala lumpur",
            "kualalumpur",
            "my",
        ),
    },
    {
        "code": "DE",
        "flag": "🇩🇪",
        "name": "德国",
        "aliases": (
            "德国",
            "德國",
            "germany",
            "berlin",
            "frankfurt",
            "munich",
            "de",
        ),
    },
    {
        "code": "FR",
        "flag": "🇫🇷",
        "name": "法国",
        "aliases": (
            "法国",
            "法國",
            "france",
            "paris",
            "marseille",
            "fr",
        ),
    },
    {
        "code": "GB",
        "flag": "🇬🇧",
        "name": "英国",
        "aliases": (
            "英国",
            "英國",
            "uk",
            "united kingdom",
            "england",
            "london",
            "manchester",
            "gb",
        ),
    },
    {
        "code": "RU",
        "flag": "🇷🇺",
        "name": "俄罗斯",
        "aliases": (
            "俄罗斯",
            "俄羅斯",
            "russia",
            "moscow",
            "st petersburg",
            "ru",
        ),
    },
    {
        "code": "CA",
        "flag": "🇨🇦",
        "name": "加拿大",
        "aliases": (
            "加拿大",
            "canada",
            "toronto",
            "vancouver",
            "montreal",
            "ca",
        ),
    },
    {
        "code": "AU",
        "flag": "🇦🇺",
        "name": "澳大利亚",
        "aliases": (
            "澳大利亚",
            "澳洲",
            "australia",
            "sydney",
            "melbourne",
            "perth",
            "au",
        ),
    },
    {
        "code": "NL",
        "flag": "🇳🇱",
        "name": "荷兰",
        "aliases": (
            "荷兰",
            "荷蘭",
            "netherlands",
            "holland",
            "amsterdam",
            "nl",
        ),
    },
    {
        "code": "AT",
        "flag": "🇦🇹",
        "name": "奥地利",
        "aliases": (
            "奥地利",
            "奧地利",
            "austria",
            "vienna",
            "at",
        ),
    },
    {
        "code": "CH",
        "flag": "🇨🇭",
        "name": "瑞士",
        "aliases": (
            "瑞士",
            "switzerland",
            "zurich",
            "geneva",
            "ch",
        ),
    },
    {
        "code": "SE",
        "flag": "🇸🇪",
        "name": "瑞典",
        "aliases": (
            "瑞典",
            "sweden",
            "stockholm",
            "se",
        ),
    },
    {
        "code": "NO",
        "flag": "🇳🇴",
        "name": "挪威",
        "aliases": (
            "挪威",
            "norway",
            "oslo",
            "no",
        ),
    },
    {
        "code": "FI",
        "flag": "🇫🇮",
        "name": "芬兰",
        "aliases": (
            "芬兰",
            "芬蘭",
            "finland",
            "helsinki",
            "fi",
        ),
    },
    {
        "code": "IT",
        "flag": "🇮🇹",
        "name": "意大利",
        "aliases": (
            "意大利",
            "italy",
            "rome",
            "milan",
            "it",
        ),
    },
    {
        "code": "ES",
        "flag": "🇪🇸",
        "name": "西班牙",
        "aliases": (
            "西班牙",
            "spain",
            "madrid",
            "barcelona",
            "es",
        ),
    },
    {
        "code": "PL",
        "flag": "🇵🇱",
        "name": "波兰",
        "aliases": (
            "波兰",
            "波蘭",
            "poland",
            "warsaw",
            "pl",
        ),
    },
    {
        "code": "TR",
        "flag": "🇹🇷",
        "name": "土耳其",
        "aliases": (
            "土耳其",
            "turkey",
            "istanbul",
            "tr",
        ),
    },
    {
        "code": "IN",
        "flag": "🇮🇳",
        "name": "印度",
        "aliases": (
            "印度",
            "india",
            "mumbai",
            "delhi",
            "bangalore",
            "in",
        ),
    },
    {
        "code": "ID",
        "flag": "🇮🇩",
        "name": "印度尼西亚",
        "aliases": (
            "印度尼西亚",
            "印尼",
            "indonesia",
            "jakarta",
            "id",
        ),
    },
    {
        "code": "TH",
        "flag": "🇹🇭",
        "name": "泰国",
        "aliases": (
            "泰国",
            "泰國",
            "thailand",
            "bangkok",
            "th",
        ),
    },
    {
        "code": "VN",
        "flag": "🇻🇳",
        "name": "越南",
        "aliases": (
            "越南",
            "vietnam",
            "hanoi",
            "ho chi minh",
            "vn",
        ),
    },
    {
        "code": "PH",
        "flag": "🇵🇭",
        "name": "菲律宾",
        "aliases": (
            "菲律宾",
            "菲律賓",
            "philippines",
            "manila",
            "ph",
        ),
    },
    {
        "code": "BR",
        "flag": "🇧🇷",
        "name": "巴西",
        "aliases": (
            "巴西",
            "brazil",
            "sao paulo",
            "rio",
            "br",
        ),
    },
    {
        "code": "MX",
        "flag": "🇲🇽",
        "name": "墨西哥",
        "aliases": (
            "墨西哥",
            "mexico",
            "mexico city",
            "mx",
        ),
    },
    {
        "code": "ZA",
        "flag": "🇿🇦",
        "name": "南非",
        "aliases": (
            "南非",
            "south africa",
            "johannesburg",
            "cape town",
            "za",
        ),
    },
    {
        "code": "AE",
        "flag": "🇦🇪",
        "name": "阿联酋",
        "aliases": (
            "阿联酋",
            "阿聯酋",
            "迪拜",
            "dubai",
            "uae",
            "united arab emirates",
            "ae",
        ),
    },
    {
        "code": "IL",
        "flag": "🇮🇱",
        "name": "以色列",
        "aliases": (
            "以色列",
            "israel",
            "tel aviv",
            "il",
        ),
    },
]


def read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []

    lines = []

    for raw_line in path.read_text(
        encoding="utf-8-sig"
    ).splitlines():
        line = raw_line.strip()

        if line and not line.startswith("#"):
            lines.append(line)

    return lines


def write_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    content = "\n".join(lines)

    if content:
        content += "\n"

    path.write_text(
        content,
        encoding="utf-8",
        newline="\n",
    )


def is_node(line: str) -> bool:
    match = re.match(
        r"^(trojan|vmess|vless|hysteria2|hy2|ss|shadowsocks|socks5)://",
        line,
        re.IGNORECASE,
    )

    return bool(
        match
        and match.group(1).lower() in SUPPORTED_SCHEMES
    )


def decode_base64(value: str) -> bytes | None:
    try:
        value += "=" * (-len(value) % 4)

        return base64.urlsafe_b64decode(
            value.encode("ascii")
        )

    except (ValueError, UnicodeError):
        return None


def encode_base64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode(
        "ascii"
    ).rstrip("=")


def get_fragment(line: str) -> str:
    try:
        return unquote(urlsplit(line).fragment)

    except ValueError:
        return ""


def vmess_data(line: str) -> dict | None:
    if not line.lower().startswith("vmess://"):
        return None

    payload = line[len("vmess://"):].split("#", 1)[0]
    decoded = decode_base64(payload)

    if decoded is None:
        return None

    try:
        data = json.loads(decoded.decode("utf-8"))

    except (UnicodeError, json.JSONDecodeError):
        return None

    return data if isinstance(data, dict) else None


def vmess_remark(line: str) -> str:
    data = vmess_data(line)

    if data is not None:
        return str(data.get("ps", ""))

    return get_fragment(line)


def node_text_parts(line: str) -> list[str]:
    parts = [get_fragment(line)]

    if line.lower().startswith("vmess://"):
        parts.append(vmess_remark(line))

    try:
        parsed = urlsplit(line)

        parts.extend(
            [
                unquote(parsed.hostname or ""),
                unquote(parsed.netloc),
            ]
        )

    except ValueError:
        pass

    return parts


def contains_alias(text: str, alias: str) -> bool:
    # 两个字母的国家代码使用边界匹配，降低误识别概率。
    if len(alias) == 2 and alias.isascii() and alias.isalpha():
        return bool(
            re.search(
                rf"(?<![a-z]){re.escape(alias)}(?![a-z])",
                text,
                re.IGNORECASE,
            )
        )

    return alias in text


def detect_country(line: str) -> dict | None:
    text = " ".join(node_text_parts(line)).lower()

    for country in COUNTRIES:
        for alias in country["aliases"]:
            if contains_alias(text, alias.lower()):
                return country

    return None


def node_key(line: str) -> str:
    """
    生成节点唯一键。

    普通协议忽略 URL 备注。
    VMess 忽略 URL fragment 和 JSON 中的 ps 字段，
    防止同一个 VMess 节点因备注不同而重复导入。
    """
    try:
        if line.lower().startswith("vmess://"):
            data = vmess_data(line)

            if data is not None:
                data = dict(data)
                data.pop("ps", None)

                normalized = json.dumps(
                    data,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )

                return f"vmess://{normalized}"

        parsed = urlsplit(line)

        return urlunsplit(
            (
                parsed.scheme.lower(),
                parsed.netloc,
                parsed.path,
                parsed.query,
                "",
            )
        )

    except (TypeError, ValueError):
        return line.split("#", 1)[0].strip().lower()


def existing_number(
    line: str,
    country: dict,
) -> int | None:
    remark = (
        vmess_remark(line)
        if line.lower().startswith("vmess://")
        else get_fragment(line)
    )

    patterns = [
        rf"{re.escape(country['name'])}\s*0*(\d+)",
        rf"{re.escape(country['code'])}\s*0*(\d+)",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            remark,
            re.IGNORECASE,
        )

        if match:
            return int(match.group(1))

    return None


def set_fragment(line: str, name: str) -> str:
    parsed = urlsplit(line)

    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.query,
            quote(name, safe=""),
        )
    )


def rename_node(line: str, name: str) -> str:
    if line.lower().startswith("vmess://"):
        data = vmess_data(line)

        if data is not None:
            data["ps"] = name

            encoded = encode_base64(
                json.dumps(
                    data,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            )

            return f"vmess://{encoded}"

    return set_fragment(line, name)


def unique_nodes(
    lines: list[str],
    existing_keys: set[str] | None = None,
) -> list[str]:
    """
    按节点连接参数去重。

    existing_keys 用于传入 sub.txt 中已有的节点，
    这样机器人不会把手动节点再次加入 managed.txt。
    """
    seen = set(existing_keys or ())
    result = []

    for line in lines:
        if not is_node(line):
            continue

        key = node_key(line)

        if key in seen:
            continue

        seen.add(key)
        result.append(line)

    return result


def normalize_nodes(lines: list[str]) -> list[str]:
    """
    生成最终订阅内容。

    这里不做去重，因为去重已经在 sub.txt 和
    managed.txt/inbox.txt 合并时完成。

    已识别国家的节点按 COUNTRIES 顺序输出并重新命名。
    无法识别国家的节点保留原始内容，并追加到末尾。
    """
    all_nodes = [
        line
        for line in lines
        if is_node(line)
    ]

    grouped = {
        country["code"]: []
        for country in COUNTRIES
    }

    max_numbers = {
        country["code"]: 0
        for country in COUNTRIES
    }

    unknown_nodes = []

    for line in all_nodes:
        country = detect_country(line)

        if country is None:
            # 未知国家节点保留原始备注和原始内容。
            unknown_nodes.append(line)
            continue

        code = country["code"]
        number = existing_number(line, country)

        if number is not None:
            max_numbers[code] = max(
                max_numbers[code],
                number,
            )

        grouped[code].append((line, number))

    result = []

    for country in COUNTRIES:
        code = country["code"]
        next_number = max_numbers[code] + 1

        for line, number in grouped[code]:
            if number is None:
                number = next_number
                next_number += 1

            remark = (
                f"{country['flag']}"
                f"{country['name']}"
                f"{number:02d}"
                f"|峰"
            )

            result.append(rename_node(line, remark))

    # 无法识别国家的节点追加到所有已识别国家之后。
    result.extend(unknown_nodes)

    return result


def main() -> None:
    # sub.txt 是手动维护文件，只读，绝不覆盖。
    manual_nodes = [
        line
        for line in read_lines(SUB_FILE)
        if is_node(line)
    ]

    # managed.txt 保存机器人历史管理节点。
    old_managed_nodes = read_lines(MANAGED_FILE)

    # inbox.txt 保存本次新导入的节点。
    inbox_nodes = read_lines(INBOX_FILE)

    # 手动节点优先作为去重基准。
    manual_keys = {
        node_key(line)
        for line in manual_nodes
    }

    # 清理 managed.txt 中的无效节点、重复节点，
    # 同时移除已经存在于 sub.txt 的节点。
    managed_nodes = unique_nodes(
        old_managed_nodes,
        existing_keys=manual_keys,
    )

    managed_keys = {
        node_key(line)
        for line in managed_nodes
    }

    # 只将真正的新节点加入机器人管理列表。
    new_managed_nodes = unique_nodes(
        inbox_nodes,
        existing_keys=manual_keys | managed_keys,
    )

    managed_nodes.extend(new_managed_nodes)

    # 保存机器人管理文件。
    write_lines(MANAGED_FILE, managed_nodes)

    # sub.txt 和 managed.txt 合并生成最终订阅文件。
    merged_nodes = normalize_nodes(
        manual_nodes + managed_nodes
    )

    for share_file in SHARE_FILES:
        write_lines(share_file, merged_nodes)

    # 只清空收件箱。
    # sub.txt 和 managed.txt 都不会被清空。
    write_lines(INBOX_FILE, [])


if __name__ == "__main__":
    main()
