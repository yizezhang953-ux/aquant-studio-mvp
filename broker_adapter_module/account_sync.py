from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .read_only_broker_adapter import ReadOnlyBrokerAdapter
except ImportError:
    from read_only_broker_adapter import ReadOnlyBrokerAdapter


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync read-only broker account snapshot")
    parser.add_argument("--snapshot", default="broker_adapter_module/configs/read_only_broker_snapshot.json")
    parser.add_argument("--output", default="broker_adapter_module/output/read_only_account_snapshot.json")
    args = parser.parse_args()
    adapter = ReadOnlyBrokerAdapter(Path(args.snapshot))
    snapshot = adapter.export_normalized_snapshot()
    write_json(Path(args.output), snapshot)
    print(json.dumps({"ok": True, "mode": "read_only", "output": args.output}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
