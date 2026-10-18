import { Cloud, CloudRain, Sun, type LucideIcon } from 'lucide-react';
import type { WeatherCondition } from '../types';

export const WEATHER_META: Record<WeatherCondition, { label: string; icon: LucideIcon; color: string; hex: string }> = {
  sunny: { label: '맑음', icon: Sun, color: 'text-cat-cafe', hex: '#FFC53D' },
  cloudy: { label: '흐림', icon: Cloud, color: 'text-text-sub', hex: '#9CA3AF' },
  rain: { label: '비', icon: CloudRain, color: 'text-cat-activity', hex: '#4FA3F7' },
};
