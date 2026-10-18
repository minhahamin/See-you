"""맞춤 일정 평가: 저장된 설정(취향·예산)이 일정에 실제로 반영되는지 측정한다.

페르소나마다 같은 날짜·일수·동행으로 두 번 실행한다.
- 대조군: 메시지에 동행만 말하고 설정은 없다 (취향·예산 모름)
- 실험군: 메시지에는 날짜·일수만 말하고, 동행·취향·예산은 저장된 설정(profile)으로 준다
날씨는 모두 맑음으로 고정한다. 지표는 확정된 일정의 장소 특성(place_traits.json)에서 계산해서 LLM 판정에 의존하지 않는다.
주의: 예산 초과는 validate_itinerary의 검증 항목이기도 해서, 두 조건 모두 재생성 루프가 어느 정도 걸러 준다.
"""
import argparse
import csv
import json
import logging
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from unittest.mock import patch

from langchain_core.messages import HumanMessage

from agent import catalog
from agent.graph import build_graph, make_checkpointer
from agent.state import Itinerary
from config import get_settings, setup_logging
from eval.run_itinerary_eval import START_OFFSET_DAYS, fixed_weather
from llm import is_daily_quota_error

logger = logging.getLogger(__name__)

# 취향 → 장소 텍스트(이름·소개·장점)에서 찾을 단어. 평가 전에 정해 두었다.
KEYWORDS: dict[str, tuple[str, ...]] = {
    "바다 전망": ("바다", "해변", "해안", "전망", "오션"),
    "조용한 곳": ("조용", "한적", "여유", "고요"),
    "자연 풍경": ("자연", "풍경", "숲", "오름", "경관"),
}
CATEGORY_PREFS = {"카페": "카페", "맛집": "음식점"}  # 취향 → 카테고리 일치
INDOOR_PREF = "실내 위주"


@dataclass(frozen=True)
class Persona:
    """평가 페르소나: 저장 설정과 요청 문구."""

    id: str
    days: int
    companion: str
    preferences: tuple[str, ...]
    budget: int


PERSONAS: list[Persona] = [
    Persona("family-indoor", 2, "가족", (INDOOR_PREF,), 2),
    Persona("couple-sea-cafe", 3, "커플", ("바다 전망", "카페"), 3),
    Persona("solo-quiet", 2, "혼자", ("조용한 곳",), 2),
    Persona("friends-food-nature", 3, "친구", ("맛집", "자연 풍경"), 2),
]
CONDITIONS = ("control", "personalized")


def visit_matches(place_id: str, prefs: tuple[str, ...]) -> bool:
    """방문 장소가 취향 중 하나라도 만족하는지 (취향이 없으면 False)."""
    place, trait = catalog.places()[place_id], catalog.traits()[place_id]
    text = " ".join([place.name, place.description or "", *trait.pros])
    for pref in prefs:
        if pref == INDOOR_PREF and trait.indoor:
            return True
        if pref in CATEGORY_PREFS and place.category == CATEGORY_PREFS[pref]:
            return True
        if any(k in text for k in KEYWORDS.get(pref, ())):
            return True
    return False


def itinerary_metrics(itinerary: Itinerary, persona: Persona) -> dict[str, Any]:
    """일정의 취향 일치율·실내 비율·예산 초과 비율·평균 가격대를 장소 특성으로 계산한다."""
    visits = [v for d in itinerary.days for v in d.visits]
    traits = catalog.traits()
    n = max(len(visits), 1)
    return {
        "n_visits": len(visits),
        "pref_hit_rate": sum(visit_matches(v.place_id, persona.preferences) for v in visits) / n,
        "indoor_rate": sum(traits[v.place_id].indoor for v in visits) / n,
        "over_budget_rate": sum(traits[v.place_id].price_level > persona.budget for v in visits) / n,
        "avg_price_level": sum(traits[v.place_id].price_level for v in visits) / n,
        "violations": len(itinerary.validation.issues) if hasattr(itinerary.validation, "issues") else None,
    }


def run_one(persona: Persona, condition: str, today: date) -> dict[str, Any]:
    """페르소나 하나를 한 조건으로 실행하고 확정 일정의 지표를 돌려준다."""
    start = today + timedelta(days=START_OFFSET_DAYS)
    when = f"{start.month}월 {start.day}일부터 제주 {persona.days}일 여행"
    personalized = condition == "personalized"
    message = when if personalized else f"{when}, {persona.companion}끼리 가요"
    profile = {"companion": persona.companion, "preferences": list(persona.preferences), "budget": persona.budget} if personalized else None
    graph = build_graph(make_checkpointer())
    cfg = {"configurable": {"thread_id": f"{persona.id}-{condition}"}}
    final: Itinerary | None = None
    issues: list[str] = []
    applied: dict = {}
    asked = False
    started = time.perf_counter()
    with patch("agent.nodes.check_weather.get_forecast", fixed_weather(("sunny",) * persona.days)):
        for update in graph.stream({"messages": [HumanMessage(message)], "profile": profile}, cfg, stream_mode="updates"):
            if "validate_itinerary" in update:
                final = update["validate_itinerary"]["itinerary"]
                issues = update["validate_itinerary"]["validation_issues"]
            elif "parse_request" in update:
                applied = update["parse_request"].get("applied_settings") or {}
            elif "__interrupt__" in update:
                asked = update["__interrupt__"][0].value["type"] == "question"
    if final is None or asked:
        return {"id": persona.id, "condition": condition, "error": "일정을 만들지 못했다 (되묻기 발생 또는 결과 없음)", "message": message}
    metrics = itinerary_metrics(final, persona)
    metrics["violations"] = len(issues)
    return {
        "id": persona.id,
        "condition": condition,
        "message": message,
        "applied_settings": applied,
        "response_sec": round(time.perf_counter() - started, 1),
        "model": get_settings().llm_model,
        **metrics,
    }


METRICS = ("pref_hit_rate", "indoor_rate", "over_budget_rate", "avg_price_level", "violations")


def summarize(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """조건별 평균과 페르소나 쌍(대조 vs 실험)별 차이를 집계한다. 두 조건이 모두 성공한 페르소나만 쓴다."""
    ok = {(r["id"], r["condition"]): r for r in records if "error" not in r}
    ids = [p.id for p in PERSONAS if (p.id, "control") in ok and (p.id, "personalized") in ok]
    rows: list[dict[str, Any]] = []
    for condition in CONDITIONS:
        rs = [ok[(i, condition)] for i in ids]
        rows.append({"condition": condition, "n": len(rs), **{m: (round(sum(r[m] for r in rs) / len(rs), 4) if rs else None) for m in METRICS}})
    if ids:
        wins = {m: sum(ok[(i, "personalized")][m] > ok[(i, "control")][m] for i in ids) for m in METRICS}
        rows.append({"condition": "personalized_higher_in_n_personas", "n": len(ids), **wins})
    return rows


def write_summary(rows: list[dict[str, Any]], model: str) -> None:
    """집계를 eval/results/personalization_summary.csv에 저장한다 (같은 날짜·모델의 이전 행은 교체)."""
    path = get_settings().eval_results_dir / "personalization_summary.csv"
    today = date.today().isoformat()
    fields = ["date", "model", "condition", "n", *METRICS]
    kept: list[dict[str, str]] = []
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as f:
            kept = [r for r in csv.DictReader(f) if not (r["date"] == today and r["model"] == model)]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows([*kept, *({"date": today, "model": model, **r} for r in rows)])


def main() -> None:
    """페르소나×조건을 실행하고 기록(jsonl)과 집계(csv)를 저장한다. 중단 후 다시 실행하면 이어서 한다."""
    setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--summarize-only", action="store_true")
    args = parser.parse_args()

    out_dir = get_settings().eval_results_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    runs_path = out_dir / f"personalization_runs_{date.today().isoformat()}.jsonl"
    records = [json.loads(line) for line in runs_path.read_text(encoding="utf-8").splitlines()] if runs_path.exists() else []
    done = {(r["id"], r["condition"]) for r in records if "error" not in r}

    if not args.summarize_only:
        for persona in PERSONAS:
            for condition in CONDITIONS:
                if (persona.id, condition) in done:
                    continue
                try:
                    record = run_one(persona, condition, date.today())
                except Exception as exc:  # noqa: BLE001 - 일일 한도만 중단 사유, 나머지는 기록하고 계속
                    if is_daily_quota_error(exc):
                        logger.error("일일 호출 한도 초과로 중단합니다. 다시 실행하면 이어서 합니다.")
                        break
                    record = {"id": persona.id, "condition": condition, "error": type(exc).__name__}
                records = [r for r in records if (r["id"], r["condition"]) != (persona.id, condition)] + [record]
                runs_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8")
                logger.info("%s/%s → %s", persona.id, condition, {k: record.get(k) for k in ("error", *METRICS, "applied_settings")})
            else:
                continue
            break

    rows = summarize(records)
    if rows and rows[0]["n"]:
        write_summary(rows, get_settings().llm_model)
        for r in rows:
            logger.info("%s", r)


if __name__ == "__main__":
    main()
