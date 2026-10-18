import { RefreshCw } from 'lucide-react';
import ExperimentCard from '../components/dashboard/ExperimentCard';
import NodeLatencyCard from '../components/dashboard/NodeLatencyCard';
import RegenCard from '../components/dashboard/RegenCard';
import RunCostCard from '../components/dashboard/RunCostCard';
import { useMetrics } from '../hooks/useMetrics';

/** 성능 대시보드: 백엔드가 제공하는 결과만 표시하고 직접 계산하지 않는다 */
export default function DashboardPage() {
  const { state, reload } = useMetrics();

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold lg:text-3xl">성능 대시보드</h1>
          <p className="mt-1 text-sm text-text-sub">
            평가 결과는 eval/results, 실행 지표는 에이전트를 실행할 때마다 쌓이는 기록에서 가져옵니다.
          </p>
        </div>
        <button
          type="button"
          onClick={reload}
          disabled={state.status === 'loading'}
          className="flex shrink-0 items-center gap-2 rounded-full bg-surface px-4 py-2 text-sm font-medium shadow-soft disabled:opacity-60"
        >
          <RefreshCw size={14} className={`text-primary ${state.status === 'loading' ? 'animate-spin' : ''}`} />
          새로고침
        </button>
      </header>

      {state.status === 'loading' && (
        <p className="rounded-3xl bg-surface p-8 text-center text-sm text-text-sub shadow-soft">지표를 불러오는 중…</p>
      )}
      {state.status === 'error' && (
        <p role="alert" className="rounded-3xl bg-surface p-8 text-center text-sm text-primary-ink shadow-soft">
          {state.message}
        </p>
      )}
      {state.status === 'ready' && (
        <div className="grid min-h-0 flex-1 grid-cols-1 content-start gap-4 overflow-y-auto pb-2 lg:grid-cols-2">
          <ExperimentCard
            experiments={state.snapshot.experiments}
            source={state.snapshot.sources.experiments}
            isSample={state.snapshot.is_sample}
          />
          <NodeLatencyCard
            nodes={state.snapshot.nodes}
            source={state.snapshot.sources.nodes}
            isSample={state.snapshot.is_sample}
          />
          <RunCostCard
            runs={state.snapshot.runs}
            source={state.snapshot.sources.runs}
            isSample={state.snapshot.is_sample}
          />
          <RegenCard
            runs={state.snapshot.runs}
            source={state.snapshot.sources.runs}
            isSample={state.snapshot.is_sample}
          />
        </div>
      )}
    </div>
  );
}
