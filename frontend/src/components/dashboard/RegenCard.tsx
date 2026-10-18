import type { RunMetrics } from '../../types';
import DashboardCard, { NoData } from './DashboardCard';

interface Props {
  runs: RunMetrics | null;
  source: string | null;
  isSample: boolean;
}

/** validate 재생성 비율과 주요 실패 사유 Top 3 */
export default function RegenCard({ runs, source, isSample }: Props) {
  const failures = [...(runs?.top_failures ?? [])].sort((a, b) => b.count - a.count).slice(0, 3);
  const max = Math.max(0, ...failures.map((f) => f.count));

  return (
    <DashboardCard title="재생성 루프" source={source} isSample={isSample}>
      {runs === null || runs.regen_rate === null ? (
        <NoData />
      ) : (
        <>
          <p className="text-xs text-text-sub">validate 재생성 비율</p>
          <p className="mt-1 text-3xl font-bold tracking-tight">{Math.round(runs.regen_rate * 100)}%</p>

          <h3 className="mb-2 mt-5 text-xs font-semibold text-text-sub">주요 실패 사유 Top 3</h3>
          {failures.length === 0 ? (
            <p className="text-sm text-text-sub">데이터 없음</p>
          ) : (
            <ul className="flex flex-col gap-3">
              {failures.map((f) => (
                <li key={f.reason}>
                  <div className="mb-1 flex justify-between text-xs">
                    <span className="font-medium">{f.reason}</span>
                    <span className="text-text-sub">{f.count}건</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-bg">
                    <div
                      className="h-full rounded-full bg-primary"
                      style={{ width: max ? `${(f.count / max) * 100}%` : '0%' }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </DashboardCard>
  );
}
