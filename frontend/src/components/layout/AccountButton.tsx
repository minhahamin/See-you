import { LogIn, LogOut } from 'lucide-react';
import { useState } from 'react';
import { useAuth } from '../../hooks/useAuth';

/** 사이드바 아래의 계정 버튼: 로그인하지 않았으면 로그인, 했으면 이니셜과 로그아웃 메뉴 */
export default function AccountButton() {
  const { user, ready, requestLogin, logout } = useAuth();
  const [open, setOpen] = useState(false);

  if (!ready) return <div className="size-11" aria-hidden />;

  if (!user) {
    return (
      <button
        type="button"
        title="로그인"
        aria-label="로그인"
        onClick={requestLogin}
        className="grid size-11 place-items-center rounded-full bg-surface text-text-sub shadow-soft transition-colors hover:text-primary"
      >
        <LogIn size={20} />
      </button>
    );
  }

  const initial = (user.display_name || user.email).trim().charAt(0).toUpperCase();
  return (
    <div className="relative">
      <button
        type="button"
        title={user.email}
        aria-label={`계정 메뉴 (${user.email})`}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="grid size-11 place-items-center rounded-full bg-primary text-sm font-bold text-white shadow-soft"
      >
        {initial}
      </button>
      {open && (
        <div className="absolute bottom-0 left-14 z-50 w-56 rounded-2xl bg-surface p-3 shadow-2xl">
          <p className="truncate px-2 text-sm font-semibold">{user.display_name || '내 계정'}</p>
          <p className="truncate px-2 pb-2 text-xs text-text-sub">{user.email}</p>
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              void logout();
            }}
            className="flex w-full items-center gap-2 rounded-xl px-2 py-2 text-sm text-text-sub hover:bg-bg hover:text-text-main"
          >
            <LogOut size={16} />
            로그아웃
          </button>
        </div>
      )}
    </div>
  );
}
