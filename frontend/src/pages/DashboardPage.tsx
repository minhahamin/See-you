import ExperimentCard from '../components/dashboard/ExperimentCard';
import NodeLatencyCard from '../components/dashboard/NodeLatencyCard';
import RegenCard from '../components/dashboard/RegenCard';
import RunCostCard from '../components/dashboard/RunCostCard';
import { mockMetrics } from '../mocks/metrics';

/** 성능 대시보드: 백엔드가 제공하는 결과만 표시하고 직접 계산하지 않는다 */
export default function DashboardPage() {
  // API 연결 전이라 샘플 데이터를 사용한다
  const m = mockMetrics;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <header>
        <h1 className="text-2xl font-bold lg:text-3xl">성능 대시보드</h1>
        {m.is_sample && (
          <p className="mt-1 text-sm text-text-sub">
            표시된 수치는 화면 개발용 샘플이며 실제 평가 결과가 아닙니다.
          </p>
        )}
      </header>
      <div className="grid min-h-0 flex-1 grid-cols-1 content-start gap-4 overflow-y-auto pb-2 lg:grid-cols-2">
        <ExperimentCard experiments={m.experiments} source={m.sources.experiments} isSample={m.is_sample} />
        <NodeLatencyCard nodes={m.nodes} source={m.sources.nodes} isSample={m.is_sample} />
        <RunCostCard runs={m.runs} source={m.sources.runs} isSample={m.is_sample} />
        <RegenCard runs={m.runs} source={m.sources.runs} isSample={m.is_sample} />
      </div>
    </div>
  );
}
