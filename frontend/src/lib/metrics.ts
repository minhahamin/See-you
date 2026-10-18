import type { ExperimentsResponse, MetricsSnapshot, RunsResponse } from '../types';

/**
 * 두 API 응답을 대시보드가 쓰는 한 덩어리로 합친다.
 * 응답이 없으면(null) 해당 카드는 "데이터 없음"으로 표시되며, 값을 만들어 채우지 않는다.
 */
export function buildSnapshot(experiments: ExperimentsResponse | null, runs: RunsResponse | null): MetricsSnapshot {
  return {
    experiments: experiments?.experiments ?? [],
    nodes: runs?.nodes ?? [],
    runs: runs?.runs ?? null,
    sources: {
      experiments: experiments?.source ?? null,
      nodes: runs?.source ?? null,
      runs: runs?.source ?? null,
    },
    is_sample: false,
  };
}
