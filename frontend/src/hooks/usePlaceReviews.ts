import { useEffect, useState } from 'react';
import { getPlaceDetail } from '../api/sessions';
import { mockReviews } from '../mocks';
import type { PlaceDetail, Review, Visit } from '../types';

// 같은 장소를 다시 선택해도 다시 요청하지 않는다. 실패한 요청은 캐시에서 빼서 다음에 다시 시도한다.
const detailCache = new Map<string, Promise<PlaceDetail>>();

function loadDetail(placeId: string): Promise<PlaceDetail> {
  let pending = detailCache.get(placeId);
  if (!pending) {
    pending = getPlaceDetail(placeId);
    detailCache.set(placeId, pending);
    pending.catch(() => detailCache.delete(placeId));
  }
  return pending;
}

/** 방문의 근거 후기만 골라낸다 */
export function pickEvidence(reviews: Review[], evidenceIds: string[]): Review[] {
  const wanted = new Set(evidenceIds);
  return reviews.filter((r) => wanted.has(r.review_id));
}

/** 선택한 방문의 근거 후기. 예시 일정은 더미에서, 실제 일정은 GET /api/places/{id}로 가져온다. */
export function usePlaceReviews(visit: Visit | undefined, isDemo: boolean): Review[] {
  const [reviews, setReviews] = useState<Review[]>([]);
  const placeId = visit?.place_id;
  const evidenceKey = visit?.evidence_review_ids.join(',') ?? '';

  useEffect(() => {
    if (!placeId) {
      setReviews([]);
      return;
    }
    const ids = evidenceKey ? evidenceKey.split(',') : [];
    if (isDemo) {
      setReviews(ids.flatMap((id) => (mockReviews[id] ? [mockReviews[id]] : [])));
      return;
    }
    let cancelled = false;
    setReviews([]);
    loadDetail(placeId)
      .then((detail) => {
        if (!cancelled) setReviews(pickEvidence(detail.reviews, ids));
      })
      .catch(() => {
        if (!cancelled) setReviews([]); // 후기를 못 가져와도 일정 화면은 그대로 쓸 수 있다
      });
    return () => {
      cancelled = true;
    };
  }, [placeId, evidenceKey, isDemo]);

  return reviews;
}
