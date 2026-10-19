import { DAY_TRACK_ATTR } from '../../hooks/useBlockDrag';
import type { MoveRequest } from '../../lib/dragMove';
import { WEATHER_META } from '../../lib/weather';
import { formatDate, minutesToPx, PX_PER_HOUR, toMinutes, TRACK_WIDTH } from '../../lib/time';
import type { DayPlan, Place, Selection } from '../../types';
import PlaceBlock from './PlaceBlock';
import TravelGap from './TravelGap';

export const ROW_HEADER_WIDTH = 168;

// 30분 단위 연한 세로선
const GRID_STYLE = {
  width: TRACK_WIDTH,
  backgroundImage: `repeating-linear-gradient(to right, rgba(238,123,166,0.14) 0, rgba(238,123,166,0.14) 1px, transparent 1px, transparent ${PX_PER_HOUR / 2}px)`,
};

interface Props {
  day: DayPlan;
  places: Record<string, Place>;
  selection: Selection;
  onSelect: (selection: Selection) => void;
  /** 없으면 끌어서 옮길 수 없다 */
  onMove?: (move: MoveRequest) => void;
}

/** 타임라인의 한 행 = 여행 하루 */
export default function DayRow({ day, places, selection, onSelect, onMove }: Props) {
  const forecast = day.weather;
  const weather = forecast ? WEATHER_META[forecast.condition] : null;
  const rainy = forecast?.condition === 'rain';

  return (
    <div className={`flex rounded-3xl ${rainy ? 'bg-rain' : 'bg-row'}`}>
      <div
        className="sticky left-0 z-20 flex shrink-0 flex-col justify-center gap-1 rounded-l-3xl bg-inherit px-5"
        style={{ width: ROW_HEADER_WIDTH }}
      >
        <span className="text-lg font-bold">{day.day}일차</span>
        <span className="text-xs text-text-sub">{formatDate(day.date)}</span>
        <span className="flex items-center gap-1.5 text-xs font-medium">
          {forecast && weather ? (
            <>
              <weather.icon size={14} className={weather.color} aria-label={weather.label} />
              {forecast.temp_max}° / {forecast.temp_min}°
            </>
          ) : (
            <span className="text-text-sub">날씨 정보 없음</span>
          )}
        </span>
      </div>

      <div className="relative h-28 shrink-0" style={GRID_STYLE} {...{ [DAY_TRACK_ATTR]: day.day }}>
        {day.visits.map((visit, i) => {
          const place = places[visit.place_id];
          if (!place) return null;
          const prev = day.visits[i - 1];
          const gapLeft = prev ? minutesToPx(toMinutes(prev.end)) : 0;
          const gapWidth = prev ? minutesToPx(toMinutes(visit.start)) - gapLeft : 0;

          return (
            <div key={`${visit.place_id}-${visit.start}`}>
              {prev && gapWidth > 0 && (
                <div
                  className="absolute top-1/2 flex -translate-y-1/2 justify-center"
                  style={{ left: gapLeft, width: gapWidth }}
                >
                  <TravelGap minutes={visit.travel_minutes_from_prev} />
                </div>
              )}
              <PlaceBlock
                visit={visit}
                place={place}
                selected={selection.day === day.day && selection.index === i}
                onClick={() => onSelect({ day: day.day, index: i })}
                onDrop={onMove && ((target) => onMove({ ...target, fromDay: day.day, fromIndex: i }))}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}
