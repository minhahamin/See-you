import { useEffect, useMemo, useState } from 'react';
import ChatDrawer, { inputPlaceholder } from '../components/chat/ChatDrawer';
import ChatInput from '../components/chat/ChatInput';
import EmptyPlanner from '../components/EmptyPlanner';
import TopBar, { type ViewMode } from '../components/layout/TopBar';
import MapView from '../components/MapView';
import PlaceDetail from '../components/PlaceDetail';
import PlaceDetailSheet from '../components/PlaceDetailSheet';
import MobileTimeline from '../components/timeline/MobileTimeline';
import TimelineView from '../components/timeline/TimelineView';
import TripSummary from '../components/TripSummary';
import TripSummaryChips from '../components/TripSummaryChips';
import type { ChatSession } from '../hooks/useChatSession';
import { usePlaceReviews } from '../hooks/usePlaceReviews';
import { moveMessage, type MoveRequest } from '../lib/dragMove';
import { computeStats } from '../lib/summary';
import type { Selection } from '../types';

interface Props {
  view: ViewMode;
  onViewChange: (view: ViewMode) => void;
  chat: ChatSession;
}

/** 플래너 화면: 타임라인/지도 + 오른쪽 상세·요약 + 하단 입력창 + 대화 패널 */
export default function PlannerPage({ view, onViewChange, chat }: Props) {
  const { itinerary, places } = chat;

  // 처음에는 첫 일정을 "다음 일정"으로 보여준다
  const [selection, setSelection] = useState<Selection>({ day: 1, index: 0 });
  const [sheetOpen, setSheetOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);

  const stats = useMemo(() => (itinerary ? computeStats(itinerary, places) : null), [itinerary, places]);

  // 새 일정으로 바뀌었을 때 선택이 가리키는 방문이 없으면 첫 방문으로 되돌린다
  useEffect(() => {
    if (!itinerary) return;
    setSelection((prev) =>
      itinerary.days.find((d) => d.day === prev.day)?.visits[prev.index]
        ? prev
        : { day: itinerary.days[0]?.day ?? 1, index: 0 },
    );
  }, [itinerary]);

  // 에이전트가 되물으면 대화 패널을 자동으로 열어 질문이 보이게 한다
  useEffect(() => {
    if (chat.awaiting === 'question') setChatOpen(true);
  }, [chat.awaiting]);

  const visit = itinerary?.days.find((d) => d.day === selection.day)?.visits[selection.index];
  const place = visit ? places[visit.place_id] : undefined;
  const reviews = usePlaceReviews(visit, chat.isDemo);

  const handleSelect = (next: Selection) => {
    setSelection(next);
    setSheetOpen(true);
  };

  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  // 이미지 생성 코드는 처음 누를 때만 불러온다
  const handleExport = async () => {
    if (!itinerary) return;
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

  // 타임라인에서 끌어다 놓은 방문은 에이전트 피드백으로 보낸다 (예시 일정이나 실행 중에는 옮기지 않는다)
  const handleMove = (move: MoveRequest) => {
    const moved = itinerary?.days.find((d) => d.day === move.fromDay)?.visits[move.fromIndex];
    const name = moved ? places[moved.place_id]?.name : undefined;
    if (name) handleSend(moveMessage(move, name));
  };
  const canMove = !chat.isDemo && !chat.running;

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
          onNew={chat.newSession}
          exporting={exporting}
        />
        {exportError && (
          <p role="alert" className="rounded-2xl bg-surface px-4 py-2 text-sm text-primary-ink shadow-soft">
            {exportError}
          </p>
        )}

        {!itinerary || !stats ? (
          <EmptyPlanner running={chat.running} onPick={handleSend} onDemo={chat.loadDemo} />
        ) : view === 'map' ? (
          <MapView itinerary={itinerary} places={places} selection={selection} onSelect={handleSelect} />
        ) : (
          <>
            <div className="hidden min-h-0 flex-1 lg:flex">
              <TimelineView
                itinerary={itinerary}
                places={places}
                selection={selection}
                onSelect={handleSelect}
                onMove={canMove ? handleMove : undefined}
              />
            </div>
            <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto lg:hidden">
              <TripSummaryChips stats={stats} />
              <MobileTimeline
                itinerary={itinerary}
                places={places}
                selection={selection}
                onSelect={handleSelect}
                onMove={canMove ? handleMove : undefined}
              />
            </div>
          </>
        )}

        <ChatInput onSubmit={handleSend} busy={chat.running} placeholder={inputPlaceholder(chat)} />
      </div>

      {itinerary && stats && (
        <aside className="hidden min-h-0 w-[340px] shrink-0 flex-col gap-4 overflow-y-auto lg:flex">
          {detail}
          <TripSummary stats={stats} />
        </aside>
      )}

      <PlaceDetailSheet open={sheetOpen} onClose={() => setSheetOpen(false)}>
        {detail}
      </PlaceDetailSheet>

      <ChatDrawer open={chatOpen} onClose={() => setChatOpen(false)} chat={chat} onSend={handleSend} />
    </div>
  );
}
