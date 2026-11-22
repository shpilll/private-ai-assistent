import React, {useEffect, useState} from 'react';
import {Editor} from './Editor';
import {errorText, listEntries, sections, statuses, type Entry, type Kind} from './records';
import './library.css';

function Collection({kind}: {kind:Kind}) {
  const [rows, setRows] = useState<Entry[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [reload, setReload] = useState(0);
  const [notice, setNotice] = useState('');
  const [editing, setEditing] = useState<Entry | null | undefined>(undefined);
  useEffect(() => {
    let active = true;
    setLoaded(false); setError('');
    listEntries(kind).then(items => {
      if (active) {setRows(items.reverse()); setLoaded(true);}
    }).catch(e => {if (active) setError(errorText(e));});
    return () => {active = false;};
  }, [kind, reload]);
  const search = query.trim().toLocaleLowerCase();
  const filtered = rows.filter(r =>
    [r.title, r.body, r.description].some(v => v?.toLocaleLowerCase().includes(search)));
  function save(row: Entry) {
    setRows(old => [row, ...old.filter(r => r.id !== row.id)].sort((a,b) => b.id-a.id));
    setEditing(undefined); setNotice('Сохранено: ' + row.title); setQuery('');
  }
  return <section className="collection">
    <div className="collection-head"><h1>{sections[kind][0]}</h1>
      <button className="primary" disabled={!loaded} onClick={() => setEditing(null)}>{sections[kind][1]}</button></div>
    <label className="search-box"><span aria-hidden="true">⌕</span><input type="search" aria-label="Поиск в разделе"
      placeholder="Поиск в разделе" value={query} onChange={e => setQuery(e.target.value)}/></label>
    {error && <div role="alert" className="error">{error} <button onClick={() => setReload(n=>n+1)}>Повторить</button></div>}
    {notice && <p className="notice" role="status">{notice}</p>}
    {!loaded && !error && <p role="status">Загрузка…</p>}
    {loaded && <><div className="list-label"><span>Название</span><span>Записей: {filtered.length}</span></div>
      {filtered.length === 0 ? <div className="empty-list">{search ? 'По этому запросу ничего не найдено.' : 'В разделе пока нет записей.'}</div>
      : <ul className="entry-list">{filtered.map(r => <li key={r.id}><button onClick={() => setEditing(r)}>
        <span className="entry-main"><strong>{r.title}</strong>{(r.description || r.body) &&
          <small>{(r.description || r.body)?.slice(0,180)}</small>}</span>
        {r.status && <span className="state-pill">{statuses[r.status]}</span>}
        {(r.target_date || r.due_date) && <time>{r.target_date || r.due_date}</time>}
        <span className="entry-open" aria-hidden="true">›</span></button></li>)}</ul>}</>}
    {editing !== undefined && <Editor kind={kind} row={editing} close={() => setEditing(undefined)} saved={save}
      removed={id => {setRows(old => old.filter(r => r.id !== id)); setEditing(undefined); setNotice('Запись удалена.');}}/>}
  </section>;
}

export function Library({kind}: {kind:Kind}) {
  return <div className="workspace library"><aside className="library-side">
    <div className="brand"><span className="book" aria-hidden="true"><i/><b/></span><span>Контекст</span></div>
    <a className="return-chat" href="#chat">← К чату</a><h2>База знаний</h2>
    <div className="library-links">{(Object.keys(sections) as Kind[]).map(key =>
      <a key={key} href={'#knowledge/'+key} aria-current={kind === key ? 'page' : undefined}>{sections[key][0]}</a>)}</div>
  </aside><main><header><a href="#chat">Чаты</a><small>/</small><strong>База знаний</strong></header>
    <select className="mobile-section" aria-label="Раздел базы знаний" value={kind}
      onChange={e => {location.hash = 'knowledge/' + e.target.value;}}>
      {(Object.keys(sections) as Kind[]).map(key => <option key={key} value={key}>{sections[key][0]}</option>)}</select>
    <Collection key={kind} kind={kind}/></main></div>;
}
