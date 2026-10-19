import { describe, expect, it } from 'vitest';
import type { Visit } from '../types';
import { formatClock, moveMessage, snapStart, startAtDayEnd, startForVisitSlot } from './dragMove';
import { DAY_END_MIN, DAY_START_MIN, PX_PER_HOUR } from './time';

describe('snapStart', () => {
  it('30분 격자에 맞춘다', () => {
    expect(snapStart(0, 60)).toBe(DAY_START_MIN);
    expect(snapStart(PX_PER_HOUR * 6.4, 60)).toBe(14 * 60 + 30); // 08:00 + 6.4시간 = 14:24 → 14:30
  });

  it('하루 범위를 벗어나면 자른다', () => {
    expect(snapStart(-500, 60)).toBe(DAY_START_MIN);
    expect(snapStart(PX_PER_HOUR * 20, 90)).toBe(DAY_END_MIN - 90);
  });
});

describe('moveMessage', () => {
  it('백엔드가 읽는 형식으로 만든다', () => {
    const text = moveMessage({ fromDay: 1, fromIndex: 1, day: 2, startMin: 14 * 60 + 30 }, '성산일출봉');
    expect(text).toBe('1일차 2번째 방문(성산일출봉)을 2일차 14:30로 옮겨줘');
    expect(text).toMatch(/(\d+)일차 (\d+)번째 방문\(.*\)을 (\d+)일차 (\d{1,2}:\d{2})로 옮겨줘/); // 백엔드 MOVE_PATTERN과 동일
  });

  it('시각은 두 자리로 채운다', () => {
    expect(formatClock(9 * 60)).toBe('09:00');
  });
});

describe('모바일 목록 끌기', () => {
  const visit = (start: string, end: string): Visit => ({ place_id: start, start, end } as Visit);
  const visits = [visit('09:00', '10:30'), visit('11:00', '12:00'), visit('13:15', '14:40')];

  it('위 방문으로 옮기면 그 방문의 시작 시각을 쓴다', () => {
    expect(startForVisitSlot(visits, 2, 0)).toBe(9 * 60);
  });

  it('아래 방문으로 옮기면 그 방문이 끝난 뒤 30분 격자를 쓴다', () => {
    expect(startForVisitSlot(visits, 0, 2)).toBe(15 * 60); // 14:40 → 15:00
  });

  it('같은 자리면 옮기지 않는다', () => {
    expect(startForVisitSlot(visits, 1, 1)).toBeNull();
  });

  it('하루 범위를 벗어나지 않게 자른다', () => {
    const late = [visit('09:00', '10:00'), visit('20:30', '21:50')];
    expect(startForVisitSlot(late, 0, 1)).toBe(DAY_END_MIN - 60);
  });

  it('다른 일차 탭에 놓으면 그날 마지막 방문 뒤, 빈 날이면 하루 시작', () => {
    expect(startAtDayEnd(visits, 90)).toBe(15 * 60);
    expect(startAtDayEnd([], 90)).toBe(DAY_START_MIN);
  });
});
