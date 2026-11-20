export function ruCount(value: number, one: string, few: string, many: string): string {
  const lastTwo = Math.abs(value) % 100;
  const last = lastTwo % 10;
  if (lastTwo >= 11 && lastTwo <= 14) return many;
  if (last === 1) return one;
  if (last >= 2 && last <= 4) return few;
  return many;
}

export function dateKey(value: string): string | null {
  if (!value) return null;
  const match = /^(\d{4}-\d{2}-\d{2})/.exec(value);
  if (!match) return null;
  const date = new Date(`${match[1]}T00:00:00Z`);
  return Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== match[1] ? null : match[1];
}

export function formatDate(value: string, options?: Intl.DateTimeFormatOptions): string {
  const key = dateKey(value);
  if (!key) return "Дата неизвестна";
  return new Intl.DateTimeFormat("ru-RU", { timeZone: "UTC", ...(options ?? { day: "numeric", month: "short", year: "numeric" }) }).format(
    new Date(`${key}T12:00:00Z`),
  );
}

/** A greeting for the time of day, as the home screen opens. */
export function greeting(date: Date): string {
  const hour = date.getHours();
  if (hour >= 5 && hour < 12) return "Доброе утро";
  if (hour >= 12 && hour < 18) return "Добрый день";
  if (hour >= 18 && hour < 23) return "Добрый вечер";
  return "Доброй ночи";
}

const POS_SHORT: Record<string, string> = { n: "сущ.", v: "гл.", a: "прил.", s: "прил.", r: "нареч." };

/** Dictionary-style abbreviation for a WordNet part-of-speech code, or "" when unknown. */
export function partOfSpeechShort(pos: string | undefined): string {
  return (pos && POS_SHORT[pos]) || "";
}
