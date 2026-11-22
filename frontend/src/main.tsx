import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { api, sendTurn, type Action, type Conversation, type Source, type Turn } from './api';
import './style.css';
import {Library} from './knowledge/Library';
import {activeSection} from './knowledge/records';

const examples = [
  ['✎', 'Записать мысль', 'Сохрани заметку о '],
  ['☷', 'Посмотреть задачи', 'Покажи мои задачи'],
  ['⌕', 'Найти в заметках', 'Найди в моей базе знаний ']
];
const toolLabels: Record<string, string> = {
  search_knowledge: 'Поиск по базе знаний', get_tasks: 'Список задач', get_projects: 'Список проектов',
  create_task: 'Создание задачи', update_task: 'Изменение задачи', delete_task: 'Запрос на удаление',
  create_goal: 'Создание цели', update_goal: 'Изменение цели', save_note: 'Сохранение заметки'
};

function Book({ large = false }: {large?: boolean}) {
  return <span aria-hidden="true" className={large ? 'book large' : 'book'}><i/><b/></span>;
}

function ResponseBody({ turn, busy, decide }: {
  turn: Turn; busy: boolean; decide: (action: Action, confirm: boolean) => void
}) {
  const hits = turn.tools.flatMap(e => e.name === 'search_knowledge' && Array.isArray(e.result) ? e.result as Source[] : []);
  return <><div className="answer">{turn.answer}</div>
    {hits.length > 0 && <details className="sources"><summary>Источники · {hits.length}</summary>
      {hits.map((s, i) => <div className="source" key={i}><a href={s.url} target="_blank" rel="noreferrer">{s.title} ↗</a><p>{s.text}</p></div>)}</details>}
    {turn.confirmations.map(a => <div className="confirm" key={a.id}><strong>Удаление задачи «{a.title}»</strong>
      {a.state === 'pending' && Date.parse(a.expires_at) > Date.now() ? <div>
        <button disabled={busy} onClick={() => decide(a, true)}>Удалить</button>
        <button disabled={busy} onClick={() => decide(a, false)}>Отмена</button>
      </div> : <small>{a.state === 'pending' || a.state === 'expired' ? 'Срок подтверждения истёк' : 'Запрос закрыт'}</small>}</div>)}
  </>;
}

function App() {
  const [section, setSection] = useState(activeSection);
  useEffect(() => {
    const sync = () => setSection(activeSection());
    window.addEventListener('hashchange', sync);
    return () => window.removeEventListener('hashchange', sync);
  }, []);
  const [chats, setChats] = useState<Conversation[]>([]);
  const [id, setId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [partial, setPartial] = useState<{prompt:string; answer:string; status:string} | null>(null);
  const [open, setOpen] = useState(false);
  const lock = useRef(false);
  const retry = useRef<{id:string; prompt:string; key:string} | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const title = chats.find(c => c.id === id)?.title ?? 'Новый диалог';

  function hold() { lock.current = true; setBusy(true); }
  function release() { lock.current = false; setBusy(false); }
  function report(e: unknown) { setError(e instanceof Error ? e.message : 'Ошибка соединения'); }
  function select(value: string | null) {
    setId(value);
    if (value) localStorage.setItem('active-chat', value); else localStorage.removeItem('active-chat');
  }
  async function load(chat: string) {
    const data = await api<Conversation & {turns: Turn[]}>(`/api/chats/${chat}`);
    setTurns(data.turns); select(chat);
  }
  useEffect(() => {
    hold();
    (async () => {
      const list = await api<Conversation[]>('/api/chats'); setChats(list);
      const saved = localStorage.getItem('active-chat');
      if (saved && list.some(c => c.id === saved)) await load(saved);
    })().catch(report).finally(release);
  }, []);
  useEffect(() => { bottom.current?.scrollIntoView({ block:'end' }); }, [turns, partial]);

  async function navigate(chat: string | null) {
    if (lock.current) return;
    hold(); setError('');
    try {
      if (chat) await load(chat); else { select(null); setTurns([]); }
      setDraft(''); retry.current = null; setOpen(false); input.current?.focus();
    } catch (e) { report(e); } finally { release(); }
  }
  async function send() {
    const prompt = draft.trim();
    if (!prompt || lock.current) return;
    hold(); setError(''); setOpen(false); setDraft('');
    setPartial({prompt, answer:'', status:'Ассистент отвечает…'});
    let finished = false;
    try {
      let chat = id;
      if (!chat) {
        const created = await api<Conversation>('/api/chats', {});
        chat = created.id; select(chat); setChats(cs => [created, ...cs]);
      }
      const key = retry.current?.id === chat && retry.current.prompt === prompt ? retry.current.key : crypto.randomUUID();
      retry.current = { id:chat, prompt, key };
      const turn = await sendTurn(chat, key, prompt,
        text => setPartial(p => p && {...p, answer:p.answer + text}),
        tool => setPartial(p => p && {...p, answer:'', status:toolLabels[tool] ?? 'Выполняется действие'}));
      finished = true; retry.current = null;
      setTurns(ts => [...ts.filter(t => t.request_id !== key), turn]);
      setChats(await api<Conversation[]>('/api/chats'));
    } catch (e) { report(e); if (!finished) setDraft(prompt); }
    finally { setPartial(null); release(); input.current?.focus(); }
  }
  async function decide(action: Action, confirm: boolean) {
    if (!id || lock.current) return;
    hold(); setError('');
    try { await api(`/api/agent/confirmations/${action.id}`, {confirm}); }
    catch (e) { report(e); }
    finally { try { await load(id); } catch (e) { report(e); } release(); }
  }
  const empty = !turns.length && !partial;
  if (section) return <Library kind={section}/>;
  return <div className="workspace">
    {open && <button className="shade" aria-label="Закрыть историю" onClick={() => setOpen(false)}/>}
    <aside className={open ? 'open' : ''}>
      <div className="brand"><Book/><span>Контекст</span></div>
      <button className="new" disabled={busy} onClick={() => navigate(null)}><span>＋</span> Новый диалог</button>
      <h2>История диалогов</h2>
      <nav aria-label="История диалогов">{chats.length === 0 && <p>Здесь появятся ваши диалоги</p>}
        {chats.map(c => <button key={c.id} disabled={busy} className={id === c.id ? 'active' : ''} onClick={() => navigate(c.id)}>{c.title}</button>)}</nav>
      <a className="docs" href="/docs" target="_blank" rel="noreferrer">Документация API <span>↗</span></a>
    </aside>
    <main>
      <header><button className="menu" aria-label="Открыть историю" onClick={() => setOpen(true)}>☰</button><span>Чаты</span><small>/</small><strong>{title}</strong>
        <a className="lib-link" href="#knowledge/notes">База знаний</a></header>
      <section className="scroll" aria-label="Переписка">
        {empty ? <div className="welcome"><div className="illustration"><Book large/></div><h1>С чего начнём?</h1>
          <p>Спросите о своих заметках, разберите задачи<br className="wide"/> или сохраните новую мысль.</p>
          <div className="examples">{examples.map(([icon,label,text]) => <button disabled={busy} key={label} onClick={() => {setDraft(text); input.current?.focus();}}>
            <span aria-hidden="true">{icon}</span>{label}</button>)}</div></div>
          : <div className="thread">{turns.map(t => <article key={t.request_id}><div className="user">{t.prompt}</div><div className="by"><Book/>Контекст</div>
            <ResponseBody turn={t} busy={busy} decide={decide}/></article>)}
            {partial && <article><div className="user">{partial.prompt}</div><div className="by"><Book/>Контекст</div>
              <div className={partial.answer ? 'answer' : 'working'}>{partial.answer || partial.status}</div></article>}
            <div ref={bottom}/></div>}
      </section>
      <footer>{error && <div role="alert" className="error">{error}</div>}
        <form onSubmit={e => {e.preventDefault(); void send();}}>
          <textarea ref={input} rows={2} maxLength={8000} aria-label="Сообщение" placeholder="Напишите сообщение…" value={draft}
            onChange={e => setDraft(e.target.value)} onKeyDown={e => {if(e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {e.preventDefault(); void send();}}}/>
          <button className="send" disabled={busy || !draft.trim()} aria-label="Отправить сообщение">↑</button>
        </form><div className="hint">Enter — отправить <i>·</i> Shift + Enter — новая строка</div></footer>
    </main></div>;
}

createRoot(document.getElementById('root')!).render(<App/>);
