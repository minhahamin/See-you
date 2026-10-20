import { useState } from 'react';
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { ExperimentResult, MetricKey } from '../../types';
import DashboardCard, { NoData } from './DashboardCard';

const METRICS: { key: MetricKey; label: string; better: 'high' | 'low' }[] = [
  { key: 'recall_at_5', label: 'Recall@5', better: 'high' },
  { key: 'mrr', label: 'MRR', better: 'high' },
  { key: 'faithfulness', label: 'Faithfulness', better: 'high' },
  { key: 'violation_rate', label: '조건 위반율', better: 'low' },
];

// recharts는 Tailwind 토큰을 못 읽으므로 tailwind.config.js의 primary와 같은 계열을 직접 쓴다
const BEST_COLOR = '#EE7BA6';
const OTHER_COLOR = '#F9CADB';

// 'v4_bge-reranker-v2-m3' → 'v4 bge'. 긴 이름이 x축에서 서로 겹쳐 라벨이 사라지는 것을 막는다
const shortLabel = (version: string): string => {
  const [base, rest] = version.split('_');
  return rest ? `${base} ${rest.split('-')[0]}` : version;
};

const toPercent = (v: number | null): number | null => (v === null ? null : Math.round(v * 1000) / 10);

interface Props {
  experiments: ExperimentResult[];
  source: string | null;
  isSample: boolean;
}

/** v1~v5 버전별 검색·생성·일정 지표 비교 */
export default function ExperimentCard({ experiments, source, isSample }: Props) {
  const [metricKey, setMetricKey] = useState<MetricKey>('recall_at_5');
  const metric = METRICS.find((m) => m.key === metricKey) ?? METRICS[0];

  const data = experiments.map((e) => ({ version: e.version, value: toPercent(e[metric.key]) }));
  const values = data.flatMap((d) => (d.value === null ? [] : [d.value]));
  const best = values.length ? (metric.better === 'high' ? Math.max(...values) : Math.min(...values)) : null;

  return (
    <DashboardCard title="실험 비교 (v1 → v5)" source={source} isSample={isSample} className="lg:col-span-2">
      {values.length === 0 ? (
        <NoData />
      ) : (
        <>
          <div className="mb-3 flex flex-wrap gap-2" role="tablist" aria-label="지표 선택">
            {METRICS.map((m) => (
              <button
                key={m.key}
                type="button"
                role="tab"
                aria-selected={m.key === metricKey}
                onClick={() => setMetricKey(m.key)}
                className={`rounded-full px-3.5 py-1.5 text-xs font-semibold transition-colors ${
                  m.key === metricKey ? 'bg-primary text-white' : 'bg-bg text-text-sub hover:text-text-main'
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
          <p className="mb-1 text-[11px] text-text-sub">{metric.better === 'high' ? '높을수록 좋음' : '낮을수록 좋음'} (%)</p>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="#F6E3EA" />
              <XAxis dataKey="version" interval={0} tickFormatter={shortLabel} tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: '#9CA3AF' }} />
              <YAxis tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: '#9CA3AF' }} />
              <Tooltip
                cursor={{ fill: 'rgba(238,123,166,0.08)' }}
                formatter={(value) => [`${String(value)}%`, metric.label]}
              />
              <Bar dataKey="value" radius={[10, 10, 0, 0]} maxBarSize={56}>
                {data.map((d) => (
                  <Cell key={d.version} fill={d.value === best ? BEST_COLOR : OTHER_COLOR} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>

          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[480px] text-left text-xs">
              <thead className="text-text-sub">
                <tr>
                  <th className="py-1.5 font-medium">버전</th>
                  <th className="py-1.5 font-medium">구성</th>
                  {METRICS.map((m) => (
                    <th key={m.key} className="py-1.5 text-right font-medium">
                      {m.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {experiments.map((e) => (
                  <tr key={e.version} className="border-t border-bg">
                    <td className="py-1.5 font-semibold">{e.version}</td>
                    <td className="py-1.5 text-text-sub">{e.description}</td>
                    {METRICS.map((m) => {
                      const v = toPercent(e[m.key]);
                      return (
                        <td key={m.key} className="py-1.5 text-right tabular-nums">
                          {v === null ? '–' : `${v}%`}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </DashboardCard>
  );
}
