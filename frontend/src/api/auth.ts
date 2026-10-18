import type { User } from '../types';
import { request, requestNoContent } from './client';

const JSON_HEADERS = { 'Content-Type': 'application/json' };

/** 현재 로그인한 사용자. 로그인하지 않았으면 null (오류가 아니다). */
export async function fetchMe(): Promise<User | null> {
  return (await request<{ user: User | null }>('/api/auth/me')).user;
}

export function signup(email: string, password: string, displayName: string): Promise<User> {
  return request<User>('/api/auth/signup', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ email, password, display_name: displayName.trim() || null }),
  });
}

export function login(email: string, password: string): Promise<User> {
  return request<User>('/api/auth/login', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ email, password }),
  });
}

export function logout(): Promise<void> {
  return requestNoContent('POST', '/api/auth/logout');
}

/** 비밀번호를 확인하고 계정과 모든 데이터를 지운다. */
export function deleteAccount(password: string): Promise<void> {
  return requestNoContent('POST', '/api/auth/delete-account', { password });
}
