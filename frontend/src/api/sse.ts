// POST 요청에는 EventSource를 쓸 수 없으므로, fetch 응답 본문을 직접 읽어 SSE를 해석한다.

export interface SseMessage {
  event: string;
  data: string;
}

/** SSE 블록 하나("event: x\ndata: y")를 메시지로 바꾼다. 주석(`: ping`)이나 event가 없는 블록은 null */
export function parseSseBlock(block: string): SseMessage | null {
  let event = '';
  const data: string[] = [];
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''));
  }
  return event ? { event, data: data.join('\n') } : null;
}

/** 스트림 본문을 읽으며 완성된 SSE 메시지를 하나씩 내보낸다. 블록 경계는 빈 줄이다. */
export async function* readSse(body: ReadableStream<Uint8Array>): AsyncGenerator<SseMessage> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    for (;;) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, '\n');
      let boundary = buffer.indexOf('\n\n');
      while (boundary !== -1) {
        const message = parseSseBlock(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
        if (message) yield message;
        boundary = buffer.indexOf('\n\n');
      }
      if (done) {
        const rest = parseSseBlock(buffer);
        if (rest) yield rest;
        return;
      }
    }
  } finally {
    reader.releaseLock();
  }
}
