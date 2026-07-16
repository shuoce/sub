#!/usr/bin/env python3
"""Merge inbox nodes into the subscription files and normalize their remarks."""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parent
INBOX_FILE = ROOT / "inbox.txt"
SUB_FILE = ROOT / "sub" / "sub.txt"
SHARE_FILES = [
    ROOT / "sub" / "share" / "a.txt",
    ROOT / "sub" / "share" / "mao.txt",
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

# Country keywords are intentionally limited to Japan and Hong Kong.
JAPAN_KEYWORDS = (
    "日本",
    "东京",
    "大阪",
    "名古屋",
    "冲绳",
    "札幌",
    "japan",
    "tokyo",
    "osaka",
    "nagoya",
    "okinawa",
    "sapporo",
    "jp",
)

HONG_KONG_KEYWORDS = (
    "香港",
    "hongkong",
    "hong kong",
    "hk",
)

NODE_PATTERN = re.compile(
    r"^(?P<scheme>trojan|vmess|vless|hysteria2|hy2|ss|shadowsocks|socks5)://",
    re.IGNORECASE,
)

NUMBER_PATTERN = {
    "JP": re.compile(r"(?:日本|japan|jp).*?(\d+)", re.IGNORECASE),
    "HK": re.compile(r"(?:香港|hong\s*kong|hk).*?(\d+)", re.IGNORECASE),
}


def read_lines(path: Path) -> list[str]:
    """Read non-empty, non-comment lines while preserving node order."""
    if not path.exists():
        return []

    result = []
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        result.append(line)
    return result


def is_node(line: str) -> bool:
    match = NODE_PATTERN.match(line)
    return bool(match and match.group("scheme").lower() in SUPPORTED_SCHEMES)


def decode_base64(value: str) -> bytes | None:
    try:
        padded = value + "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii"))
    except (ValueError, UnicodeError):
        return None


def encode_base64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def vmess_remark(line: str) -> str:
    """Read the vmess name field, falling back to its URL fragment."""
    payload = line[len("vmess://") :].split("#", 1)[0]
    decoded = decode_base64(payload)
    if decoded is not None:
        try:
            data = json.loads(decoded.decode("utf-8"))
            if isinstance(data, dict) and data.get("ps"):
                return str(data["ps"])
        except (UnicodeError, json.JSONDecodeError):
            pass

    return get_fragment(line)


def get_fragment(line: str) -> str:
    try:
        return unquote(urlsplit(line).fragment)
    except ValueError:
        return ""


def detect_country(line: str) -> str | None:
    """Detect JP/HK from the remark and host, without classifying other regions."""
    haystacks = [get_fragment(line)]
    scheme = line.split("://", 1)[0].lower()

    if scheme == "vmess":
        haystacks.insert(0, vmess_remark(line))

    try:
        parsed = urlsplit(line)
        haystacks.append(unquote(parsed.hostname or ""))
        haystacks.append(unquote(parsed.netloc))
    except ValueError:
        pass

    text = " ".join(haystacks).lower()

    # Check Hong Kong first because "hk" can occur in some Japan labels.
    if contains_keyword(text, HONG_KONG_KEYWORDS):
        return "HK"
    if contains_keyword(text, JAPAN_KEYWORDS):
        return "JP"
    return None


def contains_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    for keyword in keywords:
        if keyword in ("jp", "hk"):
            if re.search(rf"(?<![a-z]){re.escape(keyword)}(?![a-z])", text):
                return True
        elif keyword in text:
            return True
    return False


def node_key(line: str) -> str:
    """Remove only the remark, so duplicate detection uses the node URL itself."""
    try:
        parsed = urlsplit(line)
        return urlunsplit((parsed.scheme.lower(), parsed.netloc, parsed.path, parsed.query, ""))
    except ValueError:
        return line.split("#", 1)[0].strip().lower()


def existing_number(line: str, country: str) -> int | None:
    remark = vmess_remark(line) if line.lower().startswith("vmess://") else get_fragment(line)
    match = NUMBER_PATTERN[country].search(remark)
    return int(match.group(1)) if match else None


def set_fragment(line: str, name: str) -> str:
    """Set a percent-encoded URL fragment while leaving the node credentials intact."""
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
    """Rename every supported URI format, including vmess JSON's ps field."""
    if line.lower().startswith("vmess://"):
        payload = line[len("vmess://") :].split("#", 1)[0]
        decoded = decode_base64(payload)
        if decoded is not None:
            try:
                data = json.loads(decoded.decode("utf-8"))
                if isinstance(data, dict):
                    data["ps"] = name
                    encoded = encode_base64(
                        json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                    )
                    return f"vmess://{encoded}"
            except (UnicodeError, json.JSONDecodeError):
                pass

    return set_fragment(line, name)


def normalize_nodes(lines: list[str]) -> list[str]:
    """Deduplicate first, retain existing valid numbers, then number new nodes."""
    unique: list[str] = []
    seen: set[str] = set()

    for line in lines:
        if not is_node(line):
            continue
        key = node_key(line)
        if key in seen:
            continue
        seen.add(key)
        unique.append(line)

    grouped = {"JP": [], "HK": []}
    max_number = {"JP": 0, "HK": 0}

    for line in unique:
        country = detect_country(line)
        if country is None:
            continue
        number = existing_number(line, country)
        if number is not None:
            max_number[country] = max(max_number[country], number)
        grouped[country].append([line, number])

    result: list[str] = []
    for country in ("JP", "HK"):
        next_number = max_number[country] + 1
        label = "日本" if country == "JP" else "香港"
        flag = "🇯🇵" if country == "JP" else "🇭🇰"

        for item in grouped[country]:
            line, number = item
            if number is None:
                number = next_number
                next_number += 1
            item[1] = number
            result.append(rename_node(line, f"{flag}{label}{number:02d}|峰"))

    return result


def write_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(lines)
    if content:
        content += "\n"
    path.write_text(content, encoding="utf-8", newline="\n")


def main() -> None:
    inbox_nodes = read_lines(INBOX_FILE)
    current_nodes = read_lines(SUB_FILE)

    # Existing nodes come first, so duplicate retention follows repository order.
    merged_nodes = normalize_nodes(current_nodes + inbox_nodes)

    write_lines(SUB_FILE, merged_nodes)
    for share_file in SHARE_FILES:
        write_lines(share_file, merged_nodes)

    # Always clear the inbox after it has been consumed.
    write_lines(INBOX_FILE, [])


if __name__ == "__main__":
    main()
