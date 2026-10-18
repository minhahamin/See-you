# 🧳 여행 일정 플래너 에이전트
> 여행 조건을 말하면 장소·후기를 검색하고 날씨와 동선을 고려해
> 일정을 짜고, 피드백에 맞춰 수정하는 LangGraph 기반 Agentic RAG 서비스

> 개발 진행 중 (4단계 진행: v1~v3 검색 실험 완료, v4 리랭커 예정)

## 데이터
- 장소: 한국관광공사 TourAPI(KorService2) 제주 30곳 (관광지 12, 음식점 8, 카페 5, 숙소 5)
- 후기: LLM 합성 데이터 453개 (**실제 리뷰 아님**, 장소당 10~19개)
- 생성 방식: 장소별 숨은 특성(`place_traits.json`) → 특성 기반 후기 생성
- 이렇게 만든 이유: 이용약관 준수 + 정답을 아는 평가셋 확보
- 생성 모델: 특성 25곳은 `gemini-2.5-flash`, 5곳은 `gemini-2.5-flash-lite`. 후기 12곳은 `gemini-2.5-flash-lite`, 18곳은 `gemini-3.1-flash-lite` (무료 티어 일일 한도 때문에 모델이 섞여 있음)
- 인덱스: 장소 1청크 + 후기 1청크(같은 장소 안의 동일 본문 제거) = 482청크, 임베딩 `gemini-embedding-2`, Chroma(cosine)

## 실험 및 평가
평가셋은 `place_traits.json`의 특성 조합(동행 유형, 실내/야외, 가격대, 분류)으로 규칙 기반 생성한 질문 21개다 (`backend/eval/testset.json`).
정답은 특성 조건을 만족하는 장소 집합이고, 지표는 장소 단위로 계산한다.
- Recall@5 = 상위 5개 중 정답 수 / min(정답 수, 5)
- MRR = 첫 정답 순위의 역수 (상위 10개 기준)

| 버전 | 구성 | Recall@5 | MRR | Faithfulness | 조건 위반율 |
|---|---|---|---|---|---|
| v1 | 벡터 검색 | 0.656 | 0.889 | - | - |
| v2 | + 메타데이터 필터 | 0.900 | 0.976 | - | - |
| v3 | + 하이브리드 | 0.870 | 0.898 | - | - |
| v4 | + 리랭커 | | | | |
| v5 | + validate 루프 | | | | |

질문별 결과는 `backend/eval/results/`의 CSV에 있다.

### 결과 해석
- **v1 → v2 (+0.244)**: 벡터 검색만으로는 "카페", "숙소" 같은 분류와 동행 조건이 잘 반영되지 않았다. 분류·실내 여부는 장소 단위로 허용 id를 먼저 구한 뒤 후기 청크까지 거르고, 동행 유형은 후기의 `author_type`으로 거른다.
- **v2 → v3 (-0.030)**: BM25(어절 + 문자 바이그램, RRF 결합)를 더했더니 오히려 낮아졌다. 평가셋의 질문이 "혼자서 가기 좋은", "가격 부담 없는" 같은 **특성 기반 표현**이라 어휘 일치가 우연히 맞는 후기를 끌어올리는 경우가 있었다. 어절만 쓰기, BM25 가중치 0.5 같은 변형도 v2를 넘지 못했다.
- 이 평가셋에는 고유명사·메뉴명 같은 **키워드형 질문**이 없어서 BM25의 강점이 측정되지 않았다. 키워드형 질문을 추가해 다시 확인할 계획이다.
- v2의 필터는 평가셋에 기록된 값(파싱이 완벽하다고 가정)을 썼다. 실제 서비스에서는 `parse_request`의 추출 정확도가 상한을 정한다.

## 실행 방법
```bash
cp .env.example .env   # 키 입력 (TOUR_API_KEY, LLM_*, EMBEDDING_MODEL)
cd backend
pip install -r requirements.txt

# 데이터 생성 (순서대로)
python -m ingest.fetch_places
python -m ingest.generate_traits
python -m ingest.generate_reviews

# 인덱싱과 평가
python -m ingest.build_index
python -m eval.build_testset
python -m eval.run_eval --version v1
```

Gemini 무료 티어는 채팅 모델 일일 20회, 임베딩 분당 100건 한도가 있어서 생성 스크립트는 중단 후 다시 실행하면 이어서 진행한다.
