import {api} from '../api';

export const sections = {
  notes: ['Заметки', 'Новая заметка'], tasks: ['Задачи', 'Новая задача'],
  goals: ['Цели', 'Новая цель'], projects: ['Проекты', 'Новый проект'],
  documents: ['Документы', 'Загрузить документ'], categories: ['Категории', 'Новая категория']
} as const;
export type Kind = keyof typeof sections;
export type Entry = { id: number; title: string; description?: string; body?: string;
  category_id?: number | null; project_id?: number | null; goal_id?: number | null;
  target_date?: string | null; due_date?: string | null; status?: string; priority?: string };
export type LinkKind = 'categories' | 'projects' | 'goals';

export const statuses: Record<string,string> = {todo:'Запланирована', in_progress:'В работе', done:'Выполнена'};
export const priorities: Record<string,string> = {low:'Низкий', normal:'Обычный', high:'Высокий'};

export function activeSection(): Kind | null {
  const [prefix, kind] = location.hash.slice(1).split('/');
  if (prefix !== 'knowledge') return null;
  return Object.hasOwn(sections, kind) ? kind as Kind : 'notes';
}

export async function listEntries(kind: Kind): Promise<Entry[]> {
  const rows: Entry[] = [];
  for (let offset = 0; ; offset += 200) {
    const page = await api<Entry[]>(`/api/${kind}?limit=200&offset=${offset}`);
    rows.push(...page);
    if (page.length < 200) return rows;
  }
}

export function errorText(error: unknown) {
  return error instanceof Error ? error.message : 'Не удалось выполнить запрос.';
}

export function fileData(file: File) {
  if (!file.name.toLowerCase().endsWith('.txt') || file.size > 1024 * 1024)
    throw new Error('Выберите файл .txt до 1 МиБ.');
  const data = new FormData();
  data.set('file', file);
  return data;
}
