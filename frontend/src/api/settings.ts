import type { UserSettings } from '../types';

export type StorageSource = 'server' | 'local';

export interface SettingsResult {
  settings: UserSettings;
  /** 어디에 저장·로드됐는지. 'local'이면 백엔드 DB가 아니라 이 브라우저에만 있다. */
  source: StorageSource;
}

export const EMPTY_SETTINGS: UserSettings = { companion: null, preferences: [], budget: null };

const ENDPOINT = '/api/settings'; // 백엔드 구현 시 GET/PUT, 본문은 UserSettings JSON
const LOCAL_KEY = 'settings:v1';
const REQUEST_TIMEOUT_MS = 2000;

async function request(method: 'GET' | 'PUT', body?: UserSettings): Promise<UserSettings> {
  const res = await fetch(ENDPOINT, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  });
  // 개발 서버가 index.html을 돌려주는 경우도 실패로 본다
  if (!res.ok || !res.headers.get('content-type')?.includes('application/json')) {
    throw new Error(`${method} ${ENDPOINT} failed: ${res.status}`);
  }
  return (await res.json()) as UserSettings;
}

function readLocal(): UserSettings {
  try {
    const raw = localStorage.getItem(LOCAL_KEY);
    return raw ? { ...EMPTY_SETTINGS, ...(JSON.parse(raw) as Partial<UserSettings>) } : EMPTY_SETTINGS;
  } catch {
    return EMPTY_SETTINGS;
  }
}

function writeLocal(settings: UserSettings): void {
  try {
    localStorage.setItem(LOCAL_KEY, JSON.stringify(settings));
  } catch {
    // 저장소를 쓸 수 없는 환경에서는 저장되지 않는다
  }
}

/** 서버 DB에서 설정을 불러온다. 연결되지 않으면 localStorage 값을 쓴다. */
export async function loadSettings(): Promise<SettingsResult> {
  try {
    return { settings: await request('GET'), source: 'server' };
  } catch {
    return { settings: readLocal(), source: 'local' };
  }
}

/** 서버 DB에 저장한다. 연결되지 않으면 localStorage에만 저장하고 source로 알린다. */
export async function saveSettings(settings: UserSettings): Promise<SettingsResult> {
  try {
    return { settings: await request('PUT', settings), source: 'server' };
  } catch {
    writeLocal(settings);
    return { settings, source: 'local' };
  }
}
