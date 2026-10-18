import type { UserSettings } from '../types';
import { request } from './client';

export type StorageSource = 'server' | 'local';

export interface SettingsResult {
  settings: UserSettings;
  /** 어디에 저장·로드됐는지. 'local'이면 계정(서버 DB)이 아니라 이 브라우저에만 있다. */
  source: StorageSource;
}

export const EMPTY_SETTINGS: UserSettings = { companion: null, preferences: [], budget: null };

const ENDPOINT = '/api/settings';
const LOCAL_KEY = 'settings:v1';
const JSON_HEADERS = { 'Content-Type': 'application/json' };

/** 설정이 하나도 없는 상태인지 */
export function isEmptySettings(s: UserSettings): boolean {
  return s.companion === null && s.budget === null && s.preferences.length === 0;
}

/** 이 브라우저에 저장된 설정. 로그인하지 않은 사용자의 설정이고, 대화 요청에도 실려 간다. */
export function readLocalSettings(): UserSettings {
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

/** 로그인했으면 계정(서버)에서, 아니면 이 브라우저에서 설정을 불러온다. 서버를 못 읽으면 브라우저 값을 보여 준다. */
export async function loadSettings(loggedIn: boolean): Promise<SettingsResult> {
  if (!loggedIn) return { settings: readLocalSettings(), source: 'local' };
  try {
    return { settings: await request<UserSettings>(ENDPOINT), source: 'server' };
  } catch {
    return { settings: readLocalSettings(), source: 'local' };
  }
}

/**
 * 로그인했으면 계정(서버)에 저장하고, 아니면 이 브라우저에만 저장한다.
 * 로그인 상태에서 서버 저장이 실패하면 저장된 것처럼 보이지 않도록 오류를 그대로 던진다.
 */
export async function saveSettings(settings: UserSettings, loggedIn: boolean): Promise<SettingsResult> {
  if (!loggedIn) {
    writeLocal(settings);
    return { settings, source: 'local' };
  }
  const saved = await request<UserSettings>(ENDPOINT, { method: 'PUT', headers: JSON_HEADERS, body: JSON.stringify(settings) });
  return { settings: saved, source: 'server' };
}

/**
 * 로그인한 직후, 계정에 저장된 설정이 비어 있고 이 브라우저에 설정이 있으면 계정으로 옮긴다.
 * 계정에 이미 설정이 있으면 그것을 존중해 아무것도 덮어쓰지 않는다. 옮겼으면 true.
 */
export async function migrateLocalSettings(): Promise<boolean> {
  const local = readLocalSettings();
  if (isEmptySettings(local)) return false;
  const remote = await request<UserSettings>(ENDPOINT);
  if (!isEmptySettings(remote)) return false;
  await request<UserSettings>(ENDPOINT, { method: 'PUT', headers: JSON_HEADERS, body: JSON.stringify(local) });
  return true;
}
