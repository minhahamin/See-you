import { Luggage } from 'lucide-react';
import AccountButton from './AccountButton';
import { NAV_ITEMS, type NavKey } from './nav';

interface Props {
  active: NavKey;
  onChange: (key: NavKey) => void;
}

/** 데스크톱 왼쪽 아이콘 사이드바 (알약 모양) */
export default function Sidebar({ active, onChange }: Props) {
  return (
    <aside className="hidden lg:flex flex-col items-center gap-6 py-6 pl-6">
      <div className="grid size-11 place-items-center rounded-2xl bg-primary text-white shadow-soft">
        <Luggage size={22} />
      </div>
      <nav className="flex flex-col items-center gap-2 rounded-full bg-surface p-2 shadow-soft">
        {NAV_ITEMS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            type="button"
            title={label}
            aria-label={label}
            aria-current={active === key ? 'page' : undefined}
            onClick={() => onChange(key)}
            className={`grid size-11 place-items-center rounded-full transition-colors ${
              active === key ? 'bg-primary/10 text-primary' : 'text-text-sub hover:text-text-main'
            }`}
          >
            <Icon size={20} />
          </button>
        ))}
      </nav>
      <div className="mt-auto">
        <AccountButton />
      </div>
    </aside>
  );
}
