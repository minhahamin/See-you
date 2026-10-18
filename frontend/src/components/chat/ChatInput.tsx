import { ArrowUp, Sparkles } from 'lucide-react';
import { useState, type FormEvent } from 'react';

interface Props {
  onSubmit: (text: string) => void;
  /** 에이전트 실행 중에는 입력을 막는다 */
  busy?: boolean;
  /** 입력 안내 문구. 생략하면 일정 수정 요청 예시 */
  placeholder?: string;
}

/** 하단 고정 넓은 입력창 */
export default function ChatInput({ onSubmit, busy = false, placeholder = '예: 2일차 오후를 실내 위주로 바꿔줘' }: Props) {
  const [text, setText] = useState('');

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const value = text.trim();
    if (!value || busy) return;
    onSubmit(value);
    setText('');
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="flex items-center gap-3 rounded-full bg-surface py-2 pl-5 pr-2 shadow-soft"
    >
      <Sparkles size={18} className="shrink-0 text-primary" />
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={busy}
        placeholder={busy ? '에이전트가 일정을 만드는 중이에요…' : placeholder}
        aria-label="여행 조건 또는 일정 수정 요청"
        className="min-w-0 flex-1 bg-transparent py-2 text-sm outline-none placeholder:text-text-sub"
      />
      <button
        type="submit"
        aria-label="전송"
        className="grid size-10 shrink-0 place-items-center rounded-full bg-primary text-white shadow-soft transition-opacity disabled:opacity-40"
        disabled={busy || !text.trim()}
      >
        <ArrowUp size={18} />
      </button>
    </form>
  );
}
