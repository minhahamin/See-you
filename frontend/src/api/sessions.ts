import type {
  ErrorEvent,
  ItineraryEvent,
  PlaceDetail,
  QuestionEvent,
  SessionSummary,
  StepEvent,
} from '../types';
import { readSse, type SseMessage } from './sse';

// 개발 중에는 비워 두면 Vite 프록시를 탄다. 배포에서는 VITE_API_BASE_URL에 백엔드 주소를 넣는다.
const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/** 서버에 연결하지 못했을 때(네트워크 오류)와 서버가 오류를 돌려줬을 때를 구분하기 위한 표시 */
export const NETWORK_ERROR_MESSAGE = '서버에 연결하지 못했어요. 백엔드(uvicorn)가 실행 중인지 확인해 주세요.';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new ApiError(0, NETWORK_ERROR_MESSAGE);
  }
  if (!res.ok) throw new ApiError(res.status, await errorDetail(res));
  return (await res.json()) as T;
}

async function errorDetail(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === 'string') return body.detail;
  } catch {
    // 본문이 JSON이 아니면 상태 코드로만 알린다
  }
  return `요청에 실패했어요 (${res.status})`;
}

export async function createSession(): Promise<string> {
  return (await request<{ session_id: string }>('/api/sessions', { method: 'POST' })).session_id;
}

export function getSession(sessionId: string): Promise<SessionSummary> {
  return request<SessionSummary>(`/api/sessions/${sessionId}`);
}

export function getPlaceDetail(placeId: string): Promise<PlaceDetail> {
  return request<PlaceDetail>(`/api/places/${placeId}`);
}

export interface StreamHandlers {
  onStep: (event: StepEvent) => void;
  onQuestion: (event: QuestionEvent) => void;
  onItinerary: (event: ItineraryEvent) => void;
  onError: (message: string) => void;
}

/** SSE 메시지 하나를 알맞은 핸들러로 보낸다. 스트림이 끝났으면 true */
export function dispatchSse(message: SseMessage, handlers: StreamHandlers): boolean {
  if (message.event === 'done') return true;
  let payload: unknown;
  try {
    payload = JSON.parse(message.data);
  } catch {
    return false; // 깨진 이벤트는 건너뛴다
  }
  switch (message.event) {
    case 'step':
      handlers.onStep(payload as StepEvent);
      break;
    case 'question':
      handlers.onQuestion(payload as QuestionEvent);
      break;
    case 'itinerary':
      handlers.onItinerary(payload as ItineraryEvent);
      break;
    case 'error':
      handlers.onError((payload as ErrorEvent).message);
      break;
  }
  return false;
}

/** 메시지를 보내고 SSE 이벤트를 받는다. 서버가 done을 보내거나 연결이 끝나면 반환한다. */
export async function streamMessage(
  sessionId: string,
  text: string,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/sessions/${sessionId}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
      signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') return;
    throw new ApiError(0, NETWORK_ERROR_MESSAGE);
  }
  if (!res.ok || !res.body) throw new ApiError(res.status, await errorDetail(res));

  try {
    for await (const message of readSse(res.body)) {
      if (dispatchSse(message, handlers)) return;
    }
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') return;
    throw new ApiError(0, '응답을 받는 중 연결이 끊겼어요.');
  }
}
