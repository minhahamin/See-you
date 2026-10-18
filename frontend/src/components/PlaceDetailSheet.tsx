import { X } from 'lucide-react';
import type { ReactNode } from 'react';

interface Props {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}

/** 모바일: 블록을 누르면 아래에서 올라오는 바텀시트 */
export default function PlaceDetailSheet({ open, onClose, children }: Props) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 lg:hidden">
      <button
        type="button"
        aria-label="닫기"
        onClick={onClose}
        className="absolute inset-0 bg-text-main/30"
      />
      <div className="animate-sheet-up absolute inset-x-0 bottom-0 flex max-h-[80dvh] flex-col rounded-t-3xl bg-bg p-3 pb-6">
        <button
          type="button"
          aria-label="닫기"
          onClick={onClose}
          className="mb-2 ml-auto grid size-8 place-items-center rounded-full bg-surface text-text-sub"
        >
          <X size={16} />
        </button>
        {children}
      </div>
    </div>
  );
}
