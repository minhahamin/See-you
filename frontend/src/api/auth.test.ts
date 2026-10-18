import { afterEach, describe, expect, it, vi } from 'vitest';
import { deleteAccount, fetchMe, login, logout, signup } from './auth';
import { streamMessage } from './sessions';

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

afterEach(() => vi.unstubAllGlobals());

describe('auth API', () => {
  it('fetchMe는 게스트면 null을 돌려준다 (오류가 아니다)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ user: null })));
    expect(await fetchMe()).toBeNull();
  });

  it('가입은 빈 이름을 null로 보내고, 서버의 오류 문구를 그대로 전달한다', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ detail: '이미 가입된 이메일이에요.' }, 409));
    vi.stubGlobal('fetch', fetchMock);
    await expect(signup('a@b.co', 'password1', '  ')).rejects.toMatchObject({ status: 409, message: '이미 가입된 이메일이에요.' });
    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string)).toEqual({ email: 'a@b.co', password: 'password1', display_name: null });
  });

  it('로그인 실패는 서버가 준 일반 문구를 보여 준다', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: '이메일 또는 비밀번호가 올바르지 않아요.' }, 401)));
    await expect(login('a@b.co', 'bad')).rejects.toMatchObject({ status: 401, message: '이메일 또는 비밀번호가 올바르지 않아요.' });
  });

  it('검증 오류(422)는 영어 원문 대신 안내 문구로 바꾼다', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: [{ msg: 'String should have at least 8 characters' }] }, 422)));
    await expect(signup('a@b.co', 'x', '')).rejects.toMatchObject({ message: '입력한 내용을 다시 확인해 주세요.' });
  });

  it('로그아웃과 계정 삭제는 204를 성공으로 본다', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(logout()).resolves.toBeUndefined();
    await expect(deleteAccount('pw')).resolves.toBeUndefined();
    expect(fetchMock.mock.calls[1][0]).toContain('/api/auth/delete-account');
    expect(JSON.parse(fetchMock.mock.calls[1][1].body as string)).toEqual({ password: 'pw' });
  });
});

describe('메시지 전송의 설정 전달', () => {
  const settings = { companion: '커플', preferences: ['카페'], budget: 3 } as const;
  const okStream = () => new Response('event: done\ndata: {}\n\n', { status: 200 });
  const handlers = { onStep: () => {}, onQuestion: () => {}, onItinerary: () => {}, onError: () => {} };

  it('게스트 설정을 본문에 싣는다', async () => {
    const fetchMock = vi.fn().mockResolvedValue(okStream());
    vi.stubGlobal('fetch', fetchMock);
    await streamMessage('s1', '안녕', handlers, undefined, { ...settings, preferences: [...settings.preferences] });
    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string)).toEqual({ text: '안녕', settings });
  });

  it('로그인한 사용자는 설정을 싣지 않는다 (서버가 계정 설정을 쓴다)', async () => {
    const fetchMock = vi.fn().mockResolvedValue(okStream());
    vi.stubGlobal('fetch', fetchMock);
    await streamMessage('s1', '안녕', handlers);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string)).toEqual({ text: '안녕', settings: null });
  });
});
