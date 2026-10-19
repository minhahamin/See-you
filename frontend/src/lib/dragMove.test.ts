import { describe, expect, it } from 'vitest';
import { formatClock, moveMessage, snapStart } from './dragMove';
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
