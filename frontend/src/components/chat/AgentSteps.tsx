import { Check, Circle, Loader2 } from 'lucide-react';
import type { AgentStep } from '../../types';

const formatTokens = (n: number): string => (n >= 1000 ? `${(n / 1000).toFixed(1)}k tok` : `${n} tok`);

/** 에이전트(LangGraph 노드)별 진행 단계. 검증 실패로 재생성하면 같은 노드가 다시 나타난다. */
export default function AgentSteps({ steps }: { steps: AgentStep[] }) {
  return (
    <ol className="flex flex-col gap-2 rounded-2xl bg-bg/70 p-4">
      {steps.map((step, i) => (
        <li key={`${step.node}-${i}`} className="flex items-center gap-3 text-sm">
          <span className="grid size-5 shrink-0 place-items-center">
            {step.status === 'done' && <Check size={16} className="text-primary-ink" />}
            {step.status === 'running' && <Loader2 size={16} className="animate-spin text-primary" />}
            {step.status === 'pending' && <Circle size={10} className="text-text-sub/60" />}
          </span>
          <span className={step.status === 'pending' ? 'text-text-sub' : 'font-medium'}>{step.label}</span>
          <span className="ml-auto font-mono text-[11px] text-text-sub">
            {step.tokens ? `${formatTokens(step.tokens)} · ` : ''}
            {step.duration_ms !== null ? `${(step.duration_ms / 1000).toFixed(1)}s` : ''}
          </span>
        </li>
      ))}
    </ol>
  );
}
