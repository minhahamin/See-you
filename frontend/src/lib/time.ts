export const DAY_START_MIN = 8 * 60;
export const DAY_END_MIN = 22 * 60;
export const PX_PER_HOUR = 120;
export const TRACK_WIDTH = ((DAY_END_MIN - DAY_START_MIN) / 60) * PX_PER_HOUR;

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];

/** "HH:MM" → 자정 기준 분 */
export function toMinutes(time: string): number {
  const [h, m] = time.split(':').map(Number);
  return h * 60 + m;
}

/** 자정 기준 분 → 타임라인 가로 위치(px) */
export function minutesToPx(minutes: number): number {
  return ((minutes - DAY_START_MIN) / 60) * PX_PER_HOUR;
}

/** 분 → "1시간 20분" / "45분" */
export function formatDuration(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  if (h === 0) return `${m}분`;
  return m === 0 ? `${h}시간` : `${h}시간 ${m}분`;
}

/** "YYYY-MM-DD" → "11.14 (토)" */
export function formatDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return `${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')} (${WEEKDAYS[d.getDay()]})`;
}
