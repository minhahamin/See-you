import { useState } from 'react';
import Sidebar from './components/layout/Sidebar';
import TabBar from './components/layout/TabBar';
import type { NavKey } from './components/layout/nav';
import { useChatSession } from './hooks/useChatSession';
import DashboardPage from './pages/DashboardPage';
import PlannerPage from './pages/PlannerPage';
import SettingsPage from './pages/SettingsPage';

export default function App() {
  // 사이드바의 "지도"는 플래너의 지도 보기와 같은 화면이다
  const [nav, setNav] = useState<NavKey>('planner');
  // 화면을 오가도 대화가 유지되도록 App에서 들고 있는다
  const chat = useChatSession();

  return (
    <div className="h-dvh bg-gradient-to-br from-[#FFE1EB] via-bg to-[#FFF9FB] lg:p-5">
      <div className="flex h-full overflow-hidden bg-white/50 shadow-soft backdrop-blur lg:rounded-[2rem]">
        <Sidebar active={nav} onChange={setNav} />
        <main className="flex min-w-0 flex-1 flex-col p-4 pb-20 lg:p-6 lg:pb-6">
          {(nav === 'planner' || nav === 'map') && (
            <PlannerPage
              view={nav === 'map' ? 'map' : 'timeline'}
              onViewChange={(view) => setNav(view === 'map' ? 'map' : 'planner')}
              chat={chat}
            />
          )}
          {nav === 'dashboard' && <DashboardPage />}
          {nav === 'settings' && <SettingsPage />}
        </main>
        <TabBar active={nav} onChange={setNav} />
      </div>
    </div>
  );
}
