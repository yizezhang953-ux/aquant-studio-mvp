from __future__ import annotations

from app.services.json_utils import read_json
from app.services.legacy_paths import TEMPLATE_MODULE


TEMPLATE_DIR = TEMPLATE_MODULE / "templates"


def list_templates() -> dict:
    return read_json(TEMPLATE_DIR / "index.json")


def get_template(template_id: str) -> dict | None:
    index = list_templates()
    for item in index["templates"]:
        if item["template_id"] == template_id:
            return {
                "metadata": item,
                "strategy": read_json(TEMPLATE_DIR / item["file"]),
            }
    return None
