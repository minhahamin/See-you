"""tools/weather.py 단위 테스트. 기상청 호출은 모두 가짜로 대체한다."""
from datetime import datetime
from types import SimpleNamespace

import pytest

from agent.nodes.check_weather import check_weather
from agent.state import TripRequest
from tools import weather as W

REAL_FETCH = W._fetch_items.__wrapped__  # conftest가 막기 전의 원본(캐시 제외)
KST = W.KST
SECRET = "abc%2Bdef%3D%3D"


def item(date: str, time: str, category: str, value: str) -> dict:
    """예보 항목 한 건."""
    return {"baseDate": "20261018", "baseTime": "2300", "category": category, "fcstDate": date, "fcstTime": time, "fcstValue": value, "nx": 53, "ny": 38}


SAMPLE = [
    # 10/19: 맑음, 일 최고/최저 기온 있음
    item("20261019", "0600", "TMN", "18.0"), item("20261019", "1500", "TMX", "23.0"),
    *[item("20261019", t, "PTY", "0") for t in ("0900", "1200", "1500")],
    *[item("20261019", t, "SKY", "1") for t in ("0900", "1200", "1500")],
    # 10/20: 낮에 비
    item("20261020", "0600", "TMN", "17.0"), item("20261020", "1500", "TMX", "21.0"),
    item("20261020", "0900", "PTY", "0"), item("20261020", "1200", "PTY", "1"),
    item("20261020", "1200", "SKY", "4"),
    # 10/23: 3시간 간격(TMX/TMN 없음) → TMP로 대체, 흐림
    item("20261023", "0000", "TMP", "11.0"), item("20261023", "0600", "TMP", "9.0"),
    item("20261023", "1200", "TMP", "14.0"), item("20261023", "1500", "TMP", "15.0"),
    *[item("20261023", t, "SKY", "4") for t in ("0900", "1200", "1500")],
    *[item("20261023", t, "PTY", "0") for t in ("0900", "1200", "1500")],
    # 10/21: 기온 값이 전혀 없음 → 날씨를 만들지 않는다
    item("20261021", "1200", "SKY", "1"),
    # 10/24: 예보 마지막 날이라 00시 한 시각만 있음 → 하루치로 보지 않는다
    item("20261024", "0000", "TMP", "16.0"), item("20261024", "0000", "SKY", "1"), item("20261024", "0000", "PTY", "0"),
]


def test_latest_base_picks_available_release() -> None:
    """발표 10분 후부터 조회 가능하고, 새벽 2시 10분 전에는 전날 23시 발표를 쓴다."""
    assert W.latest_base(datetime(2026, 10, 18, 23, 24, tzinfo=KST)) == ("20261018", "2300")
    assert W.latest_base(datetime(2026, 10, 18, 11, 5, tzinfo=KST)) == ("20261018", "0800")
    assert W.latest_base(datetime(2026, 10, 18, 11, 10, tzinfo=KST)) == ("20261018", "1100")
    assert W.latest_base(datetime(2026, 10, 18, 1, 30, tzinfo=KST)) == ("20261017", "2300")


def test_summarize_daily_conditions_and_temperatures() -> None:
    """맑음·비·흐림 판정과 기온 산출(TMX/TMN 우선, 없으면 TMP)."""
    out = W.summarize_daily(SAMPLE, ["2026-10-19", "2026-10-20", "2026-10-21", "2026-10-23", "2026-10-22", "2026-10-24"])
    assert (out["2026-10-19"].condition, out["2026-10-19"].temp_max, out["2026-10-19"].temp_min) == ("sunny", 23.0, 18.0)
    assert out["2026-10-20"].condition == "rain"  # 낮에 강수형태 != 0
    assert (out["2026-10-23"].condition, out["2026-10-23"].temp_max, out["2026-10-23"].temp_min) == ("cloudy", 15.0, 9.0)
    assert "2026-10-21" not in out and "2026-10-22" not in out  # 값이 없으면 만들지 않는다
    assert "2026-10-24" not in out  # 한 시각뿐인 날은 최고=최저처럼 잘못된 값이 되므로 제외


def test_get_forecast_skips_call_outside_horizon(monkeypatch: pytest.MonkeyPatch) -> None:
    """예보 범위(발표일 +5일) 밖이면 API를 호출하지 않고 WeatherUnavailable."""
    called = []
    monkeypatch.setattr(W, "_fetch_items", lambda *a: called.append(a) or ())
    now = datetime(2026, 10, 18, 23, 24, tzinfo=KST)
    with pytest.raises(W.WeatherUnavailable, match="범위 밖"):
        W.get_forecast(["2026-11-14", "2026-11-15"], "제주", now=now)
    assert called == []


def test_get_forecast_returns_only_dates_with_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """범위 안 날짜 중 예보가 있는 날만 돌려주고, 요청에 쓴 발표분·격자는 제주시 기준이다."""
    seen = {}
    monkeypatch.setattr(W, "_fetch_items", lambda *a: seen.setdefault("args", a) and tuple(SAMPLE))
    now = datetime(2026, 10, 18, 23, 24, tzinfo=KST)
    out = W.get_forecast(["2026-10-19", "2026-10-20", "2026-11-14"], "제주", now=now)
    assert set(out) == {"2026-10-19", "2026-10-20"}
    assert seen["args"] == ("20261018", "2300", 53, 38)


def test_get_forecast_unknown_region_and_empty_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """격자가 없는 지역이나 빈 결과는 WeatherUnavailable."""
    now = datetime(2026, 10, 18, 23, 24, tzinfo=KST)
    with pytest.raises(W.WeatherUnavailable, match="지역"):
        W.get_forecast(["2026-10-19"], "부산", now=now)
    monkeypatch.setattr(W, "_fetch_items", lambda *a: ())
    with pytest.raises(W.WeatherUnavailable, match="예보가 없습니다"):
        W.get_forecast(["2026-10-19"], "제주", now=now)


def _response(payload: dict | None = None, *, status: int = 200, text: str = "") -> SimpleNamespace:
    """httpx 응답 대역."""

    def raise_for_status() -> None:
        if status >= 400:
            raise RuntimeError(f"HTTP {status} for url key={SECRET}")

    def json() -> dict:
        if payload is None:
            raise ValueError(f"not json {text}")
        return payload

    return SimpleNamespace(raise_for_status=raise_for_status, json=json)


def _settings(monkeypatch: pytest.MonkeyPatch, key: str) -> None:
    monkeypatch.setattr("tools.weather.get_settings", lambda: SimpleNamespace(kma_api_key=key))


def test_fetch_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """키가 비어 있으면 호출 없이 실패한다."""
    _settings(monkeypatch, "")
    with pytest.raises(W.WeatherUnavailable, match="KMA_API_KEY"):
        REAL_FETCH("20261018", "2300", 53, 38)


def test_fetch_decodes_key_and_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    """인코딩된 키는 한 번 디코딩해서 보내고, totalCount만큼 페이지를 이어서 가져온다."""
    _settings(monkeypatch, SECRET)
    sent = []

    def fake_get(url: str, params: dict, timeout: int) -> SimpleNamespace:
        sent.append(params)
        page = params["pageNo"]
        rows = [SAMPLE[0]] if page == 1 else [SAMPLE[1]]
        return _response({"response": {"header": {"resultCode": "00", "resultMsg": "OK"}, "body": {"items": {"item": rows}, "totalCount": 2}}})

    monkeypatch.setattr(W, "ROWS_PER_PAGE", 1)
    monkeypatch.setattr("tools.weather.httpx.get", fake_get)
    items = REAL_FETCH("20261018", "2300", 53, 38)
    assert len(items) == 2 and [p["pageNo"] for p in sent] == [1, 2]
    assert sent[0]["serviceKey"] == "abc+def==" and sent[0]["base_time"] == "2300"


@pytest.mark.parametrize(
    "response",
    [
        _response({"response": {"header": {"resultCode": "03", "resultMsg": "NO_DATA"}, "body": {}}}),
        _response(None, text="<OpenAPI_ServiceResponse>SERVICE_KEY_IS_NOT_REGISTERED</OpenAPI_ServiceResponse>"),
        _response(status=500),
    ],
)
def test_fetch_failures_do_not_leak_key(monkeypatch: pytest.MonkeyPatch, response: SimpleNamespace) -> None:
    """오류 응답·비JSON·HTTP 오류는 모두 WeatherUnavailable이고, 메시지에 키가 들어가지 않는다."""
    _settings(monkeypatch, SECRET)
    monkeypatch.setattr("tools.weather.httpx.get", lambda *a, **k: response)
    with pytest.raises(W.WeatherUnavailable) as exc:
        REAL_FETCH("20261018", "2300", 53, 38)
    assert SECRET not in str(exc.value) and "def" not in str(exc.value)


def test_check_weather_node_uses_forecast_and_degrades(monkeypatch: pytest.MonkeyPatch) -> None:
    """노드는 예보가 있으면 담고, 범위 밖이면 빈 dict로 진행한다."""
    far = check_weather({"request": TripRequest(start_date="2099-11-14", days=2)})
    assert far == {"weather": {}, "area_weather": {}}
    monkeypatch.setattr("agent.nodes.check_weather.get_forecast", lambda dates, region: W.summarize_daily(SAMPLE, dates))
    near = check_weather({"request": TripRequest(start_date="2026-10-19", days=2)})
    assert near["weather"]["2026-10-20"].condition == "rain"
