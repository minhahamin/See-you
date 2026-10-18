import { Database, HardDrive, LogIn } from 'lucide-react';
import { useEffect, useState } from 'react';
import { EMPTY_SETTINGS, loadSettings, saveSettings, type StorageSource } from '../api/settings';
import AccountCard from '../components/settings/AccountCard';
import ChipGroup from '../components/settings/ChipGroup';
import { useAuth } from '../hooks/useAuth';
import type { BudgetLevel, Companion, UserSettings } from '../types';

const COMPANIONS: { value: Companion; label: string }[] = (['혼자', '커플', '친구', '가족'] as const).map((c) => ({
  value: c,
  label: c,
}));

const PREFERENCES = ['자연·풍경', '맛집', '카페', '사진 명소', '체험·액티비티', '휴식·힐링', '실내 위주', '역사·문화'];

const BUDGETS: { value: BudgetLevel; label: string }[] = [
  { value: 1, label: '가성비' },
  { value: 2, label: '보통' },
  { value: 3, label: '여유롭게' },
];

type Status = 'loading' | 'idle' | 'saving' | 'saved' | 'error';

/** 설정: 동행·취향·예산 기본값. 로그인하면 계정(서버 DB)에 저장하고, 아니면 이 브라우저에 저장한다. 에이전트가 일정의 기본 조건으로 쓴다. */
export default function SettingsPage() {
  const { user, ready, requestLogin } = useAuth();
  const [draft, setDraft] = useState<UserSettings>(EMPTY_SETTINGS);
  const [source, setSource] = useState<StorageSource | null>(null);
  const [status, setStatus] = useState<Status>('loading');
  const [error, setError] = useState<string | null>(null);

  const userId = user?.id ?? null;
  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    setStatus('loading');
    loadSettings(userId !== null).then((result) => {
      if (cancelled) return;
      setDraft(result.settings);
      setSource(result.source);
      setStatus('idle');
    });
    return () => {
      cancelled = true;
    };
  }, [ready, userId]);

  const update = (patch: Partial<UserSettings>) => {
    setDraft((prev) => ({ ...prev, ...patch }));
    setStatus('idle');
  };

  const togglePreference = (p: string) =>
    update({
      preferences: draft.preferences.includes(p) ? draft.preferences.filter((x) => x !== p) : [...draft.preferences, p],
    });

  const handleSave = async () => {
    setStatus('saving');
    setError(null);
    try {
      const result = await saveSettings(draft, userId !== null);
      setSource(result.source);
      setStatus('saved');
    } catch (e) {
      setError(e instanceof Error ? e.message : '저장하지 못했어요.');
      setStatus('error');
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto">
      <header>
        <h1 className="text-2xl font-bold lg:text-3xl">설정</h1>
        <p className="mt-1 text-sm text-text-sub">
          여행 조건의 기본값입니다. 에이전트가 일정을 만들 때 이 값을 기본으로 쓰고, 대화에서 말한 조건이 우선합니다.
        </p>
      </header>

      <div className="flex max-w-2xl flex-col gap-7 rounded-3xl bg-surface p-6 shadow-soft lg:p-8">
        <ChipGroup
          label="동행"
          options={COMPANIONS}
          selected={draft.companion ? [draft.companion] : []}
          onToggle={(c) => update({ companion: draft.companion === c ? null : c })}
        />
        <ChipGroup
          label="취향"
          description="여러 개 고를 수 있어요."
          options={PREFERENCES.map((p) => ({ value: p, label: p }))}
          selected={draft.preferences}
          onToggle={togglePreference}
        />
        <ChipGroup
          label="예산"
          options={BUDGETS}
          selected={draft.budget ? [draft.budget] : []}
          onToggle={(b) => update({ budget: draft.budget === b ? null : b })}
        />

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-bg pt-5">
          <p className="flex items-center gap-2 text-xs text-text-sub">
            {source === 'server' ? <Database size={14} className="text-primary-ink" /> : <HardDrive size={14} />}
            {source === null && '저장 위치 확인 중…'}
            {source === 'server' && '내 계정(서버 DB)에 저장됩니다'}
            {source === 'local' && !user && '이 브라우저에만 저장됩니다'}
            {source === 'local' && user && '서버에서 설정을 읽지 못해 이 브라우저의 값을 보여 주고 있어요'}
          </p>
          <div className="flex items-center gap-3">
            {status === 'saved' && <span className="text-xs font-medium text-primary-ink">저장했어요</span>}
            {status === 'error' && (
              <span role="alert" className="text-xs font-medium text-primary-ink">
                {error}
              </span>
            )}
            <button
              type="button"
              onClick={handleSave}
              disabled={status === 'loading' || status === 'saving'}
              className="rounded-full bg-primary px-6 py-2.5 text-sm font-semibold text-white shadow-soft transition-opacity disabled:opacity-50"
            >
              {status === 'saving' ? '저장 중…' : '저장'}
            </button>
          </div>
        </div>

        {ready && !user && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-bg p-4 text-sm">
            <p className="text-text-sub">로그인하면 설정이 계정에 저장되어 다른 기기에서도 쓸 수 있어요.</p>
            <button type="button" onClick={requestLogin} className="flex items-center gap-2 font-semibold text-primary-ink">
              <LogIn size={14} />
              로그인
            </button>
          </div>
        )}
      </div>

      {user && <AccountCard />}
    </div>
  );
}
