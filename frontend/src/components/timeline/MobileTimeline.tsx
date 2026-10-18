import { Fragment, useState } from 'react';
import { CATEGORY_META } from '../../lib/category';
import { formatDate } from '../../lib/time';
import { WEATHER_META } from '../../lib/weather';
import type { Itinerary, Place, Selection } from '../../types';
import TravelGap from './TravelGap';

interface Props {
  itinerary: Itinerary;
  places: Record<string, Place>;
  selection: Selection;
  onSelect: (selection: Selection) => void;
}

/** 모바일: 일차 탭 + 하루 세로 타임라인 */
export default function MobileTimeline({ itinerary, places, selection, onSelect }: Props) {
  const [dayNo, setDayNo] = useState(selection.day);
  const day = itinerary.days.find((d) => d.day === dayNo) ?? itinerary.days[0];
  const weather = WEATHER_META[day.weather.condition];
  const WeatherIcon = weather.icon;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex gap-2 overflow-x-auto" role="tablist" aria-label="일차">
        {itinerary.days.map((d) => (
          <button
            key={d.day}
            type="button"
            role="tab"
            aria-selected={d.day === day.day}
            onClick={() => setDayNo(d.day)}
            className={`shrink-0 rounded-full px-4 py-2 text-sm font-semibold ${
              d.day === day.day ? 'bg-primary text-white shadow-soft' : 'bg-surface text-text-sub'
            }`}
          >
            {d.day}일차
          </button>
        ))}
      </div>

      <div
        className={`flex flex-col gap-2 rounded-3xl p-4 ${day.weather.condition === 'rain' ? 'bg-rain' : 'bg-surface'}`}
      >
        <p className="flex items-center gap-2 text-sm text-text-sub">
          {formatDate(day.date)}
          <span className="flex items-center gap-1 font-medium text-text-main">
            <WeatherIcon size={14} className={weather.color} />
            {day.weather.temp_max}° / {day.weather.temp_min}°
          </span>
        </p>

        {day.visits.map((visit, i) => {
          const place = places[visit.place_id];
          if (!place) return null;
          const meta = CATEGORY_META[place.category];
          const Icon = meta.icon;
          const selected = selection.day === day.day && selection.index === i;
          return (
            <Fragment key={`${visit.place_id}-${visit.start}`}>
              {i > 0 && (
                <div className="flex justify-center">
                  <TravelGap minutes={visit.travel_minutes_from_prev} />
                </div>
              )}
              <button
                type="button"
                onClick={() => onSelect({ day: day.day, index: i })}
                className={`flex items-center gap-3 rounded-full py-1.5 pl-1.5 pr-4 text-left shadow-lg shadow-black/10 ${meta.bg} ${meta.fg} ${
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
                {visit.changed && (
                  <span className="rounded-full bg-changed px-2 py-0.5 text-[10px] font-bold text-white">수정됨</span>
                )}
              </button>
            </Fragment>
          );
        })}
      </div>
    </div>
  );
}
