import { describe, expect, it } from 'vitest';
import { mockItinerary } from '../mocks';
import type { AgentStep, StepEvent } from '../types';
import { applyStep, itineraryMessage } from './useChatSession';
import { pickEvidence } from './usePlaceReviews';

const ev = (node: string, status: StepEvent['status'], extra: Partial<StepEvent> = {}): StepEvent => ({
  node,
  label: node,
  status,
  duration_ms: null,
  tokens: null,
  ...extra,
});

describe('applyStep', () => {
  it('running은 추가하고 done은 같은 노드의 진행 중 항목을 완료로 바꾼다', () => {
    let steps: AgentStep[] = [];
    steps = applyStep(steps, ev('parse_request', 'running'));
    steps = applyStep(steps, ev('parse_request', 'done', { duration_ms: 1200, tokens: 379 }));
    expect(steps).toEqual([
      { node: 'parse_request', label: 'parse_request', status: 'done', duration_ms: 1200, tokens: 379 },
    ]);
  });

  it('재생성 루프에서 같은 노드가 반복되면 가장 최근 항목만 완료로 바꾼다', () => {
    let steps: AgentStep[] = [];
    for (const e of [
      ev('build_itinerary', 'running'),
      ev('build_itinerary', 'done', { duration_ms: 4000 }),
      ev('build_itinerary', 'running'),
    ]) {
      steps = applyStep(steps, e);
    }
    steps = applyStep(steps, ev('build_itinerary', 'done', { duration_ms: 5000 }));
    expect(steps.map((s) => [s.status, s.duration_ms])).toEqual([
      ['done', 4000],
      ['done', 5000],
    ]);
  });

  it('시작 이벤트 없이 done만 와도 항목을 추가한다', () => {
    expect(applyStep([], ev('x', 'done', { duration_ms: 1 }))).toHaveLength(1);
  });
});

describe('itineraryMessage', () => {
  it('문제가 없으면 안내 한 줄', () => {
    expect(itineraryMessage(mockItinerary, [])).toBe(
      `${mockItinerary.title} 일정을 만들었어요. 바꾸고 싶은 부분이 있으면 말해 주세요.`,
    );
  });

  it('남은 문제는 최대 5건까지 보이고 나머지는 개수로 알린다', () => {
    const issues = Array.from({ length: 7 }, (_, i) => `문제${i + 1}`);
    const text = itineraryMessage(mockItinerary, issues);
    expect(text).toContain('7건');
    expect(text).toContain('- 문제5');
    expect(text).not.toContain('- 문제6');
    expect(text).toContain('외 2건');
  });
});

describe('pickEvidence', () => {
  it('근거 후기 id에 해당하는 후기만 고른다', () => {
    const r = (id: string) => ({
      review_id: id,
      place_id: 'p',
      text: '',
      rating: 5,
      author_type: '가족' as const,
      season: '가을',
      visit_time: '',
    });
    expect(pickEvidence([r('a'), r('b'), r('c')], ['c', 'a']).map((x) => x.review_id)).toEqual(['a', 'c']);
    expect(pickEvidence([r('a')], [])).toEqual([]);
  });
});
