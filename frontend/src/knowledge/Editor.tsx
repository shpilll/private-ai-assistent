import React, {useEffect, useRef, useState} from 'react';
import {api} from '../api';
import {IndexState} from './IndexState';
import {errorText, fileData, listEntries, priorities, sections, statuses, type Entry, type Kind, type LinkKind} from './records';

type Props = { kind: Kind; row: Entry | null; close: () => void;
  saved: (row:Entry) => void; removed: (id:number) => void };
const linkFields = [
  ['categories','category_id','Категория'], ['projects','project_id','Проект'], ['goals','goal_id','Цель']
] as const;

export function Editor({kind, row, close, saved, removed}: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [draft, setDraft] = useState<Partial<Entry>>(row ?? {title:'', status:'todo', priority:'normal'});
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [confirm, setConfirm] = useState(false);
  const [links, setLinks] = useState<Partial<Record<LinkKind, Entry[]>>>({});
  const [linkError, setLinkError] = useState('');
  const [reload, setReload] = useState(0);
  const [replaceMode, setReplaceMode] = useState(false);
  const isDoc = kind === 'documents';
  const isNote = kind === 'notes';
  const isTask = kind === 'tasks';
  const hasDescription = isTask || kind === 'goals' || kind === 'projects';
  const applicable = linkFields.filter(([key]) =>
    key === 'categories' ? kind !== 'categories' : key === 'projects' ? isTask || isNote : isTask);
  const endpoint = '/api/' + kind + (row ? '/' + row.id : '');
  const waiting = applicable.some(([key]) => !links[key]);
  useEffect(() => {
    const el = dialog.current!;
    el.showModal();
    return () => el.close();
  }, []);
  useEffect(() => {
    let active = true;
    setLinkError('');
    Promise.all(applicable.map(async ([key]) => [key, await listEntries(key)] as const))
      .then(values => {if (active) setLinks(Object.fromEntries(values));})
      .catch(e => {if (active) setLinkError(errorText(e));});
    return () => {active = false;};
  }, [kind, reload]);

  function change<K extends keyof Entry>(key:K, value:Entry[K]) {
    setDraft(old => ({...old, [key]:value}));
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true); setError('');
    try {
      let result: Entry;
      if (isDoc && (!row || replaceMode)) {
        if (!file) throw new Error('Выберите файл для загрузки.');
        const category = !row && draft.category_id ? '?category_id=' + draft.category_id : '';
        result = await api<Entry>(endpoint + category, fileData(file), row ? 'PUT' : 'POST');
      } else {
        const values: Record<string, unknown> = {};
        if (!isDoc) values.title = draft.title?.trim();
        if (isNote) values.body = draft.body;
        if (hasDescription) values.description = draft.description ?? '';
        if (isTask) Object.assign(values, {status:draft.status, priority:draft.priority, due_date:draft.due_date || null});
        if (kind === 'goals') values.target_date = draft.target_date || null;
        for (const [, field] of applicable) values[field] = draft[field] ?? null;
        if (row && !isDoc) {
          for (const key of Object.keys(values)) if (row[key as keyof Entry] === values[key]) delete values[key];
        }
        result = await api<Entry>(endpoint, values, row ? 'PATCH' : 'POST');
      }
      saved(result);
    } catch (e) {setError(errorText(e));}
    finally {setBusy(false);}
  }
  async function erase() {
    if (!row || busy) return;
    setBusy(true); setError('');
    try {await api(endpoint, undefined, 'DELETE'); removed(row.id);}
    catch (e) {setError(errorText(e));}
    finally {setBusy(false);}
  }
  const name = row?.title ?? sections[kind][1];
  return <dialog ref={dialog} className="entry-dialog" aria-labelledby="editor-title"
    onCancel={e => {e.preventDefault(); if (!busy) close();}}>
    <div className="dialog-head"><h2 id="editor-title">{confirm ? 'Удалить запись?' : name}</h2>
      <button type="button" disabled={busy} onClick={close} aria-label="Закрыть">×</button></div>
    {confirm ? <div className="delete-box"><p>«{row?.title}» будет удалена из базы знаний.</p>
      <div className="actions"><button disabled={busy} onClick={() => setConfirm(false)}>Отмена</button>
      <button className="danger" disabled={busy} onClick={erase}>Подтвердить удаление</button></div></div>
    : <form className="entry-form" onSubmit={submit}><fieldset disabled={busy}>
      {isDoc && row && <div className="doc-tools">
        <a target="_blank" rel="noreferrer" href={endpoint+'/content'}>Открыть текст ↗</a>
        <button type="button" onClick={() => {setReplaceMode(!replaceMode); setFile(null); setError('');}}>
          {replaceMode ? 'К свойствам' : 'Заменить файл'}</button></div>}
      {isDoc && (!row || replaceMode) && <label>Текстовый файл (.txt, UTF-8, до 1 МиБ)
        <input required type="file" accept=".txt,text/plain" onChange={e => setFile(e.target.files?.[0] ?? null)}/></label>}
      {!isDoc && <label>Название<input autoFocus required maxLength={200} value={draft.title ?? ''}
        onChange={e => change('title', e.target.value)}/></label>}
      {(isNote || hasDescription) && <label>{isNote ? 'Текст заметки' : 'Описание'}
        <textarea rows={isNote ? 7 : 3} required={isNote} value={(isNote ? draft.body : draft.description) ?? ''}
          onChange={e => change(isNote ? 'body' : 'description', e.target.value)}/></label>}
      {isTask && <div className="field-grid"><label>Статус<select value={draft.status} onChange={e => change('status',e.target.value)}>
        {Object.entries(statuses).map(([v,label]) => <option key={v} value={v}>{label}</option>)}</select></label>
        <label>Приоритет<select value={draft.priority} onChange={e => change('priority',e.target.value)}>
        {Object.entries(priorities).map(([v,label]) => <option key={v} value={v}>{label}</option>)}</select></label></div>}
      {(isTask || kind === 'goals') && <label>{isTask ? 'Срок задачи' : 'Целевая дата'}<input type="date"
        value={(isTask ? draft.due_date : draft.target_date) || ''}
        onChange={e => change(isTask ? 'due_date' : 'target_date',e.target.value || null)}/></label>}
      {!replaceMode && <div className="field-grid">{applicable.map(([source, field, label]) =>
        <label key={field}>{label}<select disabled={!links[source]} value={draft[field] ?? ''}
          onChange={e => change(field, e.target.value ? Number(e.target.value) : null)}>
          <option value="">Без привязки</option>{links[source]?.map(r => <option key={r.id} value={r.id}>{r.title} · #{r.id}</option>)}
        </select></label>)}</div>}
      {linkError && <div role="alert">{linkError} <button type="button" onClick={() => setReload(n => n+1)}>Повторить</button></div>}
      {row && (isNote || isDoc) && <IndexState path={`/api/index/${kind}/${row.id}`} revision={row.id}/>}
      <div className="actions">{row && <button className="remove" type="button" onClick={() => setConfirm(true)}>Удалить</button>}
        <button type="button" onClick={close}>Отмена</button><button className="primary" disabled={!replaceMode && waiting}>
        {busy ? 'Сохранение…' : replaceMode ? 'Сохранить замену' : isDoc && !row ? 'Загрузить' : 'Сохранить'}</button></div>
    </fieldset></form>}
    {error && <div className="error" role="alert">{error}</div>}
  </dialog>;
}
