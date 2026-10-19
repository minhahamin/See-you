import { DAY_END_MIN, DAY_START_MIN, PX_PER_HOUR } from './time';

/** 끌어다 놓을 때 시작 시각이 맞춰지는 단위(분) — 타임라인 격자와 같다 */
export const SNAP_MIN = 30;

/** 방문을 놓을 곳: 도착 일차와 시작 시각(자정 기준 분) */
export interface DropTarget {
  day: number;
  startMin: number;
}

/** 방문 이동 요청: 어느 방문을 어디로 옮기는지 */
export interface MoveRequest extends DropTarget {
  fromDay: number;
  fromIndex: number; // 0부터
}

/** 자정 기준 분 → "HH:MM" */
export function formatClock(minutes: number): string {
  return `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;
}

/** 블록의 왼쪽 위치(px, 트랙 기준)를 30분 격자에 맞춘 시작 시각으로 바꾼다. 하루 범위를 벗어나지 않게 자른다 */
export function snapStart(leftPx: number, durationMin: number): number {
  const raw = DAY_START_MIN + (leftPx / PX_PER_HOUR) * 60;
  const snapped = Math.round(raw / SNAP_MIN) * SNAP_MIN;
  return Math.min(Math.max(snapped, DAY_START_MIN), DAY_END_MIN - durationMin);
}

/**
 * 에이전트에게 보낼 이동 문장. 백엔드(agent/moving.py)의 MOVE_PATTERN과 형식이 같아야 한다.
 * 순번은 사람이 세는 1부터다.
 */
export function moveMessage(move: MoveRequest, placeName: string): string {
  return `${move.fromDay}일차 ${move.fromIndex + 1}번째 방문(${placeName})을 ${move.day}일차 ${formatClock(move.startMin)}로 옮겨줘`;
}
