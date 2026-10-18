import { CalendarDays, Download, MessageCircle, Plus, Users } from 'lucide-react';
import { formatDate } from '../../lib/time';
import type { Itinerary } from '../../types';

export type ViewMode = 'timeline' | 'map';

interface Props {
  /** 아직 일정이 없으면 null */
  itinerary: Itinerary | null;
  view: ViewMode;
  onViewChange: (view: ViewMode) => void;
  chatOpen: boolean;
  chatRunning: boolean;
  onChatToggle: () => void;
  /** 타임라인을 이미지로 저장 */
  onExport: () => void;
  /** 새 일정을 시작한다 (지금 대화는 로그인했다면 기록에 남는다) */
  onNew: () => void;
  exporting: boolean;
}

const VIEWS: { key: ViewMode; label: string }[] = [
  { key: 'timeline', label: '타임라인' },
  { key: 'map', label: '지도' },
];

const PILL = 'flex items-center gap-2 rounded-full bg-surface px-4 py-2 text-sm font-medium shadow-soft disabled:opacity-60';

/** 여행 제목 · 날짜 · 동행 · [타임라인|지도] 토글 · 대화 열기 */
export default function TopBar({
  itinerary,
  view,
  onViewChange,
  chatOpen,
  chatRunning,
  onChatToggle,
  onExport,
  onNew,
  exporting,
}: Props) {
  const first = itinerary?.days[0];
  const last = itinerary?.days[itinerary.days.length - 1];

  return (
    <header className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold lg:text-3xl">{itinerary?.title ?? '새 여행 일정'}</h1>
        <p className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-text-sub">
          {itinerary && first && last ? (
            <>
              <span className="flex items-center gap-1.5">
                <CalendarDays size={14} />
                {formatDate(first.date)} – {formatDate(last.date)}
              </span>
              <span className="flex items-center gap-1.5">
                <Users size={14} />
                {itinerary.companions}
              </span>
            </>
          ) : (
            <span>여행 조건을 말하면 일정을 만들어 드려요</span>
          )}
        </p>
      </div>

      <div className="flex items-center gap-3">
        <button type="button" onClick={onChatToggle} aria-pressed={chatOpen} className={`relative ${PILL}`}>
          <MessageCircle size={16} className="text-primary" />
          대화
          {chatRunning && <span className="absolute -right-0.5 -top-0.5 size-2.5 animate-pulse rounded-full bg-primary" />}
        </button>
        {itinerary && (
          <>
            <button type="button" onClick={onNew} disabled={chatRunning} aria-label="새 일정 시작" title="새 일정 시작" className={PILL}>
              <Plus size={16} className="text-primary" />
              <span className="hidden sm:inline">새 일정</span>
            </button>
            <button
              type="button"
              onClick={onExport}
              disabled={exporting}
              aria-label="타임라인을 이미지로 저장"
              title="타임라인을 이미지로 저장"
              className={PILL}
            >
              <Download size={16} className="text-primary" />
              <span className="hidden sm:inline">{exporting ? '저장 중…' : '이미지 저장'}</span>
            </button>
            <div className="flex rounded-full bg-surface p-1 shadow-soft" role="tablist" aria-label="보기 방식">
              {VIEWS.map(({ key, label }) => (
                <button
                  key={key}
                  type="button"
                  role="tab"
                  aria-selected={view === key}
                  onClick={() => onViewChange(key)}
                  className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
                    view === key ? 'bg-primary text-white' : 'text-text-sub hover:text-text-main'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    </header>
  );
}
