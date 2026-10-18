import { formatDuration } from '../lib/time';
import type { TripStats } from '../lib/summary';

/** 여행 요약 카드: 방문 장소 수, 이동·실내 지표, 조건 충족률 */
export default function TripSummary({ stats }: { stats: TripStats }) {
  return (
    <section className="shrink-0 rounded-3xl bg-surface p-6 shadow-soft [@media(max-height:720px)]:p-4">
      <h2 className="text-center text-sm font-semibold">여행 요약</h2>
      <p className="mt-3 text-center text-5xl font-bold tracking-tight [@media(max-height:720px)]:mt-1 [@media(max-height:720px)]:text-4xl">
        {stats.placeCount}
        <span className="ml-1 text-2xl text-text-sub">곳</span>
      </p>
      <p className="mt-1 text-center text-xs text-text-sub">방문 장소 (숙소 제외)</p>

      <dl className="mt-5 grid grid-cols-3 gap-2 text-center [@media(max-height:720px)]:mt-3">
        <div>
          <dt className="text-[11px] text-text-sub">총 이동시간</dt>
          <dd className="mt-0.5 text-sm font-semibold">{formatDuration(stats.totalTravelMin)}</dd>
        </div>
        <div>
          <dt className="text-[11px] text-text-sub">하루 평균</dt>
          <dd className="mt-0.5 text-sm font-semibold">{formatDuration(stats.avgTravelMin)}</dd>
        </div>
        <div>
          <dt className="text-[11px] text-text-sub">실내 비율</dt>
          <dd className="mt-0.5 text-sm font-semibold">{stats.indoorPercent}%</dd>
        </div>
      </dl>

      <div className="mt-5 [@media(max-height:720px)]:mt-3">
        <div className="mb-1.5 flex items-baseline justify-between text-xs">
          <span className="font-medium">조건 충족률</span>
          <span className="text-text-sub">
            <span className="font-bold text-text-main">{stats.passed}</span>/{stats.total}
          </span>
        </div>
        <div
          className="h-2.5 overflow-hidden rounded-full bg-bg"
          role="progressbar"
          aria-valuenow={stats.passPercent}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div className="h-full rounded-full bg-primary" style={{ width: `${stats.passPercent}%` }} />
        </div>
        <p className="mt-1 text-right text-[11px] text-primary-ink">{stats.passPercent}%</p>
      </div>
    </section>
  );
}
