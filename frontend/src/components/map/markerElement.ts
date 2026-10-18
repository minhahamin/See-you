interface MarkerOptions {
  /** 그날의 방문 순번 (1부터) */
  number: number;
  /** 일차 색상 */
  color: string;
  /** 마우스를 올리면 보이는 툴팁(장소 이름) */
  title: string;
  /** 선택된 마커 위에 항상 보여줄 장소 이름 */
  label: string | null;
  selected: boolean;
  onClick: () => void;
}

/** 지도 위에 올릴 번호 마커 DOM. 텍스트는 textContent로만 넣는다. */
export function createMarkerElement({ number, color, title, label, selected, onClick }: MarkerOptions): HTMLElement {
  const root = document.createElement('button');
  root.type = 'button';
  root.className = `relative flex items-center justify-center rounded-full border-2 border-white text-xs font-bold text-white shadow-lg ${
    selected ? 'size-9 ring-4 ring-white/70' : 'size-7'
  }`;
  root.style.backgroundColor = color;
  root.textContent = String(number);
  root.title = title;
  root.setAttribute('aria-label', `${number}. ${title}`);

  if (label) {
    const tag = document.createElement('span');
    tag.className =
      'absolute bottom-full mb-1.5 whitespace-nowrap rounded-full bg-white px-2.5 py-1 text-xs font-semibold text-text-main shadow-lg';
    tag.textContent = label;
    root.appendChild(tag);
  }

  root.addEventListener('click', onClick);
  return root;
}
