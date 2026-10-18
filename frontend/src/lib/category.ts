import { BedDouble, Coffee, Mountain, Utensils, Waves, type LucideIcon } from 'lucide-react';
import type { Category } from '../types';

interface CategoryMeta {
  label: string;
  /** 블록 배경 */
  bg: string;
  /** 같은 색의 글자/막대 */
  text: string;
  /** 블록 위 글자색 (노란색 배경은 어두운 글자) */
  fg: string;
  /** 캔버스(이미지 저장)용 색. tailwind.config.js의 토큰과 같은 값 */
  hex: string;
  onHex: string;
  icon: LucideIcon;
}

// Tailwind가 클래스를 인식하도록 전체 클래스명을 그대로 적는다.
export const CATEGORY_META: Record<Category, CategoryMeta> = {
  sight: { label: '관광지', bg: 'bg-cat-sight', text: 'text-cat-sight', fg: 'text-white', hex: '#22C55E', onHex: '#FFFFFF', icon: Mountain },
  food: { label: '맛집', bg: 'bg-cat-food', text: 'text-cat-food', fg: 'text-white', hex: '#FF8A4C', onHex: '#FFFFFF', icon: Utensils },
  cafe: { label: '카페', bg: 'bg-cat-cafe', text: 'text-cat-cafe', fg: 'text-text-main', hex: '#FFC53D', onHex: '#1F2937', icon: Coffee },
  stay: { label: '숙소', bg: 'bg-cat-stay', text: 'text-cat-stay', fg: 'text-white', hex: '#8B5CF6', onHex: '#FFFFFF', icon: BedDouble },
  activity: { label: '체험', bg: 'bg-cat-activity', text: 'text-cat-activity', fg: 'text-white', hex: '#4FA3F7', onHex: '#FFFFFF', icon: Waves },
};
