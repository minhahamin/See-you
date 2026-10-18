import { DAY_END_MIN, DAY_START_MIN, PX_PER_HOUR, TRACK_WIDTH } from '../../lib/time';
import type { Itinerary, Place, Selection } from '../../types';
import DayRow, { ROW_HEADER_WIDTH } from './DayRow';

interface Props {
  itinerary: Itinerary;
  places: Record<string, Place>;
  selection: Selection;
  onSelect: (selection: Selection) => void;
}

const HOURS = Array.from(
  { length: (DAY_END_MIN - DAY_START_MIN) / 60 + 1 },
  (_, i) => DAY_START_MIN / 60 + i,
);

/** 행 = 여행 일차, 가로축 = 시간(08:00~22:00) */
export default function TimelineView({ itinerary, places, selection, onSelect }: Props) {
  return (
    <div className="min-h-0 flex-1 overflow-auto rounded-3xl">
      <div className="flex min-w-max flex-col gap-3 pb-3">
        <div className="sticky top-0 z-30 flex bg-bg">
          <div className="sticky left-0 z-40 shrink-0 bg-bg" style={{ width: ROW_HEADER_WIDTH }} />
          <div className="relative h-8 shrink-0" style={{ width: TRACK_WIDTH }}>
            {HOURS.map((h) => (
              <span
                key={h}
                className="absolute top-1 text-xs font-medium text-text-sub"
                style={{ left: (h - DAY_START_MIN / 60) * PX_PER_HOUR + 4 }}
              >
                {String(h).padStart(2, '0')}:00
              </span>
            ))}
          </div>
        </div>
        {itinerary.days.map((day) => (
          <DayRow key={day.day} day={day} places={places} selection={selection} onSelect={onSelect} />
        ))}
      </div>
    </div>
  );
}
