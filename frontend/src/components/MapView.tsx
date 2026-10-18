import { Map } from 'lucide-react';
import type { Itinerary, Place, Selection } from '../types';
import KakaoMap from './map/KakaoMap';

interface Props {
  itinerary: Itinerary;
  places: Record<string, Place>;
  selection: Selection;
  onSelect: (selection: Selection) => void;
}

const APP_KEY = (import.meta.env.VITE_KAKAO_MAP_KEY ?? '').trim();

/** 카카오맵 + 동선 표시. 키가 없으면 설정 방법을 안내한다. */
export default function MapView(props: Props) {
  if (!APP_KEY) {
    return (
      <div className="grid min-h-[320px] flex-1 place-items-center rounded-3xl bg-surface p-8 text-center shadow-soft">
        <div className="max-w-md">
          <Map size={32} className="mx-auto text-primary" />
          <p className="mt-3 font-semibold">카카오맵 키가 필요해요</p>
          <ol className="mt-3 list-decimal space-y-1 pl-5 text-left text-sm text-text-sub">
            <li>카카오 디벨로퍼스에서 JavaScript 키를 발급받습니다.</li>
            <li>앱의 플랫폼(Web) 설정에 http://localhost:5173 을 등록합니다.</li>
            <li>프로젝트 루트 .env에 VITE_KAKAO_MAP_KEY=키 를 넣고 개발 서버를 다시 시작합니다.</li>
          </ol>
        </div>
      </div>
    );
  }
  return <KakaoMap appKey={APP_KEY} {...props} />;
}
