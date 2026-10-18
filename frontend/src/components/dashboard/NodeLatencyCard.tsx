import type { NodeMetric } from '../../types';
import DashboardCard, { NoData } from './DashboardCard';

interface Props {
  nodes: NodeMetric[];
  source: string | null;
  isSample: boolean;
}

/** LangGraph 노드별 평균 지연시간·토큰 (가로 막대) */
export default function NodeLatencyCard({ nodes, source, isSample }: Props) {
  const max = Math.max(0, ...nodes.map((n) => n.avg_latency_ms ?? 0));

  return (
    <DashboardCard title="노드별 성능" source={source} isSample={isSample} className="lg:row-span-2">
      {nodes.length === 0 ? (
        <NoData />
      ) : (
        <ul className="flex flex-col gap-4">
          {nodes.map((n) => (
            <li key={n.node}>
              <div className="mb-1 flex items-baseline justify-between gap-2 text-xs">
                <span className="truncate font-mono font-medium">{n.node}</span>
                <span className="shrink-0 text-text-sub">
                  {n.avg_latency_ms === null ? '데이터 없음' : `${(n.avg_latency_ms / 1000).toFixed(1)}초`}
                  {n.avg_tokens !== null && ` · ${n.avg_tokens.toLocaleString()} tok`}
                </span>
              </div>
              <div className="h-2.5 overflow-hidden rounded-full bg-bg">
                <div
                  className="h-full rounded-full bg-primary"
                  style={{ width: max && n.avg_latency_ms ? `${(n.avg_latency_ms / max) * 100}%` : '0%' }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </DashboardCard>
  );
}
