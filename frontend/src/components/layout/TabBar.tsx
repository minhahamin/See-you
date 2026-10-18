import { NAV_ITEMS, type NavKey } from './nav';

interface Props {
  active: NavKey;
  onChange: (key: NavKey) => void;
}

/** 모바일 하단 탭바 (플래너 / 지도 / 기록 / 대시보드 / 설정) */
export default function TabBar({ active, onChange }: Props) {
  const items = NAV_ITEMS;
  return (
    <nav className="fixed inset-x-0 bottom-0 z-30 flex justify-around bg-surface px-4 pb-[env(safe-area-inset-bottom)] pt-2 shadow-[0_-8px_30px_-10px_rgba(238,123,166,0.3)] lg:hidden">
      {items.map(({ key, label, icon: Icon }) => (
        <button
          key={key}
          type="button"
          onClick={() => onChange(key)}
          className={`flex flex-col items-center gap-0.5 px-2 py-1 text-[11px] font-medium ${
            active === key ? 'text-primary-ink' : 'text-text-sub'
          }`}
        >
          <Icon size={20} />
          {label}
        </button>
      ))}
    </nav>
  );
}
