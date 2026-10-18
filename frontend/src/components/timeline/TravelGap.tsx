import { Car } from 'lucide-react';

/** 블록 사이 이동 구간 라벨 ("🚗 25분") */
export default function TravelGap({ minutes }: { minutes: number }) {
  return (
    <span className="flex items-center gap-1 whitespace-nowrap rounded-full bg-white/80 px-2 py-0.5 text-[11px] font-medium text-text-sub">
      <Car size={12} />
      {minutes}분
    </span>
  );
}
