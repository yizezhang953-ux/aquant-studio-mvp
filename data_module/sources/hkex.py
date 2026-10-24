"""HK board lots from the public HKEX list of securities (ListOfSecurities.xlsx).

The xlsx is parsed with the standard library (zipfile + XML), so openpyxl is not required.
"""
from __future__ import annotations

import io
import re
import zipfile
from xml.etree import ElementTree as ET

from data_module.sources.http import get_bytes

URLS = [
    "https://www.hkex.com.hk/eng/services/trading/securities/securitieslists/ListOfSecurities.xlsx",
    "https://www.hkex.com.hk/chi/services/trading/securities/securitieslists/ListOfSecurities_c.xlsx",
]
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _col(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def parse_board_lots(data: bytes) -> dict[str, int]:
    """{'00700': 100, ...} from the xlsx bytes."""
    archive = zipfile.ZipFile(io.BytesIO(data))
    shared: list[str] = []
    if "xl/sharedStrings.xml" in archive.namelist():
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        for si in root.findall("m:si", NS):
            shared.append("".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])))
    sheet = next(n for n in sorted(archive.namelist()) if n.startswith("xl/worksheets/sheet"))
    root = ET.fromstring(archive.read(sheet))
    code_i = lot_i = None
    out: dict[str, int] = {}
    for row in root.iter("{%s}row" % NS["m"]):
        values: dict[int, str] = {}
        for cell in row.findall("m:c", NS):
            v = cell.find("m:v", NS)
            inline = cell.find("m:is", NS)
            if v is not None:
                text = shared[int(v.text)] if cell.get("t") == "s" else v.text
            elif inline is not None:
                text = "".join(t.text or "" for t in inline.iter("{%s}t" % NS["m"]))
            else:
                continue
            values[_col(cell.get("r"))] = (text or "").strip()
        if code_i is None:
            for i, text in values.items():
                lower = text.lower()
                if lower in ("stock code", "股份代號", "股份代号"):
                    code_i = i
                if "board lot" in lower or text in ("買賣單位", "买卖单位"):
                    lot_i = i
            if lot_i is None:
                code_i = None
            continue
        code, lot = values.get(code_i, ""), values.get(lot_i, "")
        if code.isdigit() and lot:
            try:
                out[code.zfill(5)] = int(float(lot.replace(",", "")))
            except ValueError:
                continue
    return out


def fetch_board_lots() -> dict[str, int]:
    last_error: Exception | None = None
    for url in URLS:
        try:
            lots = parse_board_lots(get_bytes(url, timeout=60))
            if lots:
                return lots
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"could not load the HKEX securities list: {last_error}")
