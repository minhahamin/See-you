import { Fragment, useState } from 'react';
import { DAY_TAB_ATTR, type CardDropTarget } from '../../hooks/useCardDrag';
import { startAtDayEnd, startForVisitSlot, type MoveRequest } from '../../lib/dragMove';
import { formatDate, toMinutes } from '../../lib/time';
import { WEATHER_META } from '../../lib/weather';
import type { Itinerary, Place, Selection } from '../../types';
import MobileVisitCard from './MobileVisitCard';
import TravelGap from './TravelGap';

interface Props {
  itinerary: Itinerary;
  places: Record<string, Place>;
  selection: Selection;
  onSelect: (selection: Selection) => void;
  /** 끌어서 옮길 수 있을 때만 넘긴다 */
  onMove?: (move: MoveRequest) => void;
}

/** 모바일: 일차 탭 + 하루 세로 타임라인 */
export default function MobileTimeline({ itinerary, places, selection, onSelect, onMove }: Props) {
  const [dayNo, setDayNo] = useState(selection.day);
  const day = itinerary.days.find((d) => d.day === dayNo) ?? itinerary.days[0];
  const [hover, setHover] = useState<CardDropTarget | null>(null);
  const forecast = day.weather;

  // 카드를 같은 날의 다른 방문 자리나 다른 일차 탭에 놓으면 이동 요청을 보낸다
  const handleDrop = (fromIndex: number, target: CardDropTarget) => {
    const moved = day.visits[fromIndex];
    if (!onMove || !moved) return;
    if (target.kind === 'visit') {
      const startMin = startForVisitSlot(day.visits, fromIndex, target.index);
      if (startMin !== null) onMove({ fromDay: day.day, fromIndex, day: day.day, startMin });
      return;
    }
    const other = itinerary.days.find((d) => d.day === target.day);
    if (!other || other.day === day.day) return;
    const duration = toMinutes(moved.end) - toMinutes(moved.start);
    onMove({ fromDay: day.day, fromIndex, day: other.day, startMin: startAtDayEnd(other.visits, duration) });
  };
  const weather = forecast ? WEATHER_META[forecast.condition] : null;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex gap-2 overflow-x-auto" role="tablist" aria-label="일차">
        {itinerary.days.map((d) => (
          <button
            key={d.day}
            type="button"
            role="tab"
            aria-selected={d.day === day.day}
            {...(onMove ? { [DAY_TAB_ATTR]: d.day } : {})}
            onClick={() => setDayNo(d.day)}
            className={`shrink-0 rounded-full px-4 py-2 text-sm font-semibold ${
              d.day === day.day ? 'bg-primary text-white shadow-soft' : 'bg-surface text-text-sub'
            } ${hover?.kind === 'day' && hover.day === d.day ? 'ring-2 ring-primary ring-offset-2' : ''}`}
          >
            {d.day}일차
          </button>
        ))}
      </div>

      <div
        className={`flex flex-col gap-2 rounded-3xl p-4 ${forecast?.condition === 'rain' ? 'bg-rain' : 'bg-surface'}`}
      >
        <p className="flex items-center gap-2 text-sm text-text-sub">
          {formatDate(day.date)}
          <span className="flex items-center gap-1 font-medium text-text-main">
            {forecast && weather ? (
              <>
                <weather.icon size={14} className={weather.color} />
                {forecast.temp_max}° / {forecast.temp_min}°
              </>
            ) : (
              <span className="text-text-sub">날씨 정보 없음</span>
            )}
          </span>
        </p>

        {day.visits.map((visit, i) => {
          const place = places[visit.place_id];
          if (!place) return null;
          return (
            <Fragment key={`${visit.place_id}-${visit.start}`}>
              {i > 0 && (
                <div className="flex justify-center">
                  <TravelGap minutes={visit.travel_minutes_from_prev} />
                </div>
              )}
              <MobileVisitCard
                index={i}
                visit={visit}
                place={place}
                selected={selection.day === day.day && selection.index === i}
                isDropTarget={hover?.kind === 'visit' && hover.index === i}
                onSelect={() => onSelect({ day: day.day, index: i })}
                onDrop={onMove ? (target) => handleDrop(i, target) : undefined}
                onHover={setHover}
              />
            </Fragment>
          );
        })}
      </div>
    </div>
  );
}
