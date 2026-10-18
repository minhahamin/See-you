import { Check, Star } from 'lucide-react';
import { useEffect, useState } from 'react';
import { CATEGORY_META } from '../lib/category';
import type { Place, Review, Visit } from '../types';

interface Props {
  visit: Visit;
  place: Place;
  /** 이 방문의 근거 후기 */
  reviews: Review[];
}

type Checked = Record<string, boolean>;

/** 체크 상태는 localStorage에만 저장한다 (장소별) */
function useChecklist(placeId: string): [Checked, (item: string) => void] {
  const key = `checklist:${placeId}`;
  const [checked, setChecked] = useState<Checked>({});

  useEffect(() => {
    try {
      const raw = localStorage.getItem(key);
      setChecked(raw ? (JSON.parse(raw) as Checked) : {});
    } catch {
      setChecked({});
    }
  }, [key]);

  const toggle = (item: string) =>
    setChecked((prev) => {
      const next = { ...prev, [item]: !prev[item] };
      try {
        localStorage.setItem(key, JSON.stringify(next));
      } catch {
        // 저장소를 못 쓰는 환경에서는 화면 상태로만 유지한다
      }
      return next;
    });

  return [checked, toggle];
}

/** 선택한 장소의 상세: 방문 시간, 추천 이유, 근거 후기, 태그, 체크리스트 */
export default function PlaceDetail({ visit, place, reviews }: Props) {
  const meta = CATEGORY_META[place.category];
  const [checked, toggle] = useChecklist(place.id);

  return (
    <section className="flex min-h-[300px] flex-1 flex-col gap-5 overflow-y-auto rounded-3xl bg-surface p-6 shadow-soft">
      <div className="flex items-center gap-4">
        <span className="text-4xl font-bold tracking-tight">{visit.start}</span>
        <span className={`h-10 w-1 rounded-full ${meta.bg}`} />
        <div className="min-w-0">
          <p className="text-xs text-text-sub">{meta.label}</p>
          <h2 className="truncate text-base font-bold">{place.name}</h2>
        </div>
      </div>

      <div>
        <h3 className="mb-1.5 text-sm font-semibold">추천 이유</h3>
        <p className="text-sm leading-relaxed text-text-main/80">{visit.reason}</p>
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold">근거 후기</h3>
        <ul className="flex flex-col gap-2">
          {reviews.slice(0, 3).map((review) => (
            <li key={review.review_id} className="rounded-2xl bg-bg/70 p-3">
              <div className="mb-1 flex items-center justify-between text-xs text-text-sub">
                <span>
                  {review.author_type} · {review.season}
                </span>
                <span className="flex items-center gap-0.5 font-medium text-text-main">
                  <Star size={12} className="fill-cat-cafe text-cat-cafe" />
                  {review.rating}
                </span>
              </div>
              <p className="line-clamp-2 text-sm">{review.text}</p>
            </li>
          ))}
        </ul>
        <p className="mt-2 text-[11px] text-text-sub">후기는 합성 데이터입니다.</p>
      </div>

      {place.tags.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {place.tags.map((tag) => (
            <li key={tag} className="rounded-full bg-primary/15 px-3 py-1 text-xs font-medium text-primary-ink">
              {tag}
            </li>
          ))}
        </ul>
      )}

      {place.checklist.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-semibold">체크리스트</h3>
          <ul className="flex flex-col gap-2">
            {place.checklist.map((item) => {
              const done = !!checked[item];
              return (
                <li key={item}>
                  <button
                    type="button"
                    role="checkbox"
                    aria-checked={done}
                    onClick={() => toggle(item)}
                    className={`flex w-full items-center justify-between rounded-xl px-4 py-2.5 text-left text-sm transition-colors ${
                      done ? 'bg-primary/10 font-medium' : 'bg-bg/70'
                    }`}
                  >
                    {item}
                    <span
                      className={`grid size-5 place-items-center rounded-full border ${
                        done ? 'border-primary bg-primary text-white' : 'border-text-sub/40'
                      }`}
                    >
                      {done && <Check size={12} />}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </section>
  );
}
