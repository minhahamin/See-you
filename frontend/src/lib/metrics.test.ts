import { describe, expect, it } from 'vitest';
import type { ExperimentsResponse, RunsResponse } from '../types';
import { buildSnapshot } from './metrics';

const experiments: ExperimentsResponse = {
  experiments: [{ version: 'v1', description: '벡터 검색', recall_at_5: 0.8, mrr: 0.9, faithfulness: null, violation_rate: null }],
  source: 'eval/results/summary.csv',
};

const runs: RunsResponse = {
  nodes: [{ node: 'build_itinerary', avg_latency_ms: 5000, avg_tokens: 5300 }],
  runs: { avg_response_sec: 30, avg_cost_usd: null, recent: [], regen_rate: 1, top_failures: [] },
  source: 'data/metrics/runs.jsonl',
};

describe('buildSnapshot', () => {
  it('두 응답을 합치고 출처를 그대로 전달하며 샘플이 아님을 표시한다', () => {
    const s = buildSnapshot(experiments, runs);
    expect(s.is_sample).toBe(false);
    expect(s.experiments).toHaveLength(1);
    expect(s.nodes[0].node).toBe('build_itinerary');
    expect(s.sources).toEqual({
      experiments: 'eval/results/summary.csv',
      nodes: 'data/metrics/runs.jsonl',
      runs: 'data/metrics/runs.jsonl',
    });
  });

  it('응답이 없으면 빈 값과 null 출처로 둔다 (값을 만들어 채우지 않는다)', () => {
    const s = buildSnapshot(null, null);
    expect(s.experiments).toEqual([]);
    expect(s.nodes).toEqual([]);
    expect(s.runs).toBeNull();
    expect(s.sources).toEqual({ experiments: null, nodes: null, runs: null });
  });

  it('한쪽만 있어도 받은 쪽은 살린다', () => {
    const s = buildSnapshot(experiments, null);
    expect(s.experiments).toHaveLength(1);
    expect(s.runs).toBeNull();
    expect(s.sources.experiments).toBe('eval/results/summary.csv');
  });
});
