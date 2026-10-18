import type { Itinerary, Place } from '../types';

export interface TripStats {
  placeCount: number;
  totalTravelMin: number;
  avgTravelMin: number;
  indoorPercent: number;
  passed: number;
  total: number;
  passPercent: number;
}

/** 일정에서 요약 지표를 계산한다. 방문 장소 수와 실내 비율은 숙소를 제외한다. */
export function computeStats(itinerary: Itinerary, places: Record<string, Place>): TripStats {
  const visits = itinerary.days.flatMap((d) => d.visits);
  const spots = visits.filter((v) => places[v.place_id]?.category !== 'stay');
  const indoor = spots.filter((v) => places[v.place_id]?.indoor).length;
  const totalTravelMin = visits.reduce((sum, v) => sum + v.travel_minutes_from_prev, 0);
  const { passed, total } = itinerary.validation;

  return {
    placeCount: spots.length,
    totalTravelMin,
    avgTravelMin: itinerary.days.length ? Math.round(totalTravelMin / itinerary.days.length) : 0,
    indoorPercent: spots.length ? Math.round((indoor / spots.length) * 100) : 0,
    passed,
    total,
    passPercent: total ? Math.round((passed / total) * 100) : 0,
  };
}
