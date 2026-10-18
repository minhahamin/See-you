// 화면 개발용 샘플 수치. 실제 평가 결과가 아니다. eval/results 결과가 생기면 /api/metrics/*로 교체한다.
import type { MetricsSnapshot } from '../types';

export const mockMetrics: MetricsSnapshot = {
  is_sample: true,
  sources: {
    experiments: '샘플 (src/mocks/metrics.ts)',
    nodes: '샘플 (src/mocks/metrics.ts)',
    runs: '샘플 (src/mocks/metrics.ts)',
  },
  experiments: [
    { version: 'v1', description: '벡터 검색', recall_at_5: 0.52, mrr: 0.41, faithfulness: 0.71, violation_rate: 0.31 },
    { version: 'v2', description: '+ 메타데이터 필터', recall_at_5: 0.63, mrr: 0.5, faithfulness: 0.73, violation_rate: 0.22 },
    { version: 'v3', description: '+ 하이브리드(BM25)', recall_at_5: 0.71, mrr: 0.58, faithfulness: 0.76, violation_rate: 0.18 },
    { version: 'v4', description: '+ 리랭커', recall_at_5: 0.78, mrr: 0.66, faithfulness: 0.8, violation_rate: 0.15 },
    { version: 'v5', description: '+ validate 루프', recall_at_5: 0.78, mrr: 0.66, faithfulness: 0.91, violation_rate: 0.06 },
  ],
  nodes: [
    { node: 'parse_request', avg_latency_ms: 1200, avg_tokens: 450 },
    { node: 'ask_clarification', avg_latency_ms: 900, avg_tokens: 300 },
    { node: 'search_places', avg_latency_ms: 600, avg_tokens: 0 },
    { node: 'analyze_reviews', avg_latency_ms: 3800, avg_tokens: 2800 },
    { node: 'check_weather', avg_latency_ms: 400, avg_tokens: 0 },
    { node: 'build_itinerary', avg_latency_ms: 6500, avg_tokens: 4200 },
    { node: 'validate_itinerary', avg_latency_ms: 1100, avg_tokens: 900 },
    { node: 'apply_feedback', avg_latency_ms: 2700, avg_tokens: 1800 },
  ],
  runs: {
    avg_response_sec: 14.8,
    avg_cost_usd: 0.034,
    regen_rate: 0.18,
    recent: [
      { run_id: 'r1', response_sec: 13.2, cost_usd: 0.031 },
      { run_id: 'r2', response_sec: 15.9, cost_usd: 0.036 },
      { run_id: 'r3', response_sec: 12.4, cost_usd: 0.029 },
      { run_id: 'r4', response_sec: 19.1, cost_usd: 0.045 },
      { run_id: 'r5', response_sec: 14.0, cost_usd: 0.033 },
      { run_id: 'r6', response_sec: 13.7, cost_usd: 0.032 },
      { run_id: 'r7', response_sec: 16.3, cost_usd: 0.038 },
      { run_id: 'r8', response_sec: 14.5, cost_usd: 0.034 },
      { run_id: 'r9', response_sec: 12.8, cost_usd: 0.03 },
      { run_id: 'r10', response_sec: 15.1, cost_usd: 0.035 },
    ],
    top_failures: [
      { reason: '이동거리 과다', count: 9 },
      { reason: '영업시간 충돌', count: 6 },
      { reason: '근거 없는 주장', count: 4 },
    ],
  },
};
