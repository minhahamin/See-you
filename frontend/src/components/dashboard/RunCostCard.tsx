import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { RunMetrics } from '../../types';
import DashboardCard, { NoData } from './DashboardCard';

interface Props {
  runs: RunMetrics | null;
  source: string | null;
  isSample: boolean;
}

function Stat({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <p className="text-xs text-text-sub">{label}</p>
      {value === null ? (
        <p className="mt-1 text-sm text-text-sub">데이터 없음</p>
      ) : (
        <p className="mt-1 text-3xl font-bold tracking-tight">{value}</p>
      )}
    </div>
  );
}

/** 요청당 평균 비용·응답시간과 최근 요청 추이 */
export default function RunCostCard({ runs, source, isSample }: Props) {
  const recent = runs?.recent ?? [];
  const chartData = recent.map((r, i) => ({ n: i + 1, sec: r.response_sec }));

  return (
    <DashboardCard title="요청당 비용·응답시간" source={source} isSample={isSample}>
      {runs === null ? (
        <NoData />
      ) : (
        <>
          <div className="flex gap-10">
            <Stat
              label="평균 응답시간"
              value={runs.avg_response_sec === null ? null : `${runs.avg_response_sec.toFixed(1)}초`}
            />
            <Stat
              label="평균 비용"
              value={runs.avg_cost_usd === null ? null : `$${runs.avg_cost_usd.toFixed(3)}`}
            />
          </div>
          {chartData.length > 0 && (
            <div className="mt-4">
              <p className="mb-1 text-[11px] text-text-sub">최근 {chartData.length}건 응답시간(초)</p>
              <ResponsiveContainer width="100%" height={110}>
                <LineChart data={chartData} margin={{ top: 6, right: 8, left: -24, bottom: 0 }}>
                  <CartesianGrid vertical={false} stroke="#F6E3EA" />
                  <XAxis dataKey="n" hide />
                  <YAxis tickLine={false} axisLine={false} tick={{ fontSize: 11, fill: '#9CA3AF' }} domain={['auto', 'auto']} />
                  <Tooltip formatter={(value) => [`${String(value)}초`, '응답시간']} labelFormatter={(n) => `${String(n)}번째 요청`} />
                  <Line type="monotone" dataKey="sec" stroke="#EE7BA6" strokeWidth={2.5} dot={{ r: 3, fill: '#EE7BA6' }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </>
      )}
    </DashboardCard>
  );
}
