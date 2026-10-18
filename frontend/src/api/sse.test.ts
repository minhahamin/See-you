import { describe, expect, it } from 'vitest';
import { parseSseBlock, readSse, type SseMessage } from './sse';

/** 문자열 조각들을 그대로 흘려 보내는 스트림 */
function streamOf(...chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      chunks.forEach((c) => controller.enqueue(encoder.encode(c)));
      controller.close();
    },
  });
}

async function collect(body: ReadableStream<Uint8Array>): Promise<SseMessage[]> {
  const out: SseMessage[] = [];
  for await (const m of readSse(body)) out.push(m);
  return out;
}

describe('parseSseBlock', () => {
  it('event와 data를 읽는다', () => {
    expect(parseSseBlock('event: step\ndata: {"a":1}')).toEqual({ event: 'step', data: '{"a":1}' });
  });
  it('여러 줄 data는 줄바꿈으로 잇는다', () => {
    expect(parseSseBlock('event: x\ndata: a\ndata: b')?.data).toBe('a\nb');
  });
  it('주석(ping)이나 event 없는 블록은 무시한다', () => {
    expect(parseSseBlock(': ping')).toBeNull();
    expect(parseSseBlock('data: orphan')).toBeNull();
  });
});

describe('readSse', () => {
  it('CRLF 구분자를 처리한다 (sse-starlette 형식)', async () => {
    const msgs = await collect(streamOf('event: step\r\ndata: 1\r\n\r\nevent: done\r\ndata: {}\r\n\r\n'));
    expect(msgs.map((m) => m.event)).toEqual(['step', 'done']);
  });

  it('이벤트가 청크 경계에서 잘려도 이어 붙인다', async () => {
    const msgs = await collect(streamOf('event: ste', 'p\ndata: {"x"', ':1}\n', '\nevent: done\ndata: {}\n\n'));
    expect(msgs).toEqual([
      { event: 'step', data: '{"x":1}' },
      { event: 'done', data: '{}' },
    ]);
  });

  it('한글이 바이트 경계에서 잘려도 깨지지 않는다', async () => {
    const bytes = new TextEncoder().encode('event: question\ndata: "며칠 일정인가요?"\n\n');
    const cut = 30; // '며칠' 중간
    const body = new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(bytes.slice(0, cut));
        c.enqueue(bytes.slice(cut));
        c.close();
      },
    });
    expect((await collect(body))[0].data).toBe('"며칠 일정인가요?"');
  });

  it('끝에 빈 줄이 없어도 마지막 이벤트를 내보낸다', async () => {
    expect(await collect(streamOf('event: done\ndata: {}'))).toEqual([{ event: 'done', data: '{}' }]);
  });
});
