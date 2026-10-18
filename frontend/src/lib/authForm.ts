export const MIN_PASSWORD_LENGTH = 8;
export const MAX_PASSWORD_LENGTH = 128;

// 형식만 가볍게 확인한다. 실제 검증은 서버가 한다.
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** 로그인·가입 입력의 문제를 한국어 문구로 돌려준다. 문제가 없으면 null. */
export function validateCredentials(email: string, password: string, mode: 'login' | 'signup'): string | null {
  if (!EMAIL_PATTERN.test(email.trim())) return '이메일 형식을 확인해 주세요.';
  if (!password) return '비밀번호를 입력해 주세요.';
  if (password.length > MAX_PASSWORD_LENGTH) return `비밀번호는 ${MAX_PASSWORD_LENGTH}자 이하로 입력해 주세요.`;
  if (mode === 'signup' && password.length < MIN_PASSWORD_LENGTH) {
    return `비밀번호는 ${MIN_PASSWORD_LENGTH}자 이상이어야 해요.`;
  }
  return null;
}
