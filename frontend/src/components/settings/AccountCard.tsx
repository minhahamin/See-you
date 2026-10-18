import { useState, type FormEvent } from 'react';
import { useAuth } from '../../hooks/useAuth';

/** 계정 관리: 이메일 표시, 로그아웃, 계정 삭제(비밀번호 확인) */
export default function AccountCard() {
  const { user, logout, deleteAccount } = useAuth();
  const [confirming, setConfirming] = useState(false);
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!user) return null;

  const handleDelete = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await deleteAccount(password);
    } catch (err) {
      setError(err instanceof Error ? err.message : '삭제하지 못했어요.');
      setBusy(false);
    } finally {
      setPassword('');
    }
  };

  return (
    <section className="flex max-w-2xl flex-col gap-4 rounded-3xl bg-surface p-6 shadow-soft lg:p-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-base font-bold">계정</h2>
          <p className="mt-1 truncate text-sm text-text-sub">{user.display_name ? `${user.display_name} · ` : ''}{user.email}</p>
        </div>
        <button type="button" onClick={() => void logout()} className="rounded-full bg-bg px-5 py-2 text-sm font-medium">
          로그아웃
        </button>
      </div>

      <div className="border-t border-bg pt-4">
        {!confirming ? (
          <button type="button" onClick={() => setConfirming(true)} className="text-xs text-text-sub underline underline-offset-4">
            계정 삭제
          </button>
        ) : (
          <form onSubmit={handleDelete} className="flex flex-col gap-3">
            <p className="text-sm text-text-sub">
              계정과 모든 일정 기록, 설정이 영구히 삭제되고 되돌릴 수 없어요. 계속하려면 비밀번호를 입력해 주세요.
            </p>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="비밀번호"
              aria-label="계정 삭제 확인 비밀번호"
              autoComplete="current-password"
              className="max-w-xs rounded-2xl bg-bg px-4 py-2.5 text-sm outline-none ring-primary/40 focus:ring-2"
            />
            {error && (
              <p role="alert" className="text-xs font-medium text-primary-ink">
                {error}
              </p>
            )}
            <div className="flex gap-3">
              <button
                type="submit"
                disabled={busy || !password}
                className="rounded-full bg-primary px-5 py-2 text-sm font-semibold text-white disabled:opacity-50"
              >
                {busy ? '삭제 중…' : '영구 삭제'}
              </button>
              <button
                type="button"
                onClick={() => {
                  setConfirming(false);
                  setPassword('');
                  setError(null);
                }}
                className="text-sm text-text-sub"
              >
                취소
              </button>
            </div>
          </form>
        )}
      </div>
    </section>
  );
}
