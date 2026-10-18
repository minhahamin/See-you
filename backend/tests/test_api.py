"""FastAPI 엔드포인트와 SSE 스트림, 지표 수집 테스트."""
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from agent.graph import build_graph, make_checkpointer
from agent.nodes.parse_request import ParsedRequest
from api.main import create_app
from api.metrics import MetricsStore, RunRecorder, classify_issue
from api.schemas import PlaceOut


def parse_sse(text: str) -> list[tuple[str, dict]]:
    """SSE 응답 본문을 (event, data) 목록으로 파싱한다."""
    events = []
    for block in text.replace("\r\n", "\n").strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.split("\n") if ": " in line)
        if "event" in fields:
            events.append((fields["event"], json.loads(fields.get("data", "{}") or "{}")))
    return events


@pytest.fixture
def client(wired, tmp_path, db_url):
    """가짜 LLM·검색으로 그래프를 구성한 테스트 클라이언트 (지표는 임시 파일, 계정·대화는 실제 Postgres)."""
    store = MetricsStore(tmp_path / "runs.jsonl")
    app = create_app(graph=build_graph(make_checkpointer()), store=store, database_url=db_url)
    with TestClient(app) as c:
        c.store = store  # type: ignore[attr-defined]
        yield c


def send(client: TestClient, sid: str, text: str) -> list[tuple[str, dict]]:
    """메시지를 보내고 SSE 이벤트를 모두 받는다."""
    r = client.post(f"/api/sessions/{sid}/messages", json={"text": text})
    assert r.status_code == 200
    return parse_sse(r.text)


def test_health(client) -> None:
    """헬스체크."""
    assert client.get("/api/health").json() == {"status": "ok"}


def test_unknown_session_and_validation(client) -> None:
    """없는 세션은 404, 빈 메시지는 422."""
    assert client.post("/api/sessions/nope/messages", json={"text": "hi"}).status_code == 404
    assert client.get("/api/sessions/nope").status_code == 404
    sid = client.post("/api/sessions").json()["session_id"]
    assert client.post(f"/api/sessions/{sid}/messages", json={"text": ""}).status_code == 422


def test_question_then_itinerary_stream(client) -> None:
    """부족한 조건이면 question, 답하면 step들과 itinerary가 스트리밍되고 항상 done으로 끝난다."""
    sid = client.post("/api/sessions").json()["session_id"]

    first = send(client, sid, "제주 2박 3일 가고 싶어요")
    names = [e for e, _ in first]
    assert names[-1] == "done" and "question" in names
    q = dict(first)["question"]
    assert set(q["missing_fields"]) == {"start_date", "companions"}
    steps = [d for e, d in first if e == "step"]
    assert steps[0]["node"] == "parse_request" and steps[0]["status"] == "running"
    assert steps[0]["label"] == "여행 조건 파악"
    assert any(d["status"] == "done" and d["duration_ms"] is not None for d in steps)

    summary = client.get(f"/api/sessions/{sid}").json()
    assert summary["awaiting"] == "question" and summary["itinerary"] is None
    assert summary["messages"][0]["role"] == "user"

    second = send(client, sid, "11월 14일에 커플로 가요")
    payload = dict(second)["itinerary"]
    assert len(payload["itinerary"]["days"]) == 2
    assert payload["itinerary"]["days"][0]["weather"] is None  # 날씨 연동 전
    shown = {v["place_id"] for d in payload["itinerary"]["days"] for v in d["visits"]}
    assert shown == {p["id"] for p in payload["places"]}
    PlaceOut.model_validate(payload["places"][0])
    assert [e for e, _ in second][-1] == "done"
    assert client.get(f"/api/sessions/{sid}").json()["awaiting"] == "feedback"


def test_error_event_closes_stream(client, fake_llm) -> None:
    """노드가 실패하면 error 후 done으로 닫히고, 내부 예외 내용은 노출하지 않는다."""

    def boom(msgs: list):
        raise RuntimeError("secret-internal-detail")

    fake_llm[ParsedRequest] = boom
    sid = client.post("/api/sessions").json()["session_id"]
    events = send(client, sid, "제주 가고 싶어요")
    assert [e for e, _ in events][-2:] == ["error", "done"]
    assert "secret-internal-detail" not in json.dumps(dict(events)["error"], ensure_ascii=False)
    assert client.get("/api/metrics/runs").json()["runs"] is None  # 실패한 실행은 집계하지 않는다


def test_place_detail(client) -> None:
    """장소 상세는 후기와 합성 데이터 안내를 함께 준다."""
    from agent import catalog

    pid = next(iter(catalog.reviews_by_place()))
    body = client.get(f"/api/places/{pid}").json()
    assert body["place"]["id"] == pid and body["reviews"] and "합성" in body["disclaimer"]
    assert client.get("/api/places/0000").status_code == 404


def test_metrics_experiments_from_results_csv(client) -> None:
    """실험 결과는 eval/results/summary.csv에서 읽고, 값이 없는 지표는 null이다."""
    body = client.get("/api/metrics/experiments").json()
    versions = {e["version"]: e for e in body["experiments"]}
    assert {"v1", "v2", "v3"} <= set(versions)
    assert versions["v2"]["recall_at_5"] > versions["v1"]["recall_at_5"]
    assert versions["v1"]["faithfulness"] is None and body["source"].endswith("summary.csv")


def test_metrics_runs_aggregate_after_a_run(client) -> None:
    """실행 후에는 노드별 지연과 요청 집계가 생기고, 단가가 없으면 비용은 null이다."""
    assert client.get("/api/metrics/runs").json() == {"nodes": [], "runs": None, "source": None}
    sid = client.post("/api/sessions").json()["session_id"]
    send(client, sid, "11월에 커플로 2박 3일")
    body = client.get("/api/metrics/runs").json()
    nodes = {n["node"]: n for n in body["nodes"]}
    assert "build_itinerary" in nodes and nodes["build_itinerary"]["avg_latency_ms"] >= 0
    assert body["runs"]["avg_response_sec"] > 0 and body["runs"]["avg_cost_usd"] is None
    assert body["runs"]["recent"][0]["cost_usd"] is None
    assert 0 <= body["runs"]["regen_rate"] <= 1
    assert len(body["runs"]["top_failures"]) <= 3
    assert (client.store._path).read_text(encoding="utf-8").strip()  # type: ignore[attr-defined]


def test_run_recorder_attributes_tokens_to_node() -> None:
    """LLM 호출의 토큰은 호출이 시작된 노드에 더해진다."""
    rec = RunRecorder()
    run_id = uuid4()
    rec.on_chat_model_start({}, [], run_id=run_id, metadata={"langgraph_node": "analyze_reviews"})
    msg = SimpleNamespace(usage_metadata={"input_tokens": 100, "output_tokens": 20})
    rec.on_llm_end(SimpleNamespace(generations=[[SimpleNamespace(message=msg)]]), run_id=run_id)
    assert rec.node_tokens("analyze_reviews") == 120 and rec.node_tokens("build_itinerary") == 0


def test_classify_issue() -> None:
    """검증 문제 문장은 실패 사유로 분류된다."""
    assert classify_issue("1일차 이동이 과합니다(총 205분)") == "이동 과다"
    assert classify_issue("2일차 X: 예산(가격대)을 넘습니다.") == "예산 초과"
    assert classify_issue("3일차에 관광지가 없습니다. 관광지를 1곳 이상 넣으세요.") == "관광지 누락"
    assert classify_issue("알 수 없는 문장") == "기타"


def test_serves_built_frontend_without_hiding_api(wired, tmp_path, db_url) -> None:
    """빌드된 프론트(dist)가 있으면 /에서 서빙하고, /api 라우트는 그대로 동작한다. 없으면 / 는 404."""
    from config import get_settings

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>seeyou-app</body></html>", encoding="utf-8")
    graph = build_graph(make_checkpointer())
    base = get_settings()

    with TestClient(create_app(graph=graph, store=MetricsStore(), database_url=db_url, settings=base.model_copy(update={"frontend_dist": dist}))) as c:
        assert "seeyou-app" in c.get("/").text
        assert c.get("/api/health").json() == {"status": "ok"}

    with TestClient(create_app(graph=graph, store=MetricsStore(), database_url=db_url, settings=base.model_copy(update={"frontend_dist": tmp_path / "missing"}))) as c:
        assert c.get("/").status_code == 404
        assert c.get("/api/health").status_code == 200


def test_experiments_merge_itinerary_summary(tmp_path, monkeypatch) -> None:
    """일정 평가 결과가 있으면 v3 행에는 루프 없음, v5 행에는 루프 적용 지표가 붙고 v5 검색 지표는 v3와 같다."""
    from api import metrics as M

    summary_rows = [
        "date,version,embedding_model,n_trait,recall@5_trait,mrr_trait,n_keyword,recall@5_keyword,mrr_keyword,n_all,recall@5_all,mrr_all",
        "2026-10-19,v1,m,19,0.5,0.7,18,0.9,0.9,37,0.7,0.8",
        "2026-10-19,v3,m,19,0.9,0.9,18,0.9,0.9,37,0.9,0.95",
    ]
    itinerary_rows = [
        "date,config,model,n,violation_itinerary_rate,violation_check_rate,faithfulness",
        "2026-10-19,no_loop,m,10,0.9,0.12,0.8",
        "2026-10-19,loop,m,10,0.5,0.04,0.85",
    ]
    (tmp_path / "summary.csv").write_text("\n".join(summary_rows) + "\n", encoding="utf-8-sig")
    (tmp_path / "itinerary_summary.csv").write_text("\n".join(itinerary_rows) + "\n", encoding="utf-8-sig")
    monkeypatch.setattr(M, "get_settings", lambda: SimpleNamespace(eval_results_dir=tmp_path))
    results, source = M.load_experiments()
    by = {r.version: r for r in results}
    assert [r.version for r in results] == ["v1", "v3", "v5"]
    assert (by["v3"].violation_rate, by["v3"].faithfulness) == (0.12, 0.8)
    assert (by["v5"].violation_rate, by["v5"].faithfulness) == (0.04, 0.85)
    assert (by["v5"].recall_at_5, by["v5"].mrr) == (by["v3"].recall_at_5, by["v3"].mrr)
    assert by["v1"].violation_rate is None and source.endswith("itinerary_summary.csv")

    (tmp_path / "itinerary_summary.csv").unlink()  # 일정 평가가 없으면 v5 행도 만들지 않는다
    assert [r.version for r in M.load_experiments()[0]] == ["v1", "v3"]
