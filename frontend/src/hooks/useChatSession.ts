import { useCallback, useEffect, useRef, useState } from 'react';
import { DEMO_REPLY, INITIAL_MESSAGES, makeSteps } from '../mocks/chat';
import type { AgentStep, ChatMessage } from '../types';

export interface ChatSession {
  messages: ChatMessage[];
  steps: AgentStep[];
  running: boolean;
  send: (text: string) => void;
}

const STEP_INTERVAL_MS = 700;

/** 대화·진행 단계 상태. API 연결 전에는 타이머로 에이전트 실행을 흉내 낸다. */
export function useChatSession(): ChatSession {
  const [messages, setMessages] = useState<ChatMessage[]>(INITIAL_MESSAGES);
  const [steps, setSteps] = useState<AgentStep[]>(() => makeSteps('done'));
  const [running, setRunning] = useState(false);
  const timers = useRef<number[]>([]);

  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach((id) => window.clearTimeout(id));
  }, []);

  const send = useCallback(
    (text: string) => {
      if (running) return;
      const stamp = Date.now();
      setMessages((prev) => [...prev, { id: `u${stamp}`, role: 'user', text }]);
      setRunning(true);

      const total = makeSteps('pending').length;
      const initial = makeSteps('pending');
      initial[0].status = 'running';
      setSteps(initial);

      for (let i = 0; i < total; i += 1) {
        const id = window.setTimeout(() => {
          setSteps((prev) =>
            prev.map((s, idx) => {
              if (idx === i) return { ...s, status: 'done', duration_ms: makeSteps('done')[i].duration_ms };
              if (idx === i + 1) return { ...s, status: 'running' };
              return s;
            }),
          );
          if (i === total - 1) {
            setMessages((prev) => [...prev, { id: `a${stamp}`, role: 'assistant', text: DEMO_REPLY }]);
            setRunning(false);
          }
        }, (i + 1) * STEP_INTERVAL_MS);
        timers.current.push(id);
      }
    },
    [running],
  );

  return { messages, steps, running, send };
}
