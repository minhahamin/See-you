import type { LucideIcon } from 'lucide-react';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const cache = new Map<string, Promise<HTMLImageElement>>();

/**
 * lucide 아이콘을 캔버스에 그릴 수 있는 이미지로 만든다.
 * 흐려지지 않도록 SVG를 size×scale 크기로 만들고, 그릴 때 size 크기로 줄여 쓴다.
 */
export function loadIcon(icon: LucideIcon, color: string, size: number, scale: number): Promise<HTMLImageElement> {
  const key = `${icon.displayName ?? 'icon'}|${color}|${size}|${scale}`;
  const cached = cache.get(key);
  if (cached) return cached;

  const svg = renderToStaticMarkup(createElement(icon, { size: size * scale, color, strokeWidth: 2 }));
  const promise = new Promise<HTMLImageElement>((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`icon load failed: ${key}`));
    img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  });
  cache.set(key, promise);
  return promise;
}
