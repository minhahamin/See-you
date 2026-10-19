import { GripVertical } from 'lucide-react';
import { useEffect } from 'react';
import { useCardDrag, VISIT_SLOT_ATTR, type CardDropTarget } from '../../hooks/useCardDrag';
import { CATEGORY_META } from '../../lib/category';
import type { Place, Visit } from '../../types';

interface Props {
  index: number;
  visit: Visit;
  place: Place;
  selected: boolean;
  /** 이 카드가 놓일 곳으로 지목됐는지 (다른 카드를 끌고 있을 때) */
  isDropTarget: boolean;
  onSelect: () => void;
  /** 끌어서 옮길 수 있을 때만 넘긴다 */
  onDrop?: (target: CardDropTarget) => void;
  /** 끌고 있는 동안 지금 가리키는 곳을 알려 준다 (일차 탭 강조에 쓴다) */
  onHover: (target: CardDropTarget | null) => void;
}

/** 모바일 세로 타임라인의 방문 카드. 오른쪽 손잡이를 끌어 순서·일차를 옮긴다 */
export default function MobileVisitCard({ index, visit, place, selected, isDropTarget, onSelect, onDrop, onHover }: Props) {
  const meta = CATEGORY_META[place.category];
  const Icon = meta.icon;
  const drag = useCardDrag(onDrop !== undefined, (target) => onDrop?.(target));

  useEffect(() => {
    onHover(drag.target);
  }, [drag.target]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div
      {...{ [VISIT_SLOT_ATTR]: index }}
      style={drag.offsetY !== null ? { translate: `0 ${drag.offsetY}px` } : undefined}
      className={`relative flex items-center rounded-full ${drag.dragging ? 'z-30 opacity-80 shadow-2xl' : ''} ${
        isDropTarget ? 'ring-2 ring-primary ring-offset-2' : ''
      }`}
    >
      <button
        type="button"
        onClick={onSelect}
        className={`flex min-w-0 flex-1 items-center gap-3 rounded-full py-1.5 pl-1.5 pr-4 text-left shadow-lg shadow-black/10 ${meta.bg} ${meta.fg} ${
          selected ? 'ring-2 ring-primary ring-offset-2' : ''
        }`}
      >
        <span className="grid size-11 shrink-0 place-items-center rounded-full bg-white/30">
          <Icon size={20} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-semibold">{place.name}</span>
          <span className="block text-xs opacity-80">
            {visit.start} – {visit.end}
          </span>
        </span>
        {visit.changed && <span className="rounded-full bg-changed px-2 py-0.5 text-[10px] font-bold text-white">수정됨</span>}
      </button>
      {onDrop && (
        <button
          type="button"
          aria-label={`${place.name} 옮기기`}
          {...drag.handlers}
          className={`absolute right-1.5 grid size-9 touch-none select-none place-items-center rounded-full bg-white/30 ${meta.fg} ${
            drag.dragging ? 'cursor-grabbing' : 'cursor-grab'
          }`}
        >
          <GripVertical size={18} />
        </button>
      )}
    </div>
  );
}
