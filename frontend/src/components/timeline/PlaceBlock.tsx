import { ArrowRight } from 'lucide-react';
import { useEffect, useState } from 'react';
import { CATEGORY_META } from '../../lib/category';
import { minutesToPx, toMinutes } from '../../lib/time';
import type { Place, Visit } from '../../types';

interface Props {
  visit: Visit;
  place: Place;
  selected: boolean;
  onClick: () => void;
}

const CHANGED_BADGE_MS = 3000;
/** 이 너비보다 좁으면 오른쪽 화살표 버튼을 숨겨 이름이 보이게 한다 */
const ARROW_MIN_WIDTH = 160;

/** 타임라인의 알약 모양 방문 블록. 길이 = 머무는 시간, 색 = 카테고리 */
export default function PlaceBlock({ visit, place, selected, onClick }: Props) {
  const meta = CATEGORY_META[place.category];
  const Icon = meta.icon;
  const left = minutesToPx(toMinutes(visit.start));
  const width = minutesToPx(toMinutes(visit.end)) - left;

  // 피드백으로 바뀐 블록은 3초간 강조한다
  const [showChanged, setShowChanged] = useState(visit.changed);
  useEffect(() => {
    if (!visit.changed) return;
    setShowChanged(true);
    const timer = setTimeout(() => setShowChanged(false), CHANGED_BADGE_MS);
    return () => clearTimeout(timer);
  }, [visit.changed]);

  const ring = showChanged
    ? 'ring-2 ring-changed ring-offset-2'
    : selected
      ? 'ring-2 ring-primary ring-offset-2'
      : '';

  return (
    <div className="absolute top-1/2 -translate-y-1/2" style={{ left, width }}>
      <button
        type="button"
        title={`${place.name} · ${visit.start}–${visit.end}`}
        aria-pressed={selected}
        onClick={onClick}
        className={`flex h-14 w-full items-center gap-2 rounded-full pl-1.5 pr-1.5 shadow-lg shadow-black/10 transition-transform hover:-translate-y-0.5 ${meta.bg} ${meta.fg} ${ring}`}
      >
        <span className="grid size-11 shrink-0 place-items-center overflow-hidden rounded-full bg-white/30">
          {place.thumbnail_url ? (
            <img src={place.thumbnail_url} alt="" className="size-full object-cover" />
          ) : (
            <Icon size={20} />
          )}
        </span>
        <span className="min-w-0 flex-1 truncate text-left text-sm font-semibold">{place.name}</span>
        {width >= ARROW_MIN_WIDTH && (
          <span className="grid size-8 shrink-0 place-items-center rounded-full bg-white/30">
            <ArrowRight size={14} />
          </span>
        )}
      </button>
      {showChanged && (
        <span className="absolute -top-2.5 right-3 rounded-full bg-changed px-2 py-0.5 text-[10px] font-bold text-white shadow">
          수정됨
        </span>
      )}
    </div>
  );
}
