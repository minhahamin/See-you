"""일정 단위 평가: validate 재생성 루프의 효과(v5)를 측정한다.

시나리오마다 그래프를 한 번 실행하며 검증이 돌 때마다 결과를 기록한다.
- 루프 없음(v4 구성에 해당) = 처음 생성한 일정(pass 0)의 검증 결과
- 루프 적용(v5)             = 재생성을 마친 최종 일정의 검증 결과
같은 입력·같은 실행에서 비교하므로 LLM 호출을 아끼고 조건이 같다.

날씨는 실제 예보 대신 시나리오별로 고정한다 (예보는 날마다 달라 재현이 안 되고, 비 오는 날 경로를 확인하기 위함).
조건 위반 = validate_itinerary의 검증 항목 중 실패한 것. Faithfulness는 eval/faithfulness.py(자체 LLM 판정).
"""
import argparse
import csv
import json
import logging
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable
from unittest.mock import patch

from langchain_core.messages import HumanMessage

from agent import catalog
from agent.graph import build_graph, make_checkpointer
from agent.state import Itinerary, Weather
from api.metrics import RunRecorder
from config import get_settings, setup_logging
from eval.faithfulness import judge_itinerary
from llm import is_daily_quota_error
from tools.route import haversine_km

logger = logging.getLogger(__name__)

START_OFFSET_DAYS = 45  # 예보 범위 밖의 날짜를 쓰고, 날씨는 아래에서 고정해 주입한다
TEMPS = (20.0, 12.0)


@dataclass(frozen=True)
class Scenario:
    """평가 시나리오: 사용자 요청과 일차별 고정 날씨."""

    id: str
    text: str  # {date}에 시작일이 들어간다
    weather: tuple[str, ...]


SCENARIOS: list[Scenario] = [
    Scenario("couple-3d-sea", "{date}부터 커플끼리 제주 3일 여행, 바다가 보이는 곳 위주로", ("sunny", "sunny", "cloudy")),
    Scenario("family-2d-indoor", "{date}부터 가족이랑 제주 2일, 아이가 있어서 실내 장소가 많았으면 좋겠어", ("rain", "cloudy")),
    Scenario("friends-3d-food", "{date}부터 친구랑 제주 3일, 맛집이랑 카페 위주로", ("sunny", "rain", "sunny")),
    Scenario("solo-2d-quiet", "{date}부터 혼자 제주 2일, 조용하고 한적한 곳 위주로", ("cloudy", "sunny")),
    Scenario("couple-2d-rain", "{date}부터 커플끼리 제주 2일", ("rain", "rain")),
    Scenario("family-3d-budget", "{date}부터 가족이랑 제주 3일, 최대한 저렴하게", ("sunny", "cloudy", "rain")),
    Scenario("friends-2d-nature", "{date}부터 친구랑 제주 2일, 자연 풍경 위주로", ("sunny", "sunny")),
    Scenario("couple-3d-luxury", "{date}부터 커플끼리 제주 3일, 여유롭고 고급스럽게", ("cloudy", "rain", "sunny")),
    Scenario("solo-3d-art", "{date}부터 혼자 제주 3일, 미술관이나 박물관을 좋아해", ("sunny", "rain", "cloudy")),
    Scenario("family-2d-mixed", "{date}부터 가족이랑 제주 2일", ("sunny", "rain")),
]


def fixed_weather(conditions: tuple[str, ...]) -> Callable[[list[str], str], dict[str, Weather]]:
    """일차 순서대로 고정 날씨를 돌려주는 get_forecast 대역."""

    def forecast(dates: list[str], region: str) -> dict[str, Weather]:
        return {
            d: Weather(condition=conditions[i], temp_max=TEMPS[0], temp_min=TEMPS[1])  # type: ignore[arg-type]
            for i, d in enumerate(dates)
            if i < len(conditions)
        }

    return forecast


def pass_metrics(itinerary: Itinerary, issues: list[str]) -> dict[str, Any]:
    """검증 한 번의 결과와 일정 지표(하루 평균 이동시간·거리, 방문 수)를 요약한다."""
    places = catalog.places()
    km_per_day: list[float] = []
    for day in itinerary.days:
        coords = [(places[v.place_id].lat, places[v.place_id].lng) for v in day.visits]
        km_per_day.append(sum(haversine_km(*a, *b) for a, b in zip(coords, coords[1:])))
    n_days = max(len(itinerary.days), 1)
    return {
        "issues": issues,
        "passed": itinerary.validation.passed,
        "total": itinerary.validation.total,
        "avg_travel_min": sum(v.travel_minutes_from_prev for d in itinerary.days for v in d.visits) / n_days,
        "avg_travel_km": sum(km_per_day) / n_days,
        "n_visits": sum(len(d.visits) for d in itinerary.days),
    }


def run_scenario(scenario: Scenario, today: date) -> dict[str, Any]:
    """시나리오 하나를 실행하고 검증 pass별 지표와 Faithfulness를 기록한다."""
    start = today + timedelta(days=START_OFFSET_DAYS)
    message = scenario.text.format(date=f"{start.month}월 {start.day}일")
    graph = build_graph(make_checkpointer())
    recorder = RunRecorder()
    cfg = {"configurable": {"thread_id": scenario.id}, "callbacks": [recorder]}

    passes: list[dict[str, Any]] = []
    itineraries: list[Itinerary] = []
    asked = False
    started = time.perf_counter()
    with patch("agent.nodes.check_weather.get_forecast", fixed_weather(scenario.weather)):
        for update in graph.stream({"messages": [HumanMessage(message)]}, cfg, stream_mode="updates"):
            if "validate_itinerary" in update:
                u = update["validate_itinerary"]
                itineraries.append(u["itinerary"])
                passes.append(pass_metrics(u["itinerary"], u["validation_issues"]))
            elif "__interrupt__" in update:
                asked = update["__interrupt__"][0].value["type"] == "question"
    elapsed = time.perf_counter() - started
    if asked or not passes:
        return {"id": scenario.id, "message": message, "error": "일정을 만들지 못했다 (되묻기 발생 또는 결과 없음)"}

    # Faithfulness는 첫 생성과 최종 일정만 판정한다 (둘이 같으면 한 번만)
    first_score, _ = judge_itinerary(itineraries[0])
    final_score = first_score if len(itineraries) == 1 else judge_itinerary(itineraries[-1])[0]
    passes[0]["faithfulness"] = first_score
    passes[-1]["faithfulness"] = final_score
    return {
        "id": scenario.id,
        "message": message,
        "weather": list(scenario.weather),
        "regen_count": len(passes) - 1,
        "passes": passes,
        "response_sec": round(elapsed, 1),
        "tokens": sum(recorder.tokens_in.values()) + sum(recorder.tokens_out.values()),
        "model": get_settings().llm_model,
    }


def _mean(values: list[float]) -> float | None:
    """빈 목록이면 None."""
    return sum(values) / len(values) if values else None


def summarize(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """'no_loop'(첫 생성)과 'loop'(최종)의 지표를 집계한다. 오류 기록은 제외한다.

    응답시간·토큰은 루프를 돌린 실행 전체의 값이라 'loop'에만 넣는다 (루프 없이 실행했을 때의 비용은 측정하지 않았다).
    n_improved/n_same/n_worse는 시나리오별로 위반 건수가 첫 생성 대비 줄었는지·같은지·늘었는지 센다.
    """
    ok = [r for r in records if "passes" in r]
    first_counts = [len(r["passes"][0]["issues"]) for r in ok]
    last_counts = [len(r["passes"][-1]["issues"]) for r in ok]
    out: dict[str, dict[str, Any]] = {}
    for config, pick in (("no_loop", lambda r: r["passes"][0]), ("loop", lambda r: r["passes"][-1])):
        ps = [pick(r) for r in ok]
        total_checks = sum(p["total"] for p in ps)
        is_loop = config == "loop"
        out[config] = {
            "n": len(ps),
            "violation_itinerary_rate": _mean([float(len(p["issues"]) > 0) for p in ps]),
            "violation_check_rate": (sum(len(p["issues"]) for p in ps) / total_checks) if total_checks else None,
            "avg_violations": _mean([float(len(p["issues"])) for p in ps]),
            "faithfulness": _mean([p["faithfulness"] for p in ps if p.get("faithfulness") is not None]),
            "avg_travel_min": _mean([p["avg_travel_min"] for p in ps]),
            "avg_travel_km": _mean([p["avg_travel_km"] for p in ps]),
            "avg_regen": _mean([float(r["regen_count"]) for r in ok]) if is_loop else 0.0,
            "avg_response_sec": _mean([r["response_sec"] for r in ok]) if is_loop else None,
            "avg_tokens": _mean([float(r["tokens"]) for r in ok]) if is_loop else None,
            "n_improved": sum(b < a for a, b in zip(first_counts, last_counts)) if is_loop else None,
            "n_same": sum(b == a for a, b in zip(first_counts, last_counts)) if is_loop else None,
            "n_worse": sum(b > a for a, b in zip(first_counts, last_counts)) if is_loop else None,
        }
    return out


SUMMARY_FIELDS = [
    "date", "config", "model", "n", "violation_itinerary_rate", "violation_check_rate", "avg_violations",
    "faithfulness", "avg_travel_min", "avg_travel_km", "avg_regen", "avg_response_sec", "avg_tokens",
    "n_improved", "n_same", "n_worse",
]


def write_summary(summary: dict[str, dict[str, Any]], model: str) -> None:
    """집계를 eval/results/itinerary_summary.csv에 저장한다. 같은 날짜·모델의 이전 행은 새 값으로 바꾼다."""
    path = get_settings().eval_results_dir / "itinerary_summary.csv"
    today = date.today().isoformat()
    kept: list[dict[str, str]] = []
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as f:
            kept = [row for row in csv.DictReader(f) if not (row["date"] == today and row["model"] == model)]
    new_rows = [
        {"date": today, "config": config, "model": model, **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in row.items()}}
        for config, row in summary.items()
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows([*kept, *new_rows])


def main() -> None:
    """시나리오를 실행하고 기록(jsonl)과 집계(csv)를 저장한다. 중단 후 다시 실행하면 이어서 한다."""
    setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="앞에서 N개 시나리오만")
    parser.add_argument("--summarize-only", action="store_true", help="실행 없이 기존 기록으로 집계만")
    args = parser.parse_args()

    out_dir = get_settings().eval_results_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    runs_path = out_dir / f"itinerary_runs_{date.today().isoformat()}.jsonl"
    records = [json.loads(line) for line in runs_path.read_text(encoding="utf-8").splitlines()] if runs_path.exists() else []
    done = {r["id"] for r in records if "passes" in r}

    if not args.summarize_only:
        for scenario in SCENARIOS[: args.limit]:
            if scenario.id in done:
                continue
            try:
                record = run_scenario(scenario, date.today())
            except Exception as exc:  # noqa: BLE001 - 한 시나리오 실패가 전체를 멈추지 않게 하되 일일 한도는 중단한다
                if is_daily_quota_error(exc):
                    logger.error("일일 호출 한도 초과로 중단합니다. 다시 실행하면 이어서 합니다.")
                    break
                record = {"id": scenario.id, "error": type(exc).__name__}
            records = [r for r in records if r["id"] != scenario.id] + [record]
            runs_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8")
            if "passes" in record:
                first, last = record["passes"][0], record["passes"][-1]
                logger.info("%s | 재생성 %d회 | 위반 %d → %d | Faithfulness %s → %s | %.0fs", scenario.id, record["regen_count"], len(first["issues"]), len(last["issues"]), first.get("faithfulness"), last.get("faithfulness"), record["response_sec"])
            else:
                logger.warning("%s 실패: %s", scenario.id, record.get("error"))

    summary = summarize(records)
    if summary["no_loop"]["n"]:
        write_summary(summary, get_settings().llm_model)
        for config, row in summary.items():
            logger.info("%s: %s", config, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in row.items()})


if __name__ == "__main__":
    main()
