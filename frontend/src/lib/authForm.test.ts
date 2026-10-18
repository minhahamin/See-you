import { describe, expect, it } from 'vitest';
import { formatUpdatedAt, sessionSubtitle } from './history';
import { validateCredentials } from './authForm';

describe('validateCredentials', () => {
  it('이메일 형식과 빈 비밀번호를 거른다', () => {
    expect(validateCredentials('nope', 'password1', 'login')).toMatch(/이메일/);
    expect(validateCredentials('a@b', 'password1', 'login')).toMatch(/이메일/);
    expect(validateCredentials('a@b.co', '', 'login')).toMatch(/비밀번호/);
  });

  it('가입은 8자 이상을 요구하지만 로그인은 길이를 따지지 않는다 (예전 비밀번호로도 로그인할 수 있어야 한다)', () => {
    expect(validateCredentials('a@b.co', 'short', 'signup')).toMatch(/8자/);
    expect(validateCredentials('a@b.co', 'short', 'login')).toBeNull();
    expect(validateCredentials(' a@b.co ', 'long-enough', 'signup')).toBeNull();
  });

  it('너무 긴 비밀번호를 거른다', () => {
    expect(validateCredentials('a@b.co', 'x'.repeat(129), 'login')).toMatch(/128자/);
  });
});

describe('history helpers', () => {
  it('목록 보조 문구는 일수와 동행을 잇고, 정보가 없으면 진행 중', () => {
    expect(sessionSubtitle({ trip_days: 3, companions: '커플' })).toBe('3일 · 커플');
    expect(sessionSubtitle({ trip_days: 2, companions: null })).toBe('2일');
    expect(sessionSubtitle({ trip_days: null, companions: null })).toBe('진행 중');
  });

  it('수정 시각을 월.일 시:분으로 바꾸고, 잘못된 값은 빈 문자열', () => {
    const d = new Date(2026, 9, 9, 7, 5); // 로컬 시간 기준
    expect(formatUpdatedAt(d.toISOString())).toBe('10.9 07:05');
    expect(formatUpdatedAt('not-a-date')).toBe('');
  });
});
