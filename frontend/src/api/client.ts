// API 호출 공통: 기본 주소, 오류 형태, JSON 요청.

// 개발 중에는 비워 두면 Vite 프록시를 탄다. 배포에서는 VITE_API_BASE_URL에 백엔드 주소를 넣는다.
export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/** 서버에 연결하지 못했을 때(네트워크 오류) 보여 줄 문구 */
export const NETWORK_ERROR_MESSAGE = '서버에 연결하지 못했어요. 백엔드(uvicorn)가 실행 중인지 확인해 주세요.';

export async function errorDetail(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === 'string') return body.detail;
    if (Array.isArray(body.detail)) return '입력한 내용을 다시 확인해 주세요.';
  } catch {
    // 본문이 JSON이 아니면 상태 코드로만 알린다
  }
  return `요청에 실패했어요 (${res.status})`;
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new ApiError(0, NETWORK_ERROR_MESSAGE);
  }
  if (!res.ok) throw new ApiError(res.status, await errorDetail(res));
  return (await res.json()) as T;
}

/** 본문이 없는(204) 응답을 돌려주는 요청. 상태 코드만 확인한다. */
export async function requestNoContent(method: 'POST' | 'DELETE', path: string, body?: unknown): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, NETWORK_ERROR_MESSAGE);
  }
  if (!res.ok) throw new ApiError(res.status, await errorDetail(res));
}
