import { useRef, useState, type PointerEvent } from 'react';

/** 이 거리(px)보다 적게 움직이면 끌기가 아니라 탭으로 본다 */
const DRAG_THRESHOLD_PX = 6;
/** 모바일 목록에서 방문 카드가 놓일 수 있는 자리(다른 방문 카드) */
export const VISIT_SLOT_ATTR = 'data-visit-slot';
/** 다른 일차로 옮길 수 있는 일차 탭 */
export const DAY_TAB_ATTR = 'data-day-tab';

/** 놓는 곳: 같은 날의 다른 방문 자리, 또는 다른 일차 탭 */
export type CardDropTarget = { kind: 'visit'; index: number } | { kind: 'day'; day: number };

/** 포인터 아래에서 놓을 곳(방문 자리 또는 일차 탭)을 찾는다 */
function targetAt(x: number, y: number): CardDropTarget | null {
  for (const el of document.elementsFromPoint(x, y)) {
    if (!(el instanceof HTMLElement)) continue;
    if (el.hasAttribute(VISIT_SLOT_ATTR)) return { kind: 'visit', index: Number(el.getAttribute(VISIT_SLOT_ATTR)) };
    if (el.hasAttribute(DAY_TAB_ATTR)) return { kind: 'day', day: Number(el.getAttribute(DAY_TAB_ATTR)) };
  }
  return null;
}

/** 모바일 방문 카드를 손잡이로 끌어 같은 날의 다른 자리나 다른 일차 탭에 놓는 포인터 동작 */
export function useCardDrag(enabled: boolean, onDrop: (target: CardDropTarget) => void) {
  const [offsetY, setOffsetY] = useState<number | null>(null);
  const [target, setTarget] = useState<CardDropTarget | null>(null);
  const origin = useRef<{ x: number; y: number; moved: boolean } | null>(null);

  const reset = () => {
    origin.current = null;
    setOffsetY(null);
    setTarget(null);
  };

  const onPointerDown = (e: PointerEvent<HTMLElement>) => {
    if (!enabled) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    origin.current = { x: e.clientX, y: e.clientY, moved: false };
  };

  const onPointerMove = (e: PointerEvent<HTMLElement>) => {
    const from = origin.current;
    if (!from) return;
    const dy = e.clientY - from.y;
    if (!from.moved && Math.hypot(e.clientX - from.x, dy) < DRAG_THRESHOLD_PX) return;
    from.moved = true;
    setOffsetY(dy);
    setTarget(targetAt(e.clientX, e.clientY));
  };

  const onPointerUp = (e: PointerEvent<HTMLElement>) => {
    const from = origin.current;
    if (from?.moved) {
      const drop = targetAt(e.clientX, e.clientY);
      if (drop) onDrop(drop);
    }
    reset();
  };

  return {
    dragging: offsetY !== null,
    offsetY,
    target,
    handlers: { onPointerDown, onPointerMove, onPointerUp, onPointerCancel: reset },
  };
}
