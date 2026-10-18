"""버전별 검색 평가를 실행해 eval/results/에 CSV로 저장한다.

지표는 장소 단위로 계산한다 (청크 검색 결과를 장소로 묶은 뒤 비교).
- Recall@k = 상위 k개 중 정답 수 / min(정답 수, k)
- MRR      = 첫 정답 장소 순위의 역수 (상위 10개 안에 없으면 0)
"""
import argparse
import csv
import json
import logging
from datetime import date
from typing import Any, Callable

from config import get_settings, setup_logging
from retrieval.hybrid import hybrid_search
from retrieval.vector import allowed_place_ids, build_where, rank_places, search_chunks

logger = logging.getLogger(__name__)

K = 5
MRR_DEPTH = 10


def search_v1(question: dict[str, Any]) -> list[str]:
    """v1: 벡터 검색만 (메타데이터 필터 없음)."""
    return rank_places(search_chunks(question["question"]))


def search_v2(question: dict[str, Any]) -> list[str]:
    """v2: v1 + 메타데이터 필터. 필터는 평가셋의 filters(파싱이 완벽하다고 가정한 값)를 쓴다."""
    filters = question["filters"]
    allowed = allowed_place_ids(filters)
    return rank_places(search_chunks(question["question"], where=build_where(filters, allowed)))


def search_v3(question: dict[str, Any]) -> list[str]:
    """v3: v2 + BM25 하이브리드 (RRF 결합)."""
    return rank_places(hybrid_search(question["question"], filters=question["filters"]))


VERSIONS: dict[str, Callable[[dict[str, Any]], list[str]]] = {"v1": search_v1, "v2": search_v2, "v3": search_v3}


def recall_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    """Recall@k를 계산한다."""
    return len(set(ranked[:k]) & relevant) / min(len(relevant), k)


def reciprocal_rank(ranked: list[str], relevant: set[str], depth: int) -> float:
    """첫 정답의 순위 역수를 계산한다."""
    for rank, pid in enumerate(ranked[:depth], start=1):
        if pid in relevant:
            return 1 / rank
    return 0.0


def run(version: str) -> None:
    """한 버전을 평가하고 질문별 결과와 요약을 저장한다."""
    settings = get_settings()
    testset = json.loads((settings.eval_results_dir.parent / "testset.json").read_text(encoding="utf-8"))
    search = VERSIONS[version]

    rows: list[dict[str, Any]] = []
    for q in testset:
        ranked = search(q)
        relevant = set(q["relevant_place_ids"])
        rows.append(
            {
                "id": q["id"],
                "type": q["type"],
                "question": q["question"],
                "n_relevant": len(relevant),
                f"recall@{K}": round(recall_at_k(ranked, relevant, K), 4),
                "rr": round(reciprocal_rank(ranked, relevant, MRR_DEPTH), 4),
                "top5": " ".join(ranked[:K]),
            }
        )

    out_dir = settings.eval_results_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    detail_path = out_dir / f"{date.today().isoformat()}_{version}.csv"
    with detail_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    mean_recall = sum(r[f"recall@{K}"] for r in rows) / len(rows)
    mrr = sum(r["rr"] for r in rows) / len(rows)
    summary_path = out_dir / "summary.csv"
    is_new = not summary_path.exists()
    with summary_path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["date", "version", "n_questions", f"recall@{K}", "mrr", "embedding_model"])
        writer.writerow(
            [date.today().isoformat(), version, len(rows), round(mean_recall, 4), round(mrr, 4), settings.embedding_model]
        )
    logger.info("%s: 질문 %d개 | Recall@%d %.3f | MRR %.3f | %s", version, len(rows), K, mean_recall, mrr, detail_path.name)


def main() -> None:
    """명령행 인자로 받은 버전을 평가한다."""
    setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="v1", choices=list(VERSIONS))
    run(parser.parse_args().version)


if __name__ == "__main__":
    main()
