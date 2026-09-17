#!/usr/bin/env python3
"""Create a shareable pseudonymized copy of a debt case JSON file."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path


ROLE_LABELS = {
    "borrower": "借款人",
    "platform": "借款平台",
    "lender": "放款机构",
    "service_provider": "服务机构",
    "guarantor": "担保机构",
    "insurer": "保险机构",
    "compensating_party": "代偿机构",
    "assignee": "受让方",
    "collector": "催收服务方",
}

SENSITIVE_KEYS = {
    "borrower_name": "[BORROWER_NAME]",
    "legal_name": "[PERSON_NAME]",
    "id_number": "[ID_NUMBER]",
    "identity_number": "[ID_NUMBER]",
    "phone": "[PHONE]",
    "mobile": "[PHONE]",
    "email": "[EMAIL]",
    "address": "[ADDRESS]",
    "home_address": "[ADDRESS]",
    "bank_account": "[BANK_ACCOUNT]",
    "bank_card": "[BANK_ACCOUNT]",
    "wechat": "[SOCIAL_ACCOUNT]",
    "qq": "[SOCIAL_ACCOUNT]",
    "username": "[ACCOUNT_NAME]",
}

PATTERNS = [
    ("email", re.compile(r"(?i)(?<![A-Z0-9._%+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![A-Z0-9-])"), "[EMAIL]"),
    ("id_number", re.compile(r"(?<!\d)(?:\d{17}[0-9Xx]|\d{15})(?!\d)"), "[ID_NUMBER]"),
    ("phone", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "[PHONE]"),
    ("bank_account", re.compile(r"(?<!\d)\d{12,19}(?!\d)"), "[BANK_ACCOUNT]"),
    ("local_path", re.compile(r"/(?:Users|home)/[^\s\"'，。；、）)]+"), "[LOCAL_PATH]"),
]


def entity_name_map(data: dict) -> dict[str, str]:
    counters: defaultdict[str, int] = defaultdict(int)
    mapping = {}
    for entity in data.get("entities", []):
        original = entity.get("name")
        if not isinstance(original, str) or not original.strip():
            continue
        role = str(entity.get("role", "entity"))
        counters[role] += 1
        label = ROLE_LABELS.get(role, "参与方")
        mapping[original] = f"{label}{counters[role]}"
    return mapping


def redact_text(value: str, names: dict[str, str], counts: Counter) -> str:
    result = value
    for original in sorted(names, key=len, reverse=True):
        if original in result:
            occurrences = result.count(original)
            result = result.replace(original, names[original])
            counts["entity_name"] += occurrences
    for label, pattern, replacement in PATTERNS:
        result, replacements = pattern.subn(replacement, result)
        counts[label] += replacements
    return result


def redact_value(value: object, names: dict[str, str], counts: Counter, key: str | None = None) -> object:
    if key == "case_name" and isinstance(value, str):
        counts["case_name"] += 1
        return "脱敏案例"
    if key in SENSITIVE_KEYS and value not in (None, ""):
        counts[key] += 1
        return SENSITIVE_KEYS[key]
    if isinstance(value, dict):
        return {item_key: redact_value(item_value, names, counts, item_key) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [redact_value(item, names, counts, key) for item in value]
    if isinstance(value, str):
        return redact_text(value, names, counts)
    return value


def redact_case(data: dict) -> dict:
    source = deepcopy(data)
    names = entity_name_map(source)
    counts: Counter = Counter()
    redacted = redact_value(source, names, counts)
    redacted["redaction_metadata"] = {
        "tool": "debt-cost-checker/scripts/redact_case.py",
        "replacement_counts": dict(sorted(counts.items())),
        "review_required": "自动脱敏不能识别所有自由文本和文件元数据；公开前仍需人工复核，原始PDF和图片需单独处理。",
    }
    return redacted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    try:
        if args.input.resolve() == args.output.resolve():
            raise ValueError("output must be a different file; the original is never overwritten")
        if args.output.exists():
            raise ValueError(f"output already exists: {args.output}")
        data = json.loads(args.input.read_text(encoding="utf-8"))
        redacted = redact_case(data)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(redacted, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"redacted copy written to {args.output}")
        print("manual review is still required before sharing", file=sys.stderr)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
