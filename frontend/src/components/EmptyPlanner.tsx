import { Loader2, Sparkles } from 'lucide-react';

interface Props {
  running: boolean;
  onPick: (text: string) => void;
  onDemo: () => void;
}

const EXAMPLES = [
  '내일부터 친구랑 제주 2박 3일, 맛집이랑 카페 위주로 가고 싶어',
  '11월 14일부터 커플끼리 제주 3일, 바다가 보이는 곳 위주로, 너무 비싸지 않게',
  '가족이랑 제주 2박 3일 가려는데 아이가 있어서 실내 장소가 많았으면 좋겠어',
];

/** 아직 일정이 없을 때 보여 주는 시작 화면. 예시 문장을 누르면 바로 보낸다. */
export default function EmptyPlanner({ running, onPick, onDemo }: Props) {
  return (
    <div className="grid min-h-[320px] flex-1 place-items-center rounded-3xl bg-surface p-8 text-center shadow-soft">
      <div className="flex max-w-lg flex-col items-center gap-5">
        {running ? (
          <>
            <Loader2 size={32} className="animate-spin text-primary" />
            <p className="font-semibold">일정을 만드는 중이에요</p>
            <p className="text-sm text-text-sub">왼쪽 대화 패널에서 진행 단계를 볼 수 있어요.</p>
          </>
        ) : (
          <>
            <Sparkles size={32} className="text-primary" />
            <div>
              <p className="text-lg font-bold">어디로 떠나볼까요?</p>
              <p className="mt-1 text-sm text-text-sub">
                날짜, 일정 길이, 누구와 가는지를 말해 주면 장소와 후기를 찾아 일정을 만들어 드려요.
              </p>
            </div>
            <ul className="flex w-full flex-col gap-2">
              {EXAMPLES.map((text) => (
                <li key={text}>
                  <button
                    type="button"
                    onClick={() => onPick(text)}
                    className="w-full rounded-2xl bg-bg px-4 py-3 text-left text-sm transition-colors hover:bg-primary/10"
                  >
                    {text}
                  </button>
                </li>
              ))}
            </ul>
            <button type="button" onClick={onDemo} className="text-xs text-text-sub underline underline-offset-4">
              서버 없이 예시 일정 보기
            </button>
          </>
        )}
      </div>
    </div>
  );
}
