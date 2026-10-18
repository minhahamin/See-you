import type { ReactNode } from 'react';

interface Props {
  title: string;
  /** 데이터 출처. 없으면 "없음"으로 표시 */
  source: string | null;
  isSample: boolean;
  className?: string;
  children: ReactNode;
}

/** 대시보드 공통 카드: 제목 + 내용 + 하단 데이터 출처 */
export default function DashboardCard({ title, source, isSample, className = '', children }: Props) {
  return (
    <section className={`flex flex-col rounded-3xl bg-surface p-6 shadow-soft ${className}`}>
      <h2 className="mb-4 text-base font-bold">{title}</h2>
      <div className="flex-1">{children}</div>
      <footer className="mt-4 flex flex-wrap items-center gap-2 text-[11px] text-text-sub">
        <span>출처: {source ?? '없음'}</span>
        {isSample && (
          <span className="rounded-full bg-cat-cafe/25 px-2 py-0.5 font-semibold text-text-main">샘플 데이터</span>
        )}
      </footer>
    </section>
  );
}

/** 수치가 없을 때의 표시. 임의 값을 넣지 않는다. */
export function NoData() {
  return <p className="grid place-items-center py-10 text-sm text-text-sub">데이터 없음</p>;
}
