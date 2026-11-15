"""Tushare Pro HTTP API (token required): CITIC industry membership and whole-market daily tables,
aggregated into daily sector data (return, turnover, float market value, active buy / sell amounts).

Tushare has no ready-made "active buy amount per CITIC industry", so it is built from stocks:
``moneyflow`` gives each stock's buy / sell amounts by order size ("数据基于主动买卖单统计"); summing the
four sizes gives the stock's active buy and active sell amounts, and stocks are summed by industry.
Sector returns are float-market-value weighted from the constituents, close to but not identical
with the CITIC index. Points needed: ci_index_member 5000, moneyflow 2000 (tushare.pro/document/2).
"""
from __future__ import annotations

import json
import time
import urllib.request
from typing import Any, Callable

API_URL = "http://api.tushare.pro"  # the endpoint the official SDK posts to
PAGE = 5000

# The 40 sectors of 华泰《行业资金流向图应用于行业轮动》: CITIC level-1 industries, with eight of them
# (有色金属、电力及公用事业、汽车、食品饮料、农林牧渔、医药、非银行金融、通信) replaced by level-2 industries.
CITIC40 = [
    "石油石化", "煤炭", "工业金属", "稀有金属", "贵金属", "钢铁", "基础化工", "建材", "机械", "电力设备及新能源",
    "国防军工", "汽车零部件", "乘用车", "商用车", "家电", "酒类", "消费者服务", "传媒", "食品", "饮料", "中药生产",
    "种植业", "畜牧业", "商贸零售", "纺织服装", "轻工制造", "银行", "保险", "证券", "房地产", "计算机", "电子",
    "通信设备", "生物医药", "化学制药", "交通运输", "发电及电网", "环保及公用事业", "电信运营", "建筑",
]

Poster = Callable[[dict[str, Any]], dict[str, Any]]


class TushareError(RuntimeError):
    pass


def _post(body: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(API_URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - fixed host
        return json.loads(response.read().decode("utf-8"))


def query(token: str, api_name: str, params: dict[str, Any], fields: str = "", post: Poster | None = None,
          retries: int = 3) -> list[dict[str, Any]]:
    """Rows of one API call as dicts. Waits and retries when the per-minute limit is hit."""
    post = post or _post
    for attempt in range(retries + 1):
        try:
            reply = post({"api_name": api_name, "token": token, "params": params, "fields": fields})
        except OSError as exc:
            if attempt == retries:
                raise TushareError(f"连不上 Tushare：{exc}") from exc
            time.sleep(2 * (attempt + 1))
            continue
        if reply.get("code") == 0:
            data = reply.get("data") or {}
            names = data.get("fields") or []
            return [dict(zip(names, item)) for item in data.get("items") or []]
        message = str(reply.get("msg") or reply.get("code"))
        if "每分钟" in message and attempt < retries:  # rate limit: wait for the next minute
            time.sleep(61)
            continue
        raise TushareError(f"Tushare {api_name}：{message}")
    raise TushareError(f"Tushare {api_name}：重试后仍然失败")


def query_all(token: str, api_name: str, params: dict[str, Any], fields: str = "", post: Poster | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    while True:
        page = query(token, api_name, {**params, "limit": PAGE, "offset": len(rows)}, fields, post)
        rows += page
        if len(page) < PAGE:
            return rows


def _clean(name: str | None) -> str:
    return (name or "").replace("Ⅱ", "").replace("II", "").replace("(中信)", "").replace("（中信）", "").strip()


def fetch_membership(token: str, post: Poster | None = None) -> list[dict[str, Any]]:
    """Current and past CITIC memberships: [{ts_code, sector, sector_code, in_date, out_date}] for the 40 sectors."""
    fields = "l1_code,l1_name,l2_code,l2_name,ts_code,in_date,out_date,is_new"
    rows = query_all(token, "ci_index_member", {"is_new": "Y"}, fields, post) + \
        query_all(token, "ci_index_member", {"is_new": "N"}, fields, post)
    out = []
    for row in rows:
        l1, l2 = _clean(row.get("l1_name")), _clean(row.get("l2_name"))
        if l2 in CITIC40:
            sector, code = l2, row.get("l2_code")
        elif l1 in CITIC40:
            sector, code = l1, row.get("l1_code")
        else:
            continue
        out.append({"ts_code": row["ts_code"], "sector": sector, "sector_code": code or sector,
                    "in_date": row.get("in_date") or "00000000", "out_date": row.get("out_date") or "99999999"})
    return out


def sector_of(membership: list[dict[str, Any]], day: str) -> dict[str, tuple[str, str]]:
    """{ts_code: (sector_code, sector)} on ``day`` (YYYYMMDD)."""
    return {m["ts_code"]: (m["sector_code"], m["sector"]) for m in membership if m["in_date"] <= day < m["out_date"]}


def _f(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def fetch_sector_day(token: str, day: str, membership: list[dict[str, Any]], post: Poster | None = None) -> list[dict[str, Any]]:
    """One trading day (YYYY-MM-DD) aggregated by sector, amounts in CNY. Empty when the market was closed."""
    ymd = day.replace("-", "")
    quotes = {r["ts_code"]: r for r in query(token, "daily", {"trade_date": ymd}, "ts_code,pct_chg,amount", post)}
    if not quotes:
        return []
    basics = {r["ts_code"]: r for r in query(token, "daily_basic", {"trade_date": ymd}, "ts_code,circ_mv", post)}
    flows = {r["ts_code"]: r for r in query(
        token, "moneyflow", {"trade_date": ymd},
        "ts_code,buy_sm_amount,sell_sm_amount,buy_md_amount,sell_md_amount,buy_lg_amount,sell_lg_amount,"
        "buy_elg_amount,sell_elg_amount", post)}
    sectors: dict[str, dict[str, Any]] = {}
    for ts_code, (code, name) in sector_of(membership, ymd).items():
        quote = quotes.get(ts_code)
        if quote is None:
            continue
        s = sectors.setdefault(code, {"code": code, "name": name, "trade_date": day, "amount": 0.0, "float_mv": 0.0,
                                      "buy_amount": 0.0, "sell_amount": 0.0, "_prev_mv": 0.0, "_gain": 0.0, "stocks": 0})
        mv = _f((basics.get(ts_code) or {}).get("circ_mv")) * 1e4  # 万元
        pct = _f(quote.get("pct_chg")) / 100
        prev_mv = mv / (1 + pct) if pct > -1 else 0.0
        s["amount"] += _f(quote.get("amount")) * 1e3  # 千元
        s["float_mv"] += mv
        s["_prev_mv"] += prev_mv
        s["_gain"] += prev_mv * pct
        flow = flows.get(ts_code)
        if flow:
            s["buy_amount"] += sum(_f(flow.get(f"buy_{k}_amount")) for k in ("sm", "md", "lg", "elg")) * 1e4
            s["sell_amount"] += sum(_f(flow.get(f"sell_{k}_amount")) for k in ("sm", "md", "lg", "elg")) * 1e4
        s["stocks"] += 1
    out = []
    for s in sectors.values():
        s["ret"] = s.pop("_gain") / s["_prev_mv"] if s["_prev_mv"] else 0.0
        s.pop("_prev_mv")
        if not flows:  # moneyflow not published for this day: leave the flow fields empty, not zero
            s["buy_amount"] = s["sell_amount"] = None
        out.append(s)
    return out
