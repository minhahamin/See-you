import { formatDuration } from '../lib/time';
import type { TripStats } from '../lib/summary';

/** 모바일용 여행 요약: 타임라인 상단 가로 스크롤 칩 */
export default function TripSummaryChips({ stats }: { stats: TripStats }) {
  const chips = [
    `${stats.placeCount}곳 방문`,
    `이동 ${formatDuration(stats.totalTravelMin)}`,
    `하루 평균 ${formatDuration(stats.avgTravelMin)}`,
    `실내 ${stats.indoorPercent}%`,
    `조건 충족 ${stats.passed}/${stats.total}`,
  ];
  return (
    <ul className="flex gap-2 overflow-x-auto">
      {chips.map((chip) => (
        <li key={chip} className="shrink-0 rounded-full bg-surface px-4 py-2 text-xs font-semibold shadow-soft">
          {chip}
        </li>
      ))}
    </ul>
  );
}
