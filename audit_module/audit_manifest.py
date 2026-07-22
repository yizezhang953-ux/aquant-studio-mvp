from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(config: dict[str, Any], root: Path) -> dict[str, Any]:
    artifacts = []
    missing = []
    for item in config.get("artifacts", []):
        path = root / item["path"]
        if not path.exists():
            missing.append(item)
            continue
        artifacts.append(
            {
                "id": item["id"],
                "category": item["category"],
                "path": item["path"],
                "sha256": sha256_file(path),
                "size": path.stat().st_size,
                "last_modified": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat(),
            }
        )
    return {
        "ok": len(missing) == 0,
        "manifest_id": config.get("manifest_id", "audit_manifest"),
        "generated_at": now_iso(),
        "artifact_count": len(artifacts),
        "missing_count": len(missing),
        "artifacts": artifacts,
        "missing": missing,
        "live_trading_status": "blocked_for_live_trading",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build AQuant audit manifest")
    parser.add_argument("--config", default="audit_module/configs/audit_manifest_config.json")
    parser.add_argument("--output", default="audit_module/output/stage11_audit_manifest.json")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    manifest = build_manifest(read_json(Path(args.config)), root)
    write_json(Path(args.output), manifest)
    print(json.dumps({"ok": manifest["ok"], "artifacts": manifest["artifact_count"], "missing": manifest["missing_count"], "output": args.output}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
