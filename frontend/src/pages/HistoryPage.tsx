import { LogIn, Plus, Trash2 } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { deleteSession, listSessions } from '../api/history';
import { useAuth } from '../hooks/useAuth';
import type { ChatSession } from '../hooks/useChatSession';
import { formatUpdatedAt, sessionSubtitle } from '../lib/history';
import type { SessionListItem } from '../types';

interface Props {
  chat: ChatSession;
  /** 대화를 열었거나 새로 시작한 뒤 플래너 화면으로 이동한다 */
  onOpened: () => void;
}

/** 내 일정(대화) 기록: 목록, 다시 열기, 삭제, 새 일정 시작. 로그인한 사용자만 쓸 수 있다. */
export default function HistoryPage({ chat, onOpened }: Props) {
  const { user, ready, requestLogin } = useAuth();
  const [items, setItems] = useState<SessionListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);

  const reload = useCallback(() => {
    setError(null);
    listSessions()
      .then(setItems)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '기록을 불러오지 못했어요.'));
  }, []);

  useEffect(() => {
    setItems(null);
    if (user) reload();
  }, [user, reload]);

  const handleOpen = async (id: string) => {
    if (await chat.openSession(id)) onOpened();
    else setError('이 일정을 열지 못했어요. 이미 삭제됐거나 진행 중인 작업이 있을 수 있어요.');
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteSession(id);
      if (chat.sessionId === id) chat.newSession();
      setConfirmId(null);
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : '삭제하지 못했어요.');
    }
  };

  return (
    // 스크롤 영역은 넘치는 부분을 가로로도 잘라 내므로, 선택 테두리(ring)와 그림자가 잘리지 않게 안쪽 여백을 두고 같은 만큼 바깥으로 넓힌다
    <div className="-mx-3 -mb-3 flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-3 pb-3">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold lg:text-3xl">내 일정</h1>
          <p className="mt-1 text-sm text-text-sub">지난 대화와 만든 일정을 다시 열어 이어서 고칠 수 있어요.</p>
        </div>
        <button
          type="button"
          onClick={() => {
            chat.newSession();
            onOpened();
          }}
          disabled={chat.running}
          className="flex items-center gap-2 rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-white shadow-soft disabled:opacity-50"
        >
          <Plus size={16} />새 일정
        </button>
      </header>

      {!ready ? (
        <p className="rounded-3xl bg-surface p-8 text-center text-sm text-text-sub shadow-soft">불러오는 중…</p>
      ) : !user ? (
        <div className="grid place-items-center gap-4 rounded-3xl bg-surface p-10 text-center shadow-soft">
          <p className="font-semibold">로그인하면 일정 기록이 계정에 저장돼요</p>
          <p className="max-w-sm text-sm text-text-sub">
            로그인하지 않아도 일정을 만들 수 있지만, 기록은 저장되지 않아요. 지금 하던 대화는 로그인하면 계정으로 옮겨져요.
          </p>
          <button
            type="button"
            onClick={requestLogin}
            className="flex items-center gap-2 rounded-full bg-primary px-6 py-2.5 text-sm font-semibold text-white shadow-soft"
          >
            <LogIn size={16} />
            로그인 / 회원가입
          </button>
        </div>
      ) : (
        <>
          {error && (
            <p role="alert" className="rounded-2xl bg-surface px-4 py-2 text-sm text-primary-ink shadow-soft">
              {error}
            </p>
          )}
          {items === null && !error && (
            <p className="rounded-3xl bg-surface p-8 text-center text-sm text-text-sub shadow-soft">기록을 불러오는 중…</p>
          )}
          {items?.length === 0 && (
            <p className="rounded-3xl bg-surface p-10 text-center text-sm text-text-sub shadow-soft">
              아직 저장된 일정이 없어요. 플래너에서 여행 조건을 말해 보세요.
            </p>
          )}
          <ul className="grid gap-3 lg:grid-cols-2">
            {items?.map((item) => (
              <li
                key={item.session_id}
                className={`flex items-center gap-3 rounded-3xl bg-surface p-5 shadow-soft ${
                  chat.sessionId === item.session_id ? 'ring-2 ring-primary/50' : ''
                }`}
              >
                <button type="button" onClick={() => handleOpen(item.session_id)} className="min-w-0 flex-1 text-left">
                  <p className="truncate font-semibold">{item.title ?? '제목 없는 대화'}</p>
                  <p className="mt-1 text-xs text-text-sub">
                    {sessionSubtitle(item)} · {formatUpdatedAt(item.updated_at)}
                  </p>
                </button>
                {confirmId === item.session_id ? (
                  <span className="flex shrink-0 items-center gap-2 text-xs">
                    <button type="button" onClick={() => handleDelete(item.session_id)} className="font-semibold text-primary-ink">
                      삭제
                    </button>
                    <button type="button" onClick={() => setConfirmId(null)} className="text-text-sub">
                      취소
                    </button>
                  </span>
                ) : (
                  <button
                    type="button"
                    aria-label={`${item.title ?? '대화'} 삭제`}
                    onClick={() => setConfirmId(item.session_id)}
                    className="grid size-9 shrink-0 place-items-center rounded-full text-text-sub hover:bg-bg hover:text-primary-ink"
                  >
                    <Trash2 size={16} />
                  </button>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
