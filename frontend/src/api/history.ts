import type { SessionListItem } from '../types';
import { request, requestNoContent } from './client';

/** 내 일정(대화) 목록. 로그인이 필요하다. */
export function listSessions(): Promise<SessionListItem[]> {
  return request<SessionListItem[]>('/api/sessions');
}

export function deleteSession(sessionId: string): Promise<void> {
  return requestNoContent('DELETE', `/api/sessions/${sessionId}`);
}

/** 로그인 전에 하던 게스트 대화를 내 계정으로 가져온다. */
export function claimSession(sessionId: string): Promise<void> {
  return requestNoContent('POST', `/api/sessions/${sessionId}/claim`);
}
