import { useRef, useState, type PointerEvent } from 'react';
import { snapStart, type DropTarget } from '../lib/dragMove';

/** 이 거리(px)보다 적게 움직이면 끌기가 아니라 클릭으로 본다 */
const DRAG_THRESHOLD_PX = 5;
/** 일차 행의 시간 트랙에 붙는 data 속성 — 놓을 곳을 찾는 데 쓴다 */
export const DAY_TRACK_ATTR = 'data-day-track';

interface Options {
  enabled: boolean;
  durationMin: number;
  onDrop: (target: DropTarget) => void;
}

interface Origin {
  x: number;
  y: number;
  left: number; // 끌기 시작 때 블록의 화면상 왼쪽 위치
  moved: boolean;
}

/** 타임라인 블록을 끌어 다른 시간·일차에 놓는 포인터 동작. 놓을 곳은 30분 격자에 맞춰진다 */
export function useBlockDrag({ enabled, durationMin, onDrop }: Options) {
  const [offset, setOffset] = useState<{ x: number; y: number } | null>(null);
  const [target, setTarget] = useState<DropTarget | null>(null);
  const origin = useRef<Origin | null>(null);
  const suppressClick = useRef(false);

  /** 포인터 아래에 있는 일차 트랙을 찾아 놓을 곳을 계산한다. 트랙 밖이면 null */
  const resolve = (e: PointerEvent<HTMLElement>, from: Origin): DropTarget | null => {
    const track = document
      .elementsFromPoint(e.clientX, e.clientY)
      .find((el): el is HTMLElement => el instanceof HTMLElement && el.hasAttribute(DAY_TRACK_ATTR));
    if (!track) return null;
    const leftPx = from.left + (e.clientX - from.x) - track.getBoundingClientRect().left;
    return { day: Number(track.getAttribute(DAY_TRACK_ATTR)), startMin: snapStart(leftPx, durationMin) };
  };

  const reset = () => {
    origin.current = null;
    setOffset(null);
    setTarget(null);
  };

  const onPointerDown = (e: PointerEvent<HTMLElement>) => {
    if (!enabled || e.button !== 0) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    origin.current = { x: e.clientX, y: e.clientY, left: e.currentTarget.getBoundingClientRect().left, moved: false };
  };

  const onPointerMove = (e: PointerEvent<HTMLElement>) => {
    const from = origin.current;
    if (!from) return;
    const dx = e.clientX - from.x;
    const dy = e.clientY - from.y;
    if (!from.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD_PX) return;
    from.moved = true;
    setOffset({ x: dx, y: dy });
    setTarget(resolve(e, from));
  };

  const onPointerUp = (e: PointerEvent<HTMLElement>) => {
    const from = origin.current;
    if (!from) return;
    if (from.moved) {
      // 끌고 놓은 뒤에 따라오는 클릭이 선택으로 처리되지 않게 한다
      suppressClick.current = true;
      setTimeout(() => {
        suppressClick.current = false;
      }, 0);
      const drop = resolve(e, from);
      if (drop) onDrop(drop);
    }
    reset();
  };

  return {
    dragging: offset !== null,
    offset,
    target,
    /** 클릭이 끌기의 끝에서 온 것이면 true */
    consumeClick: () => suppressClick.current,
    handlers: { onPointerDown, onPointerMove, onPointerUp, onPointerCancel: reset },
  };
}
