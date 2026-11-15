import time

from app.db.session import SessionLocal
from app.models import SectorDaily, User
from app.services import sector_data_service as sectors
from app.services.auth_service import set_admin
from test_app import register

API = "/api/v1/sectors"


def _admin(client):
    headers, _ = register(client, "sector")
    with SessionLocal() as db:
        set_admin(db, db.query(User).order_by(User.id.desc()).first().email)
    return headers


def _wait(client, headers, timeout=30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"{API}/sync", headers=headers).json()["job"]
        if job["status"] != "running":
            return job
        time.sleep(0.1)
    raise AssertionError("sector sync did not finish")


def test_demo_data_then_rotation_backtest(client) -> None:
    headers = _admin(client)
    reader, _ = register(client, "reader")
    assert client.post(f"{API}/sync", headers=reader, json={"provider": "demo", "start_date": "2024-01-01"}).status_code == 403
    assert client.post(f"{API}/sync", headers=headers, json={"provider": "tushare", "start_date": "2024-01-01"}).status_code == 400

    started = client.post(f"{API}/sync", headers=headers, json={
        "provider": "demo", "start_date": "2024-01-01", "end_date": "2025-12-31"})
    assert started.status_code == 200, started.text
    job = _wait(client, headers)
    assert job["status"] == "done" and job["rows"] > 40 * 400, job

    status = client.get(API, headers=reader).json()
    demo = next(u for u in status["universes"] if u["universe"] == "demo")
    assert demo["sectors"] == 40 and demo["has_flow"] and demo["last_date"] == "2025-12-31"
    assert [f["id"] for f in status["factors"]][0] == "net_active_buy"

    response = client.post(f"{API}/backtest", headers=reader, json={
        "universe": "demo", "factor": "net_active_buy", "windows": [20, 22, 20], "top_n": 5, "start_date": "2024-06-28"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert [r["window"] for r in result["runs"]] == [20, 22]
    run = result["runs"][0]
    assert result["days"][0] == "2024-06-28" and len(run["nav"]) == len(result["days"]) == len(result["benchmark_nav"])
    first = run["rebalances"][0]
    assert first["signal_date"] == "2024-06-28" and first["trade_date"] == "2024-07-01" and len(first["holdings"]) == 5
    assert first["holdings"][0]["score"] >= first["holdings"][-1]["score"]
    assert run["metrics"]["rebalances"] > 70 and run["metrics"]["sharpe"] is not None
    assert result["average"]["annualized_return"] is not None and result["names"][first["holdings"][0]["code"]]
    assert {y["year"] for y in run["yearly"]} == {"2024", "2025"}

    too_many = client.post(f"{API}/backtest", headers=reader, json={"universe": "demo", "top_n": 41})
    assert too_many.status_code == 400
    assert client.post(f"{API}/backtest", headers=reader, json={"universe": "nothing"}).status_code == 400


def test_csv_import_accepts_chinese_headers_and_reports_missing_fields(client) -> None:
    headers = _admin(client)
    lines = ["日期,代码,名称,收盘价,成交额"]
    for week in range(8):
        for d in range(5):
            day = f"2025-{3 + (week * 7 + d) // 28:02d}-{3 + (week * 7 + d) % 28:02d}"
            for k, name in enumerate(("甲", "乙", "丙")):
                lines.append(f"{day.replace('-', '/')},S{k},{name},{100 + week * (k + 1) + d * 0.1:.2f},{1000 * (k + 1)}")
    upload = client.post(f"{API}/import-csv", headers=headers, data={"universe": "wind-test"},
                         files={"file": ("sectors.csv", "\n".join(lines).encode("gbk"), "text/csv")})
    assert upload.status_code == 200, upload.text
    assert upload.json()["imported"] == 120
    info = next(u for u in upload.json()["universes"] if u["universe"] == "wind-test")
    assert info["sectors"] == 3 and info["first_date"] == "2025-03-03" and not info["has_flow"]

    no_flow = client.post(f"{API}/backtest", headers=headers, json={"universe": "wind-test", "top_n": 1})
    assert no_flow.status_code == 400 and "主动买入额" in no_flow.json()["detail"]
    momentum = client.post(f"{API}/backtest", headers=headers, json={
        "universe": "wind-test", "factor": "momentum", "windows": [5], "top_n": 1})
    assert momentum.status_code == 200, momentum.text
    assert momentum.json()["runs"][0]["rebalances"][-1]["holdings"][0]["code"] == "S2"  # the fastest riser

    bad = client.post(f"{API}/import-csv", headers=headers, data={"universe": "wind-test"},
                      files={"file": ("bad.csv", b"date,code\n2025-01-02,S0\n", "text/csv")})
    assert bad.status_code == 400 and "close" in bad.json()["detail"]
    reserved = client.post(f"{API}/import-csv", headers=headers, data={"universe": "citic40"},
                           files={"file": ("x.csv", b"date,code,close\n2025-01-02,S0,1\n", "text/csv")})
    assert reserved.status_code == 400
    assert client.delete(f"{API}/wind-test", headers=headers).json()["deleted"] == 120


def test_token_is_saved_but_only_its_ends_are_shown(client) -> None:
    headers = _admin(client)
    body = client.put(f"{API}/credentials", headers=headers, json={"secret": "abcd1234567890wxyz"}).json()
    assert body["tushare_token_hint"] == "abcd…wxyz" and "1234567890" not in str(body)
    reader, _ = register(client, "reader")
    assert client.put(f"{API}/credentials", headers=reader, json={"secret": "abcd1234567890wxyz"}).status_code == 403


def test_tushare_sync_chains_sector_index_and_resumes_after_the_last_day() -> None:
    members = [{"l1_code": "CI005021.CI", "l1_name": "银行", "l2_code": "X", "l2_name": "国有大型银行Ⅱ", "ts_code": "601398.SH",
                "in_date": "20100101", "out_date": None, "is_new": "Y"}]
    asked: list[str] = []

    def post(body: dict) -> dict:
        api, params = body["api_name"], body["params"]
        if api == "ci_index_member":
            rows = members if params["is_new"] == "Y" else []
        elif api == "daily":
            asked.append(params["trade_date"])
            rows = [{"ts_code": "601398.SH", "pct_chg": 10.0, "amount": 1.0}]
        elif api == "daily_basic":
            rows = [{"ts_code": "601398.SH", "circ_mv": 1.0}]
        else:
            rows = []  # moneyflow not published
        fields = list(rows[0]) if rows else []
        return {"code": 0, "msg": "", "data": {"fields": fields, "items": [[r[f] for f in fields] for r in rows]}}

    seen = []
    with SessionLocal() as db:
        sectors.delete_universe(db, sectors.TUSHARE_UNIVERSE)
        kwargs = {"progress": lambda done, total, day: seen.append((done, total)), "cancelled": lambda: False,
                  "post": post, "pause": 0}
        assert sectors.sync_tushare(db, "t", "2026-01-05", "2026-01-06", **kwargs) == 2
        assert sectors.sync_tushare(db, "t", "2026-01-05", "2026-01-07", **kwargs) == 1  # only the new day
        rows = db.query(SectorDaily).filter_by(universe=sectors.TUSHARE_UNIVERSE).order_by(SectorDaily.trade_date).all()
        assert [round(r.close, 2) for r in rows] == [1100.0, 1210.0, 1331.0]
        assert rows[0].buy_amount is None and rows[0].name == "银行"
        sectors.delete_universe(db, sectors.TUSHARE_UNIVERSE)
    assert asked == ["20260105", "20260106", "20260107"] and seen[-1] == (1, 1)
