import { useCallback, useEffect, useState } from 'react';
import { getExperiments, getRuns } from '../api/metrics';
import { buildSnapshot } from '../lib/metrics';
import type { MetricsSnapshot } from '../types';

export type MetricsState =
  | { status: 'loading' }
  | { status: 'ready'; snapshot: MetricsSnapshot }
  | { status: 'error'; message: string };

/** 성능 지표를 백엔드에서 가져온다. 한쪽만 실패해도 받은 쪽은 보여 주고, 둘 다 실패하면 오류로 처리한다. */
export function useMetrics(): { state: MetricsState; reload: () => void } {
  const [state, setState] = useState<MetricsState>({ status: 'loading' });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState({ status: 'loading' });
    void Promise.allSettled([getExperiments(), getRuns()]).then(([exp, runs]) => {
      if (cancelled) return;
      if (exp.status === 'rejected' && runs.status === 'rejected') {
        const reason: unknown = exp.reason;
        setState({ status: 'error', message: reason instanceof Error ? reason.message : '지표를 불러오지 못했어요.' });
        return;
      }
      setState({
        status: 'ready',
        snapshot: buildSnapshot(
          exp.status === 'fulfilled' ? exp.value : null,
          runs.status === 'fulfilled' ? runs.value : null,
        ),
      });
    });
    return () => {
      cancelled = true;
    };
  }, [tick]);

  const reload = useCallback(() => setTick((n) => n + 1), []);
  return { state, reload };
}
