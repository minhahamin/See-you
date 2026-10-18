import type {
  ErrorEvent,
  ItineraryEvent,
  PlaceDetail,
  QuestionEvent,
  SessionSummary,
  StepEvent,
  UserSettings,
} from '../types';
import { API_BASE, ApiError, NETWORK_ERROR_MESSAGE, errorDetail, request } from './client';
import { readSse, type SseMessage } from './sse';

export { ApiError } from './client';

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
  guestSettings?: UserSettings,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/sessions/${sessionId}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // 로그인하지 않은 사용자는 브라우저에 저장된 설정을 실어 보낸다 (로그인했으면 서버가 계정 설정을 쓴다)
      body: JSON.stringify({ text, settings: guestSettings ?? null }),
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
