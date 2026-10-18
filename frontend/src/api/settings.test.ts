import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  EMPTY_SETTINGS,
  isEmptySettings,
  loadSettings,
  migrateLocalSettings,
  readLocalSettings,
  saveSettings,
} from './settings';

const FILLED = { companion: '가족', preferences: ['실내 위주'], budget: 2 } as const;
const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

/** 브라우저 localStorage를 흉내 낸다 */
function stubStorage() {
  const store = new Map<string, string>();
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
  });
  return store;
}

beforeEach(() => {
  stubStorage();
});
afterEach(() => vi.unstubAllGlobals());

describe('isEmptySettings', () => {
  it('아무 값도 없을 때만 비어 있다', () => {
    expect(isEmptySettings(EMPTY_SETTINGS)).toBe(true);
    expect(isEmptySettings({ ...EMPTY_SETTINGS, budget: 1 })).toBe(false);
    expect(isEmptySettings({ ...EMPTY_SETTINGS, preferences: ['x'] })).toBe(false);
  });
});

describe('게스트 설정은 브라우저에만', () => {
  it('저장하면 localStorage에 쓰고 서버를 부르지 않는다', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    const result = await saveSettings({ ...FILLED, preferences: [...FILLED.preferences] }, false);
    expect(result.source).toBe('local');
    expect(readLocalSettings().companion).toBe('가족');
    expect(fetchMock).not.toHaveBeenCalled();
    expect((await loadSettings(false)).settings.budget).toBe(2);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe('로그인한 사용자의 설정은 서버에', () => {
  it('서버에서 읽고 저장한다', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(FILLED)).mockResolvedValueOnce(jsonResponse(FILLED));
    vi.stubGlobal('fetch', fetchMock);
    expect(await loadSettings(true)).toMatchObject({ source: 'server', settings: { companion: '가족' } });
    expect((await saveSettings({ ...EMPTY_SETTINGS, companion: '가족' }, true)).source).toBe('server');
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: 'PUT' });
  });

  it('서버 저장이 실패하면 저장된 것처럼 보이지 않게 오류를 던진다', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: '서버 오류' }, 500)));
    await expect(saveSettings(EMPTY_SETTINGS, true)).rejects.toThrow('서버 오류');
    expect(readLocalSettings()).toEqual(EMPTY_SETTINGS); // 브라우저에도 몰래 쓰지 않는다
  });

  it('서버를 읽지 못하면 브라우저 값을 보여 주되 source로 알린다', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('network')));
    expect((await loadSettings(true)).source).toBe('local');
  });
});

describe('migrateLocalSettings: 로그인 직후 브라우저 설정을 계정으로', () => {
  const seedLocal = () => localStorage.setItem('settings:v1', JSON.stringify(FILLED));

  it('브라우저 설정이 없으면 아무것도 하지 않는다', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    expect(await migrateLocalSettings()).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('계정에 이미 설정이 있으면 덮어쓰지 않는다', async () => {
    seedLocal();
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ companion: '혼자', preferences: [], budget: null }));
    vi.stubGlobal('fetch', fetchMock);
    expect(await migrateLocalSettings()).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(1); // GET만, PUT 없음
  });

  it('계정 설정이 비어 있으면 브라우저 설정을 옮긴다', async () => {
    seedLocal();
    // 호출마다 새 Response를 돌려줘야 한다 (본문은 한 번만 읽을 수 있다)
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(jsonResponse(EMPTY_SETTINGS)));
    vi.stubGlobal('fetch', fetchMock);
    expect(await migrateLocalSettings()).toBe(true);
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: 'PUT', body: JSON.stringify(FILLED) });
  });
});
