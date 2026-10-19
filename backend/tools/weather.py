"""기상청 단기예보(VilageFcstInfoService_2.0, getVilageFcst) 조회로 일자별 날씨를 만든다.

명세 출처: 기상청 '단기예보 조회서비스 오픈API 활용가이드'(2026-09-28 판).
- 발표시각(base_time): 0200, 0500, 0800, 1100, 1400, 1700, 2000, 2300 (제공은 발표 10분 후부터)
- 예보 범위: 02~14시 발표는 +4일(글피), 17·20·23시 발표는 +5일(그글피)까지. 그 밖의 날짜는 조회할 수 없다.
- 격자 좌표(nx, ny)는 가이드 첨부 엑셀(격자_위경도 2607)의 '제주특별자치도 제주시'(5011000000) 행 (53, 38)과
  '제주특별자치도 서귀포시'(5013000000) 행 (53, 33)을 쓴다. 읍면동마다 격자가 다르지만(예: 성산읍 60,37) 구역 단위로 근사한다.

호스트 주의: 가이드의 서비스 URL(apihub.kma.go.kr)은 기상청 API허브 전용 인증키(authKey)를 요구하고,
공공데이터포털에서 받은 키는 거기서 401이 난다. 같은 서비스의 공공데이터포털 주소(apis.data.go.kr)에서는
serviceKey로 정상 동작함을 2026-10-18에 직접 호출해 확인했다. 가이드에 없는 주소이므로 바뀌면 여기를 고친다.
"""
import logging
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Any
from urllib.parse import unquote

import httpx

from agent.state import Weather
from config import get_settings

logger = logging.getLogger(__name__)

BASE_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
KST = timezone(timedelta(hours=9))
BASE_HOURS = (2, 5, 8, 11, 14, 17, 20, 23)
PROVIDE_DELAY_MIN = 10  # 발표시각 + 10분부터 조회 가능
HORIZON_DAYS = 5  # 이 이상 먼 날짜는 호출하지 않는다 (가이드의 최대 예보 범위)
ROWS_PER_PAGE = 1000
HTTP_TIMEOUT_SEC = 20

# 지역 → 격자 (nx, ny). "제주"는 구역을 지정하지 않았을 때의 기본값(제주시)이다.
REGION_GRIDS: dict[str, tuple[int, int]] = {"제주": (53, 38), "제주시": (53, 38), "서귀포시": (53, 33)}

MIN_TMP_READINGS = 4  # 일 최고/최저기온이 없을 때, 시간별 기온이 이만큼은 있어야 하루치로 인정한다
DAYTIME_HOURS = range(9, 22)  # 낮 시간대(09~21시)의 하늘상태·강수로 하루 날씨를 정한다
SKY_SUNNY = "1"  # 하늘상태 코드: 맑음(1), 구름많음(3), 흐림(4)
NO_PRECIPITATION = "0"  # 강수형태 코드: 없음(0), 비(1), 비/눈(2), 눈(3), 소나기(4)


class WeatherUnavailable(RuntimeError):
    """날씨를 가져올 수 없을 때 (키 없음, 예보 범위 밖, 호출 실패 등)."""


def latest_base(now_kst: datetime) -> tuple[str, str]:
    """지금 조회할 수 있는 가장 최근 발표의 (base_date, base_time)."""
    available = now_kst - timedelta(minutes=PROVIDE_DELAY_MIN)
    hours = [h for h in BASE_HOURS if h <= available.hour]
    if hours:
        return available.strftime("%Y%m%d"), f"{hours[-1]:02d}00"
    return (available - timedelta(days=1)).strftime("%Y%m%d"), "2300"


@lru_cache(maxsize=8)
def _fetch_items(base_date: str, base_time: str, nx: int, ny: int) -> tuple[dict[str, Any], ...]:
    """단기예보 항목을 모두 가져온다. 같은 발표분은 프로세스 안에서 재사용한다."""
    key = get_settings().kma_api_key
    if not key:
        raise WeatherUnavailable("KMA_API_KEY가 비어 있습니다")
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        params = {
            "serviceKey": unquote(key),  # 인코딩된 키가 들어와도 이중 인코딩되지 않게 한다
            "numOfRows": ROWS_PER_PAGE,
            "pageNo": page,
            "dataType": "JSON",
            "base_date": base_date,
            "base_time": base_time,
            "nx": nx,
            "ny": ny,
        }
        try:
            resp = httpx.get(BASE_URL, params=params, timeout=HTTP_TIMEOUT_SEC)
            resp.raise_for_status()
            body = resp.json()["response"]
        except Exception as exc:  # 예외 문자열에 URL(키 포함)이 들어갈 수 있어 타입만 남긴다
            raise WeatherUnavailable(f"기상청 호출 실패: {type(exc).__name__}") from None
        if body["header"]["resultCode"] != "00":
            raise WeatherUnavailable(f"기상청 오류 응답: {body['header']['resultCode']} {body['header']['resultMsg']}")
        chunk = body["body"].get("items", {}).get("item", [])
        items.extend(chunk)
        if page * ROWS_PER_PAGE >= int(body["body"]["totalCount"]) or not chunk:
            return tuple(items)
        page += 1


def _daily(items: list[dict[str, Any]], fcst_date: str) -> Weather | None:
    """하루치 항목으로 Weather를 만든다. 하루치로 볼 기온 근거가 부족하면 None (임의 값을 넣지 않는다)."""
    day = [i for i in items if i["fcstDate"] == fcst_date]
    by_cat: dict[str, list[dict[str, Any]]] = {}
    for i in day:
        by_cat.setdefault(i["category"], []).append(i)

    def values(cat: str) -> list[float]:
        return [float(i["fcstValue"]) for i in by_cat.get(cat, [])]

    # 일 최고/최저기온(TMX/TMN)이 있으면 쓰고, 없으면(3시간 간격 구간) 시간별 기온(TMP)의 최대/최소를 쓴다
    temp_max = max(values("TMX"), default=None) if by_cat.get("TMX") else None
    temp_min = min(values("TMN"), default=None) if by_cat.get("TMN") else None
    tmp = values("TMP")
    if len(tmp) >= MIN_TMP_READINGS:  # 예보 마지막 날은 일부 시각만 있을 수 있어, 충분할 때만 쓴다
        temp_max = max(tmp) if temp_max is None else temp_max
        temp_min = min(tmp) if temp_min is None else temp_min
    if temp_max is None or temp_min is None:
        return None

    def daytime(cat: str) -> list[str]:
        rows = by_cat.get(cat, [])
        picked = [i for i in rows if int(i["fcstTime"][:2]) in DAYTIME_HOURS]
        return [i["fcstValue"] for i in (picked or rows)]

    if any(v != NO_PRECIPITATION for v in daytime("PTY")):
        condition = "rain"  # 비·비/눈·눈·소나기 모두 '강수 있는 날'로 묶는다
    else:
        sky = Counter(daytime("SKY")).most_common(1)
        condition = "sunny" if sky and sky[0][0] == SKY_SUNNY else "cloudy"
    return Weather(condition=condition, temp_max=temp_max, temp_min=temp_min)


def summarize_daily(items: list[dict[str, Any]], dates: list[str]) -> dict[str, Weather]:
    """요청한 날짜(YYYY-MM-DD)별 Weather. 예보에 없는 날짜는 빠진다."""
    result: dict[str, Weather] = {}
    for d in dates:
        weather = _daily(items, d.replace("-", ""))
        if weather:
            result[d] = weather
    return result


def get_forecast(dates: list[str], region: str, now: datetime | None = None) -> dict[str, Weather]:
    """날짜(YYYY-MM-DD)별 날씨를 반환한다. 예보 범위 밖 날짜는 결과에서 빠지고, 하나도 없으면 WeatherUnavailable."""
    if region not in REGION_GRIDS:
        raise WeatherUnavailable(f"격자 좌표가 없는 지역입니다: {region}")
    now_kst = (now or datetime.now(KST)).astimezone(KST)
    horizon = now_kst.date() + timedelta(days=HORIZON_DAYS)
    in_range = [d for d in dates if date.fromisoformat(d) <= horizon]
    if not in_range:
        raise WeatherUnavailable(f"예보 범위 밖입니다 (발표일 기준 최대 +{HORIZON_DAYS}일)")
    base_date, base_time = latest_base(now_kst)
    nx, ny = REGION_GRIDS[region]
    forecast = summarize_daily(list(_fetch_items(base_date, base_time, nx, ny)), in_range)
    if not forecast:
        raise WeatherUnavailable("요청한 날짜의 예보가 없습니다")
    logger.info("날씨 조회 완료: %d일 (발표 %s %s)", len(forecast), base_date, base_time)
    return forecast
