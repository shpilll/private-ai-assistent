export type Conversation = { id: string; title: string; updated_at: string };
export type Source = { title: string; text: string; url: string; start: number };
export type Action = { id: string; title: string; expires_at: string; state: string };
export type Turn = {
  request_id: string; prompt: string; answer: string; confirmations: Action[];
  tools: { name: string; result?: unknown; error?: unknown }[];
};

export async function api<T>(path: string, body?: object, method = body === undefined ? 'GET' : 'POST'): Promise<T> {
  const multipart = body instanceof FormData;
  const response = await fetch(path, {
    method, headers: body && !multipart ? { 'Content-Type': 'application/json' } : undefined,
    body: multipart ? body : JSON.stringify(body)
  });
  if (!response.ok) {
    const detail = (await response.json().catch(() => ({}))).detail;
    throw new Error(typeof detail === 'string' ? detail : `Ошибка запроса (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export async function sendTurn(id: string, requestId: string, message: string,
                               onText: (text: string) => void, onTool: (name: string) => void) {
  const response = await fetch(`/api/chats/${id}/messages`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, request_id: requestId })
  });
  if (!response.ok || !response.body) throw new Error('Не удалось открыть поток ответа.');
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = '';
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += value ?? '';
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';
      for (const line of lines) {
        const event = JSON.parse(line);
        if (event.type === 'delta') onText(event.data);
        if (event.type === 'tool') onTool(event.data);
        if (event.type === 'error') throw new Error(event.data);
        if (event.type === 'done') return event.data as Turn;
      }
      if (done) throw new Error('Связь прервалась. Повторите отправку сообщения.');
    }
  } finally {
    await reader.cancel();
    reader.releaseLock();
  }
}
