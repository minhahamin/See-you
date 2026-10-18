import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, createSession, getSession, streamMessage, type StreamHandlers } from '../api/sessions';
import { mockItinerary, mockPlaces } from '../mocks';
import type { AgentStep, ChatMessage, Itinerary, Place, StepEvent } from '../types';

export interface ChatSession {
  messages: ChatMessage[];
  /** 이번 요청에서 실행된 LangGraph 노드들 (재생성 루프면 같은 노드가 반복해서 나온다) */
  steps: AgentStep[];
  running: boolean;
  itinerary: Itinerary | null;
  places: Record<string, Place>;
  /** 에이전트가 사용자 응답을 기다리는 중이면 어떤 응답인지 */
  awaiting: 'question' | 'feedback' | null;
  /** 서버 없이 보여 주는 예시 일정인지 */
  isDemo: boolean;
  send: (text: string) => void;
  loadDemo: () => void;
}

const SESSION_KEY = 'session:v1';
const MAX_ISSUES_SHOWN = 5;

/** step 이벤트를 진행 단계 목록에 반영한다. running은 새 항목을 추가하고, done은 가장 최근의 같은 노드를 완료로 바꾼다. */
export function applyStep(steps: AgentStep[], event: StepEvent): AgentStep[] {
  if (event.status === 'running') {
    return [...steps, { node: event.node, label: event.label, status: 'running', duration_ms: null, tokens: null }];
  }
  let index = -1;
  steps.forEach((s, i) => {
    if (s.node === event.node && s.status === 'running') index = i; // 가장 최근 것
  });
  const done: AgentStep = {
    node: event.node,
    label: event.label,
    status: 'done',
    duration_ms: event.duration_ms,
    tokens: event.tokens,
  };
  if (index === -1) return [...steps, done];
  return steps.map((s, i) => (i === index ? done : s));
}

/** 일정이 나왔을 때 대화에 남길 안내 문구. 검증에서 남은 문제가 있으면 함께 알린다. */
export function itineraryMessage(itinerary: Itinerary, issues: string[]): string {
  const lines = [`${itinerary.title} 일정을 만들었어요. 바꾸고 싶은 부분이 있으면 말해 주세요.`];
  if (issues.length > 0) {
    lines.push('', `검증에서 아직 해결하지 못한 문제가 ${issues.length}건 있어요.`);
    lines.push(...issues.slice(0, MAX_ISSUES_SHOWN).map((m) => `- ${m}`));
    if (issues.length > MAX_ISSUES_SHOWN) lines.push(`- 외 ${issues.length - MAX_ISSUES_SHOWN}건`);
  }
  return lines.join('\n');
}

function storedSessionId(): string | null {
  try {
    return sessionStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
}

function storeSessionId(id: string | null): void {
  try {
    if (id) sessionStorage.setItem(SESSION_KEY, id);
    else sessionStorage.removeItem(SESSION_KEY);
  } catch {
    // 저장소를 못 쓰는 환경에서는 새로고침 시 새 세션으로 시작한다
  }
}

const toPlaceMap = (places: Place[]): Record<string, Place> => Object.fromEntries(places.map((p) => [p.id, p]));

/** 대화·진행 단계·일정 상태. 백엔드 세션(SSE)과 연결되며, 화면을 오가도 유지되도록 App에서 한 번만 만든다. */
export function useChatSession(): ChatSession {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [running, setRunning] = useState(false);
  const [itinerary, setItinerary] = useState<Itinerary | null>(null);
  const [places, setPlaces] = useState<Record<string, Place>>({});
  const [awaiting, setAwaiting] = useState<ChatSession['awaiting']>(null);
  const [isDemo, setIsDemo] = useState(false);

  const sessionId = useRef<string | null>(storedSessionId());
  const runningRef = useRef(false);
  const demoRef = useRef(false);
  const counter = useRef(0);

  const addMessage = useCallback((role: ChatMessage['role'], text: string) => {
    counter.current += 1;
    setMessages((prev) => [...prev, { id: `${role[0]}${Date.now()}-${counter.current}`, role, text }]);
  }, []);

  // 새로고침해도 같은 세션이 이어지도록 서버에서 상태를 복원한다. 서버가 없거나 세션이 사라졌으면 조용히 새로 시작한다.
  useEffect(() => {
    const id = sessionId.current;
    if (!id) return;
    let cancelled = false;
    getSession(id)
      .then((summary) => {
        if (cancelled) return;
        setMessages(summary.messages);
        setItinerary(summary.itinerary);
        setPlaces(toPlaceMap(summary.places));
        setAwaiting(summary.awaiting);
      })
      .catch((e: unknown) => {
        if (e instanceof ApiError && e.status === 404) {
          sessionId.current = null;
          storeSessionId(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handlers: StreamHandlers = {
    onStep: (event) => setSteps((prev) => applyStep(prev, event)),
    onQuestion: (event) => {
      addMessage('assistant', event.question);
      setAwaiting('question');
    },
    onItinerary: (event) => {
      setItinerary(event.itinerary);
      setPlaces(toPlaceMap(event.places));
      setAwaiting('feedback');
      addMessage('assistant', itineraryMessage(event.itinerary, event.issues));
    },
    onError: (message) => addMessage('assistant', `오류: ${message}`),
  };

  const send = useCallback(
    (text: string) => {
      if (runningRef.current) return;
      runningRef.current = true;
      setRunning(true);
      setSteps([]);
      setAwaiting(null);
      if (demoRef.current) {
        // 예시 일정에는 서버 세션이 없으므로, 새 요청을 보내면 예시를 치우고 실제 일정으로 대체한다
        demoRef.current = false;
        setIsDemo(false);
        setItinerary(null);
        setPlaces({});
      }
      addMessage('user', text);

      const run = async (): Promise<void> => {
        for (let attempt = 0; attempt < 2; attempt += 1) {
          try {
            if (!sessionId.current) {
              sessionId.current = await createSession();
              storeSessionId(sessionId.current);
            }
            await streamMessage(sessionId.current, text, handlers);
            return;
          } catch (e) {
            // 서버가 재시작돼 세션이 사라졌으면 새 세션으로 한 번 더 시도한다
            if (e instanceof ApiError && e.status === 404 && attempt === 0) {
              sessionId.current = null;
              storeSessionId(null);
              continue;
            }
            addMessage('assistant', `오류: ${e instanceof Error ? e.message : '알 수 없는 오류가 발생했어요.'}`);
            return;
          }
        }
      };
      void run().finally(() => {
        runningRef.current = false;
        setRunning(false);
      });
    },
    // handlers는 매 렌더에 새로 만들어지지만 setter와 addMessage만 쓰므로 send를 다시 만들 필요가 없다
    [addMessage],
  );

  const loadDemo = useCallback(() => {
    demoRef.current = true;
    setIsDemo(true);
    setItinerary(mockItinerary);
    setPlaces(mockPlaces);
    setAwaiting(null);
  }, []);

  return { messages, steps, running, itinerary, places, awaiting, isDemo, send, loadDemo };
}
