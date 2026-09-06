#!/usr/bin/env python3
"""Validate a story (including resolved includes) without any model calls."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.story_validation import validate_story_data  # noqa: E402
from src.models.story_models import _load_yaml_with_includes  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("story")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    try:
        issues = validate_story_data(_load_yaml_with_includes(args.story))
    except Exception as exc:
        issues = [{"severity": "error", "code": "yaml", "message": str(exc), "path": []}]
    if args.as_json:
        print(json.dumps(issues, ensure_ascii=False, indent=2))
    else:
        for issue in issues:
            print(f"{issue['severity'].upper()}: {'.'.join(map(str, issue['path']))}: {issue['message']}")
        print(f"{sum(i['severity'] == 'error' for i in issues)} errors; "
              f"{sum(i['severity'] == 'warning' for i in issues)} warnings")
    return 1 if any(i["severity"] == "error" for i in issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
