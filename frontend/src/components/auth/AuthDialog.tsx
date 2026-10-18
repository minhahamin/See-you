import { X } from 'lucide-react';
import { useEffect, useState, type FormEvent } from 'react';
import { validateCredentials } from '../../lib/authForm';

type Mode = 'login' | 'signup';

interface Props {
  open: boolean;
  onClose: () => void;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, displayName: string) => Promise<void>;
}

const INPUT = 'w-full rounded-2xl bg-bg px-4 py-3 text-sm outline-none ring-primary/40 placeholder:text-text-sub focus:ring-2';

/** 로그인·회원가입 다이얼로그. 이메일과 비밀번호만 받는다. */
export default function AuthDialog({ open, onClose, login, signup }: Props) {
  const [mode, setMode] = useState<Mode>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // 열 때마다 입력을 비운다 (비밀번호가 화면 상태에 남아 있지 않게 한다)
  useEffect(() => {
    if (open) {
      setPassword('');
      setError(null);
      setBusy(false);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const problem = validateCredentials(email, password, mode);
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (mode === 'login') await login(email.trim(), password);
      else await signup(email.trim(), password, name);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : '문제가 생겼어요. 다시 시도해 주세요.');
    } finally {
      setBusy(false);
      setPassword('');
    }
  };

  return (
    <div className="fixed inset-0 z-[60] grid place-items-center bg-text-main/30 p-4 backdrop-blur-sm" onMouseDown={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={mode === 'login' ? '로그인' : '회원가입'}
        className="w-full max-w-sm rounded-3xl bg-surface p-6 shadow-2xl"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h2 className="text-lg font-bold">{mode === 'login' ? '로그인' : '회원가입'}</h2>
            <p className="mt-1 text-xs text-text-sub">
              로그인하면 일정 기록과 설정이 계정에 저장돼요. 로그인 없이도 쓸 수 있어요.
            </p>
          </div>
          <button type="button" aria-label="닫기" onClick={onClose} className="grid size-8 place-items-center rounded-full bg-bg text-text-sub">
            <X size={16} />
          </button>
        </div>

        <div className="mb-4 flex rounded-full bg-bg p-1" role="tablist">
          {(['login', 'signup'] as const).map((m) => (
            <button
              key={m}
              type="button"
              role="tab"
              aria-selected={mode === m}
              onClick={() => {
                setMode(m);
                setError(null);
              }}
              className={`flex-1 rounded-full py-1.5 text-sm font-medium transition-colors ${
                mode === m ? 'bg-primary text-white' : 'text-text-sub'
              }`}
            >
              {m === 'login' ? '로그인' : '회원가입'}
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3" noValidate>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="이메일"
            aria-label="이메일"
            autoComplete="email"
            className={INPUT}
          />
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={mode === 'signup' ? '비밀번호 (8자 이상)' : '비밀번호'}
            aria-label="비밀번호"
            autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
            className={INPUT}
          />
          {mode === 'signup' && (
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="이름 (선택)"
              aria-label="이름"
              maxLength={40}
              autoComplete="nickname"
              className={INPUT}
            />
          )}
          {error && (
            <p role="alert" className="rounded-2xl bg-primary/10 px-4 py-2 text-xs font-medium text-primary-ink">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={busy}
            className="mt-1 rounded-full bg-primary py-3 text-sm font-semibold text-white shadow-soft disabled:opacity-60"
          >
            {busy ? '처리 중…' : mode === 'login' ? '로그인' : '가입하고 시작하기'}
          </button>
        </form>
      </div>
    </div>
  );
}
