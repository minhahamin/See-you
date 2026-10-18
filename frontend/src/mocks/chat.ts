// 화면 개발용 대화·진행 단계 더미. 실제 에이전트 응답이 아니다.
import type { AgentStep, ChatMessage } from '../types';

export const MOCK_STEP_DEFS: { node: string; label: string; duration_ms: number }[] = [
  { node: 'parse_request', label: '여행 조건 파악', duration_ms: 1200 },
  { node: 'search_places', label: '장소·후기 검색', duration_ms: 600 },
  { node: 'analyze_reviews', label: '후기 분석', duration_ms: 3800 },
  { node: 'check_weather', label: '날씨 확인', duration_ms: 400 },
  { node: 'build_itinerary', label: '일정 생성', duration_ms: 6500 },
  { node: 'validate_itinerary', label: '일정 검증', duration_ms: 1100 },
];

/** 모든 단계를 같은 상태로 만든 목록 */
export function makeSteps(status: AgentStep['status']): AgentStep[] {
  return MOCK_STEP_DEFS.map((s) => ({
    node: s.node,
    label: s.label,
    status,
    duration_ms: status === 'done' ? s.duration_ms : null,
  }));
}

export const INITIAL_MESSAGES: ChatMessage[] = [
  { id: 'm1', role: 'user', text: '커플이 11월 중순에 제주 3일 여행 가려고 해요. 바다 보면서 카페도 가고 싶어요.' },
  {
    id: 'm2',
    role: 'assistant',
    text: '조건을 반영해 3일 일정을 만들었어요. 2일차는 비 예보가 있어 실내 장소 위주로 구성했습니다.',
  },
];

export const DEMO_REPLY =
  '[데모] 지금은 시뮬레이션 응답입니다. 백엔드를 연결하면 실제 에이전트가 일정을 수정합니다.';
