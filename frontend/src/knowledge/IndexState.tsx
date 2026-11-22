import React, {useEffect, useState} from 'react';
import {api} from '../api';
import {errorText} from './records';

type Status = {state:'pending'|'ready'|'failed'; error: string | null; provider_configured: boolean; revision:number};
const labels = {pending:'В очереди', ready:'Доступно для поиска', failed:'Ошибка индексации'};

export function IndexState({path, revision}: {path:string; revision:number}) {
  const [state, setState] = useState<Status | null>(null);
  const [error, setError] = useState('');
  const [run, setRun] = useState(0);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function check() {
      try {
        const result = await api<Status>(path);
        if (!active) return;
        setState(result);
        setError('');
        if (result.state === 'pending' && result.provider_configured) timer = setTimeout(check, 3000);
      } catch (e) { if (active) setError(errorText(e)); }
    }
    void check();
    return () => {active = false; clearTimeout(timer);};
  }, [path, revision, run]);
  async function requeue() {
    setBusy(true);
    try {
      await api(path, {});
      setState(null);
      setRun(n => n + 1);
    } catch (e) {setError(errorText(e));}
    finally {setBusy(false);}
  }
  return <section className="idx"><div><strong>Поисковый индекс</strong>
    <p role="status">{state ? labels[state.state] : 'Проверка состояния…'}</p>
    {state?.state === 'pending' && !state.provider_configured && <p>Для индексации нужен ключ провайдера.</p>}
    {(error || state?.error) && <p className="error">{error || state?.error}</p>}</div>
    <button type="button" disabled={busy} onClick={requeue}>Переиндексировать</button></section>;
}
