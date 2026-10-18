import { X } from 'lucide-react';
import { useEffect, useRef } from 'react';
import type { ChatSession } from '../../hooks/useChatSession';
import AgentSteps from './AgentSteps';
import ChatInput from './ChatInput';

interface Props {
  open: boolean;
  onClose: () => void;
  chat: ChatSession;
  onSend: (text: string) => void;
}

/** 왼쪽에서 슬라이드로 열리는 대화 내역 + 에이전트 진행 단계 패널 */
export default function ChatDrawer({ open, onClose, chat, onSend }: Props) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) endRef.current?.scrollIntoView({ block: 'end' });
  }, [open, chat.messages, chat.steps]);

  if (!open) return null;

  return (
    <aside
      aria-label="에이전트 대화"
      // 데스크톱: 하단 입력창(높이 56px + 간격 16px)을 가리지 않도록 그 위에서 끝낸다
      className="animate-slide-in-left fixed inset-0 z-50 flex flex-col bg-surface p-5 lg:absolute lg:inset-x-auto lg:bottom-[72px] lg:left-0 lg:top-0 lg:z-40 lg:w-[380px] lg:rounded-3xl lg:shadow-2xl lg:shadow-primary/20"
    >
      <header className="mb-4 flex items-start justify-between">
        <div>
          <h2 className="text-lg font-bold">에이전트 대화</h2>
          <p className="mt-0.5 text-[11px] text-text-sub">데모 모드: 응답은 시뮬레이션입니다</p>
        </div>
        <button
          type="button"
          aria-label="대화 닫기"
          onClick={onClose}
          className="grid size-9 place-items-center rounded-full bg-bg text-text-sub hover:text-text-main"
        >
          <X size={16} />
        </button>
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pr-1">
        {chat.messages.map((m) => (
          <p
            key={m.id}
            className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
              m.role === 'user' ? 'self-end bg-primary text-white' : 'self-start bg-bg'
            }`}
          >
            {m.text}
          </p>
        ))}
        <div>
          <h3 className="mb-2 mt-2 text-xs font-semibold text-text-sub">
            {chat.running ? '진행 중' : '최근 실행'}
          </h3>
          <AgentSteps steps={chat.steps} />
        </div>
        <div ref={endRef} />
      </div>

      {/* 모바일은 패널이 화면 전체를 덮으므로 입력창을 패널 안에도 둔다 */}
      <div className="mt-4 lg:hidden">
        <ChatInput onSubmit={onSend} busy={chat.running} />
      </div>
    </aside>
  );
}
