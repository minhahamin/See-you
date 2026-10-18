import { useMemo, useState } from 'react';
import ChatDrawer from '../components/chat/ChatDrawer';
import ChatInput from '../components/chat/ChatInput';
import TopBar, { type ViewMode } from '../components/layout/TopBar';
import MapView from '../components/MapView';
import PlaceDetail from '../components/PlaceDetail';
import PlaceDetailSheet from '../components/PlaceDetailSheet';
import MobileTimeline from '../components/timeline/MobileTimeline';
import TimelineView from '../components/timeline/TimelineView';
import TripSummary from '../components/TripSummary';
import TripSummaryChips from '../components/TripSummaryChips';
import type { ChatSession } from '../hooks/useChatSession';
import { computeStats } from '../lib/summary';
import { mockItinerary, mockPlaces, mockReviews } from '../mocks';
import type { Selection } from '../types';

interface Props {
  view: ViewMode;
  onViewChange: (view: ViewMode) => void;
  chat: ChatSession;
}

/** 플래너 화면: 타임라인/지도 + 오른쪽 상세·요약 + 하단 입력창 + 대화 패널 */
export default function PlannerPage({ view, onViewChange, chat }: Props) {
  // 아직 API 연결 전이라 더미 데이터를 사용한다
  const itinerary = mockItinerary;
  const places = mockPlaces;

  // 처음에는 첫 일정을 "다음 일정"으로 보여준다
  const [selection, setSelection] = useState<Selection>({ day: 1, index: 0 });
  const [sheetOpen, setSheetOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);

  const stats = useMemo(() => computeStats(itinerary, places), [itinerary, places]);

  const visit = itinerary.days.find((d) => d.day === selection.day)?.visits[selection.index];
  const place = visit ? places[visit.place_id] : undefined;
  const reviews = visit
    ? visit.evidence_review_ids.flatMap((id) => (mockReviews[id] ? [mockReviews[id]] : []))
    : [];

  const handleSelect = (next: Selection) => {
    setSelection(next);
    setSheetOpen(true);
  };

  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  // 이미지 생성 코드는 처음 누를 때만 불러온다
  const handleExport = async () => {
    setExporting(true);
    setExportError(null);
    try {
      const { renderTimelineImage, downloadBlob, timelineFileName } = await import('../lib/exportTimeline');
      downloadBlob(await renderTimelineImage(itinerary, places), timelineFileName(itinerary));
    } catch {
      setExportError('이미지를 만들지 못했어요. 다시 시도해 주세요.');
    } finally {
      setExporting(false);
    }
  };

  // 에이전트 실행 중에는 대화 패널을 자동으로 연다
  const handleSend = (text: string) => {
    chat.send(text);
    setChatOpen(true);
  };

  const detail = visit && place ? <PlaceDetail visit={visit} place={place} reviews={reviews} /> : null;

  return (
    <div className="relative flex min-h-0 flex-1 gap-6">
      <div className="flex min-w-0 flex-1 flex-col gap-4">
        <TopBar
          itinerary={itinerary}
          view={view}
          onViewChange={onViewChange}
          chatOpen={chatOpen}
          chatRunning={chat.running}
          onChatToggle={() => setChatOpen((open) => !open)}
          onExport={handleExport}
          exporting={exporting}
        />
        {exportError && (
          <p role="alert" className="rounded-2xl bg-surface px-4 py-2 text-sm text-primary-ink shadow-soft">
            {exportError}
          </p>
        )}

        {view === 'map' ? (
          <MapView itinerary={itinerary} places={places} selection={selection} onSelect={handleSelect} />
        ) : (
          <>
            <div className="hidden min-h-0 flex-1 lg:flex">
              <TimelineView itinerary={itinerary} places={places} selection={selection} onSelect={handleSelect} />
            </div>
            <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto lg:hidden">
              <TripSummaryChips stats={stats} />
              <MobileTimeline itinerary={itinerary} places={places} selection={selection} onSelect={handleSelect} />
            </div>
          </>
        )}

        <ChatInput onSubmit={handleSend} busy={chat.running} />
      </div>

      <aside className="hidden min-h-0 w-[340px] shrink-0 flex-col gap-4 overflow-y-auto lg:flex">
        {detail}
        <TripSummary stats={stats} />
      </aside>

      <PlaceDetailSheet open={sheetOpen} onClose={() => setSheetOpen(false)}>
        {detail}
      </PlaceDetailSheet>

      <ChatDrawer open={chatOpen} onClose={() => setChatOpen(false)} chat={chat} onSend={handleSend} />
    </div>
  );
}
