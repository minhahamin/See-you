import type { SessionListItem } from '../types';

/** 목록 카드의 보조 문구: "3일 · 커플". 정보가 없으면 "진행 중". */
export function sessionSubtitle(item: Pick<SessionListItem, 'trip_days' | 'companions'>): string {
  const parts = [item.trip_days ? `${item.trip_days}일` : null, item.companions].filter((p): p is string => !!p);
  return parts.length ? parts.join(' · ') : '진행 중';
}

/** 수정 시각을 "10.19 14:30" 형태로 (사용자의 시간대 기준) */
export function formatUpdatedAt(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getMonth() + 1}.${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
