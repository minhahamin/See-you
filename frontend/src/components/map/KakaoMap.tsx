import { useEffect, useRef, useState } from 'react';
import { loadKakaoMaps } from '../../lib/kakaoMap';
import type { Itinerary, Place, Selection } from '../../types';
import { createMarkerElement } from './markerElement';

/** 일차별 마커·동선 색 (일차 수가 더 많으면 반복) */
export const DAY_COLORS = ['#EE7BA6', '#4FA3F7', '#22C55E', '#8B5CF6', '#FF8A4C'];
const dayColor = (dayIndex: number): string => DAY_COLORS[dayIndex % DAY_COLORS.length];

// 장소가 하나도 없을 때의 초기 중심 (제주)
const FALLBACK_CENTER = { lat: 33.38, lng: 126.55 };
const FALLBACK_LEVEL = 10;
const FIT_PADDING = 70;

type Status = 'loading' | 'ready' | 'error';

const legendClass = (on: boolean): string =>
  `flex items-center gap-2 rounded-xl px-3 py-1.5 font-medium transition-colors ${
    on ? 'bg-primary/15 text-primary-ink' : 'text-text-main/70 hover:bg-bg'
  }`;

interface Props {
  appKey: string;
  itinerary: Itinerary;
  places: Record<string, Place>;
  selection: Selection;
  onSelect: (selection: Selection) => void;
}

/** 일차별 번호 마커와 동선을 그리는 카카오맵. 선택 상태는 타임라인과 공유한다. */
export default function KakaoMap({ appKey, itinerary, places, selection, onSelect }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<kakao.maps.Map | null>(null);
  const [status, setStatus] = useState<Status>('loading');
  // 하나만 고르면 그날의 마커·동선만 보여준다 (null = 전체). 겹친 마커를 누르기 쉽게 하기 위함.
  const [activeDay, setActiveDay] = useState<number | null>(null);

  // SDK 로딩 + 지도 생성
  useEffect(() => {
    let cancelled = false;
    loadKakaoMaps(appKey)
      .then(() => {
        if (cancelled || !containerRef.current) return;
        mapRef.current = new kakao.maps.Map(containerRef.current, {
          center: new kakao.maps.LatLng(FALLBACK_CENTER.lat, FALLBACK_CENTER.lng),
          level: FALLBACK_LEVEL,
        });
        setStatus('ready');
      })
      .catch(() => {
        if (!cancelled) setStatus('error');
      });
    return () => {
      cancelled = true;
      mapRef.current = null;
    };
  }, [appKey]);

  // 보이는 장소가 모두 들어오도록 범위 맞춤 (선택이 바뀔 때마다 움직이지 않도록 일정·일차 필터가 바뀔 때만)
  useEffect(() => {
    const map = mapRef.current;
    if (status !== 'ready' || !map) return;
    const bounds = new kakao.maps.LatLngBounds();
    let count = 0;
    itinerary.days.forEach((day) => {
      if (activeDay !== null && day.day !== activeDay) return;
      day.visits.forEach((visit) => {
        const place = places[visit.place_id];
        if (!place) return;
        bounds.extend(new kakao.maps.LatLng(place.lat, place.lng));
        count += 1;
      });
    });
    if (count > 0) map.setBounds(bounds, FIT_PADDING, FIT_PADDING, FIT_PADDING, FIT_PADDING);
  }, [status, itinerary, places, activeDay]);

  // 마커·동선 그리기
  useEffect(() => {
    const map = mapRef.current;
    if (status !== 'ready' || !map) return;
    const overlays: kakao.maps.CustomOverlay[] = [];
    const lines: kakao.maps.Polyline[] = [];

    itinerary.days.forEach((day, dayIndex) => {
      if (activeDay !== null && day.day !== activeDay) return;
      const color = dayColor(dayIndex);
      const path: kakao.maps.LatLng[] = [];

      day.visits.forEach((visit, index) => {
        const place = places[visit.place_id];
        if (!place) return;
        const position = new kakao.maps.LatLng(place.lat, place.lng);
        path.push(position);
        const selected = selection.day === day.day && selection.index === index;
        overlays.push(
          new kakao.maps.CustomOverlay({
            map,
            position,
            content: createMarkerElement({
              number: index + 1,
              color,
              title: place.name,
              label: selected ? place.name : null,
              selected,
              onClick: () => onSelect({ day: day.day, index }),
            }),
            xAnchor: 0.5,
            yAnchor: 0.5,
            zIndex: selected ? 10 : 1,
            clickable: true,
          }),
        );
      });

      if (path.length > 1) {
        const line = new kakao.maps.Polyline({
          path,
          strokeWeight: 4,
          strokeColor: color,
          strokeOpacity: 0.7,
          strokeStyle: 'solid',
        });
        line.setMap(map);
        lines.push(line);
      }
    });

    return () => {
      overlays.forEach((o) => o.setMap(null));
      lines.forEach((l) => l.setMap(null));
    };
  }, [status, itinerary, places, selection, onSelect, activeDay]);

  return (
    <div className="relative min-h-[320px] flex-1 overflow-hidden rounded-3xl bg-surface shadow-soft">
      <div ref={containerRef} className="absolute inset-0" />

      {status === 'ready' && (
        <div
          role="group"
          aria-label="일차 필터"
          className="absolute left-4 top-4 z-10 flex flex-col gap-0.5 rounded-2xl bg-white/90 p-1.5 text-xs shadow-soft"
        >
          <button type="button" aria-pressed={activeDay === null} onClick={() => setActiveDay(null)} className={legendClass(activeDay === null)}>
            전체
          </button>
          {itinerary.days.map((day, i) => (
            <button
              key={day.day}
              type="button"
              aria-pressed={activeDay === day.day}
              onClick={() => setActiveDay(day.day)}
              className={legendClass(activeDay === day.day)}
            >
              <span className="size-3 rounded-full" style={{ backgroundColor: dayColor(i) }} />
              {day.day}일차
            </button>
          ))}
        </div>
      )}

      {status !== 'ready' && (
        <div className="absolute inset-0 z-10 grid place-items-center bg-surface p-8 text-center">
          {status === 'loading' ? (
            <p className="text-sm text-text-sub">지도를 불러오는 중…</p>
          ) : (
            <div>
              <p className="font-semibold">지도를 불러오지 못했어요</p>
              <p className="mt-1 text-sm text-text-sub">
                JavaScript 키가 맞는지, 카카오 디벨로퍼스에 이 주소가 웹 도메인으로 등록돼 있는지 확인해 주세요.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
