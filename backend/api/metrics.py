"""실행 지표 수집(노드별 지연·토큰)과 집계, 평가 결과 CSV 로딩."""
import csv
import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler

from api.schemas import (
    ExperimentResult,
    FailureReason,
    NodeMetric,
    RecentRun,
    RunMetrics,
)
from config import get_settings

logger = logging.getLogger(__name__)

NODE_ORDER = [
    "parse_request",
    "ask_clarification",
    "search_places",
    "analyze_reviews",
    "check_weather",
    "build_itinerary",
    "validate_itinerary",
    "present_itinerary",
    "apply_feedback",
]
RECENT_RUNS = 10
TOP_FAILURES = 3

# 검증 문제 문장 → 실패 사유 (validate_itinerary의 메시지 표현에 대응)
ISSUE_KINDS = [
    ("이동이 과합니다", "이동 과다"),
    ("영업시간", "영업시간 충돌"),
    ("예산", "예산 초과"),
    ("동행 조건", "동행 조건 불일치"),
    ("근거", "근거 없는 추천"),
    ("식사", "식사 누락"),
    ("반복", "장소 중복"),
    ("최소", "방문 수 부족"),
    ("비 예보", "우천 시 야외 일정"),
    ("08:00~22:00", "시간대 이탈"),
    ("일치", "일수 불일치"),
]
EXPERIMENT_DESCRIPTIONS = {
    "v1": "벡터 검색",
    "v2": "+ 메타데이터 필터",
    "v3": "+ 하이브리드",
    "v4": "+ 리랭커",
    "v5": "+ validate 루프",
}


def classify_issue(message: str) -> str:
    """검증 문제 문장을 실패 사유 라벨로 분류한다."""
    for needle, kind in ISSUE_KINDS:
        if needle in message:
            return kind
    return "기타"


class RunRecorder(BaseCallbackHandler):
    """LLM 호출의 토큰 사용량을 호출이 속한 LangGraph 노드별로 모은다."""

    def __init__(self) -> None:
        """노드별 누적 토큰 저장소를 만든다."""
        self._run_node: dict[UUID, str | None] = {}
        self.tokens_in: Counter[str] = Counter()
        self.tokens_out: Counter[str] = Counter()
        self._lock = Lock()

    def on_chat_model_start(self, serialized: Any, messages: Any, *, run_id: UUID, metadata: dict | None = None, **kwargs: Any) -> None:
        """호출이 어느 노드에서 시작됐는지 기록한다."""
        self._run_node[run_id] = (metadata or {}).get("langgraph_node")

    def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs: Any) -> None:
        """응답의 usage_metadata에서 입력·출력 토큰을 노드에 더한다."""
        node = self._run_node.pop(run_id, None) or "unknown"
        usage: dict = {}
        try:
            usage = response.generations[0][0].message.usage_metadata or {}
        except (AttributeError, IndexError):
            pass
        with self._lock:
            self.tokens_in[node] += int(usage.get("input_tokens", 0))
            self.tokens_out[node] += int(usage.get("output_tokens", 0))

    def node_tokens(self, node: str) -> int:
        """노드가 지금까지 쓴 토큰(입력+출력) 합계."""
        return self.tokens_in[node] + self.tokens_out[node]


def _price(value: str) -> float | None:
    """단가 설정 문자열을 숫자로. 비어 있거나 잘못되면 None."""
    try:
        return float(value) if value.strip() else None
    except ValueError:
        return None


def run_cost_usd(tokens_in: int, tokens_out: int) -> float | None:
    """설정된 단가로 비용을 계산한다. 단가가 없으면 None (임의 값을 넣지 않는다)."""
    s = get_settings()
    price_in, price_out = _price(s.llm_price_in_per_1m), _price(s.llm_price_out_per_1m)
    if price_in is None or price_out is None:
        return None
    return round((tokens_in * price_in + tokens_out * price_out) / 1_000_000, 6)


def new_record(session_id: str, run_id: str) -> dict[str, Any]:
    """빈 실행 기록을 만든다."""
    return {
        "run_id": run_id,
        "session_id": session_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "model": get_settings().llm_model,
        "response_sec": None,
        "nodes": {},  # node → {"calls", "latency_ms", "tokens_in", "tokens_out"}
        "build_count": 0,
        "issue_kinds": [],
        "cost_usd": None,
        "error": False,
    }


def add_node_call(record: dict[str, Any], node: str, latency_ms: float, tokens_in: int, tokens_out: int) -> None:
    """노드 실행 한 번을 기록에 더한다."""
    n = record["nodes"].setdefault(node, {"calls": 0, "latency_ms": 0.0, "tokens_in": 0, "tokens_out": 0})
    n["calls"] += 1
    n["latency_ms"] += latency_ms
    n["tokens_in"] += tokens_in
    n["tokens_out"] += tokens_out
    if node == "build_itinerary":
        record["build_count"] += 1


class MetricsStore:
    """실행 기록을 메모리와 JSONL 파일에 보관하고 집계한다."""

    def __init__(self, path: Path | None = None) -> None:
        """기존 기록 파일이 있으면 읽어 온다. path가 None이면 파일에 쓰지 않는다."""
        self._path = path
        self._records: list[dict[str, Any]] = []
        self._lock = Lock()
        if path and path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self._records.append(json.loads(line))

    def add(self, record: dict[str, Any]) -> None:
        """실행 기록을 저장한다."""
        with self._lock:
            self._records.append(record)
            if self._path:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _ok(self) -> list[dict[str, Any]]:
        """오류 없이 끝난 실행."""
        return [r for r in self._records if not r["error"] and r["response_sec"] is not None]

    def node_metrics(self) -> list[NodeMetric]:
        """노드별 평균 지연(ms)과 평균 토큰. 실행 기록이 없으면 빈 목록."""
        totals: dict[str, dict[str, float]] = {}
        for r in self._ok():
            for node, n in r["nodes"].items():
                t = totals.setdefault(node, {"calls": 0, "latency_ms": 0.0, "tokens": 0})
                t["calls"] += n["calls"]
                t["latency_ms"] += n["latency_ms"]
                t["tokens"] += n["tokens_in"] + n["tokens_out"]
        ordered = sorted(totals, key=lambda n: NODE_ORDER.index(n) if n in NODE_ORDER else len(NODE_ORDER))
        return [
            NodeMetric(
                node=n,
                avg_latency_ms=round(totals[n]["latency_ms"] / totals[n]["calls"], 1),
                avg_tokens=round(totals[n]["tokens"] / totals[n]["calls"], 1) if totals[n]["tokens"] else None,
            )
            for n in ordered
        ]

    def run_metrics(self) -> RunMetrics | None:
        """요청 단위 집계. 기록이 없으면 None."""
        runs = self._ok()
        if not runs:
            return None
        costs = [r["cost_usd"] for r in runs if r["cost_usd"] is not None]
        built = [r for r in runs if r["build_count"] >= 1]
        failures = Counter(k for r in runs for k in r["issue_kinds"])
        return RunMetrics(
            avg_response_sec=round(sum(r["response_sec"] for r in runs) / len(runs), 2),
            avg_cost_usd=round(sum(costs) / len(costs), 6) if costs else None,
            recent=[
                RecentRun(run_id=r["run_id"], response_sec=round(r["response_sec"], 2), cost_usd=r["cost_usd"])
                for r in runs[-RECENT_RUNS:]
            ],
            regen_rate=round(sum(r["build_count"] > 1 for r in built) / len(built), 3) if built else None,
            top_failures=[FailureReason(reason=k, count=c) for k, c in failures.most_common(TOP_FAILURES)],
        )


def load_experiments() -> tuple[list[ExperimentResult], str | None]:
    """eval/results/summary.csv를 읽어 버전별 결과로 만든다. 파일이 없으면 빈 목록."""
    path = get_settings().eval_results_dir / "summary.csv"
    if not path.exists():
        return [], None
    results: list[ExperimentResult] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            version = row["version"]
            base = version.split("_", 1)[0]
            desc = EXPERIMENT_DESCRIPTIONS.get(base, version)
            if "_" in version:
                desc += f" ({version.split('_', 1)[1]})"
            results.append(
                ExperimentResult(version=version, description=desc, recall_at_5=float(row["recall@5_all"]), mrr=float(row["mrr_all"]))
            )
    return results, f"eval/results/{path.name}"
