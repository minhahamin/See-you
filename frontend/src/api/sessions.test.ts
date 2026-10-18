import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, dispatchSse, streamMessage, type StreamHandlers } from './sessions';

function makeHandlers() {
  const log: string[] = [];
  const handlers: StreamHandlers = {
    onStep: (e) => log.push(`step:${e.node}:${e.status}`),
    onQuestion: (e) => log.push(`question:${e.question}`),
    onItinerary: (e) => log.push(`itinerary:${e.itinerary.title}`),
    onError: (m) => log.push(`error:${m}`),
  };
  return { log, handlers };
}

const sse = (event: string, data: unknown) => `event: ${event}\r\ndata: ${JSON.stringify(data)}\r\n\r\n`;

function sseResponse(...events: string[]): Response {
  return new Response(events.join(''), { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
}

afterEach(() => vi.unstubAllGlobals());

describe('dispatchSse', () => {
  it('이벤트 종류별로 핸들러를 부른다', () => {
    const { log, handlers } = makeHandlers();
    dispatchSse({ event: 'step', data: '{"node":"a","status":"running"}' }, handlers);
    dispatchSse({ event: 'question', data: '{"question":"언제?"}' }, handlers);
    dispatchSse({ event: 'error', data: '{"message":"실패"}' }, handlers);
    expect(log).toEqual(['step:a:running', 'question:언제?', 'error:실패']);
  });

  it('done은 종료 신호이고, 깨진 JSON은 건너뛴다', () => {
    const { log, handlers } = makeHandlers();
    expect(dispatchSse({ event: 'done', data: '{}' }, handlers)).toBe(true);
    expect(dispatchSse({ event: 'step', data: '{broken' }, handlers)).toBe(false);
    expect(log).toEqual([]);
  });
});

describe('streamMessage', () => {
  it('SSE 이벤트를 순서대로 전달하고 done에서 끝난다', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        sseResponse(
          sse('step', { node: 'parse_request', status: 'running' }),
          sse('step', { node: 'parse_request', status: 'done' }),
          sse('question', { question: '며칠 일정인가요?', missing_fields: ['days'] }),
          sse('done', {}),
          sse('step', { node: 'never', status: 'running' }), // done 뒤는 무시
        ),
      ),
    );
    const { log, handlers } = makeHandlers();
    await streamMessage('s1', '안녕', handlers);
    expect(log).toEqual(['step:parse_request:running', 'step:parse_request:done', 'question:며칠 일정인가요?']);
  });

  it('서버 오류는 detail 문구를 담은 ApiError로 던진다', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: '이전 메시지를 처리하는 중입니다.' }), { status: 409 })),
    );
    await expect(streamMessage('s1', 'x', makeHandlers().handlers)).rejects.toMatchObject({
      status: 409,
      message: '이전 메시지를 처리하는 중입니다.',
    });
  });

  it('네트워크 오류는 status 0인 ApiError로 던진다', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    const err = await streamMessage('s1', 'x', makeHandlers().handlers).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(0);
  });
});
