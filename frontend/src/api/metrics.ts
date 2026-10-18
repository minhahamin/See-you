import type { ExperimentsResponse, RunsResponse } from '../types';
import { request } from './client';

/** 버전별 평가 결과 (eval/results 기반) */
export function getExperiments(): Promise<ExperimentsResponse> {
  return request<ExperimentsResponse>('/api/metrics/experiments');
}

/** 노드별 지연·토큰, 요청당 응답시간·비용, 재생성 통계 */
export function getRuns(): Promise<RunsResponse> {
  return request<RunsResponse>('/api/metrics/runs');
}
