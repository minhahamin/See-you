import { CalendarDays, History, LayoutDashboard, Map, Settings, type LucideIcon } from 'lucide-react';

export type NavKey = 'planner' | 'map' | 'history' | 'dashboard' | 'settings';

export interface NavItem {
  key: NavKey;
  label: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { key: 'planner', label: '플래너', icon: CalendarDays },
  { key: 'map', label: '지도', icon: Map },
  { key: 'history', label: '기록', icon: History },
  { key: 'dashboard', label: '대시보드', icon: LayoutDashboard },
  { key: 'settings', label: '설정', icon: Settings },
];
