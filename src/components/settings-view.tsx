import * as React from "react";
import { Brain, Check, KeyRound, Loader2, Palette, PlugZap, RefreshCw, ScrollText, Shield, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useLlmConfig } from "@/features/llm/use-llm-config";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { callBackend } from "@/lib/backend";
import type { AppSettings } from "@/types";

type SettingsSectionProps = {
  icon: React.ElementType;
  title: string;
  children: React.ReactNode;
};

function SettingsSection({ icon: Icon, title, children }: SettingsSectionProps) {
  return (
    <Card className="overflow-hidden">
      <CardHeader className="border-b border-line bg-panel-raised/40">
        <div className="flex items-center gap-2.5">
          <div className="grid h-8 w-8 place-items-center rounded-[8px] bg-secondary text-primary">
            <Icon size={16} />
          </div>
          <CardTitle>{title}</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">{children}</CardContent>
    </Card>
  );
}

type FieldProps = {
  label: string;
  hint?: string;
  children: React.ReactNode;
};

function Field({ label, hint, children }: FieldProps) {
  return (
    <label className="block space-y-1.5">
      <span className="block text-sm font-medium">{label}</span>
      {children}
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </label>
  );
}

type SettingsViewProps = {
  settings: AppSettings;
  onChange: (settings: AppSettings) => void;
};

export function SettingsView({ settings, onChange }: SettingsViewProps) {
  const [saving, setSaving] = React.useState(false);
  const [saveError, setSaveError] = React.useState("");

  async function persist(next: AppSettings) {
    onChange(next);
    setSaving(true);
    setSaveError("");
    try {
      await callBackend<{ saved: boolean }>("save_settings", { settings: next });
    } catch (error) {
      setSaveError(String(error));
    } finally {
      setSaving(false);
    }
  }

  function update<K extends keyof AppSettings>(key: K, value: AppSettings[K]) {
    const next = { ...settings, [key]: value };
    void persist(next);
  }

  function persistPatch(patch: Partial<AppSettings>) {
    void persist({ ...settings, ...patch });
  }

  React.useEffect(() => {
    const root = document.documentElement;
    const { theme } = settings;
    root.classList.remove("light", "dark");
    if (theme === "system") {
      const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      root.classList.add(prefersDark ? "dark" : "light");
    } else {
      root.classList.add(theme);
    }
  }, [settings.theme]);

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-background/35">
      <header className="flex-none border-b border-line px-6 py-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-[22px] font-semibold leading-7">Настройки</h1>
            <p className="mt-1 text-sm text-muted-foreground">Внешний вид, перевод через ИИ и синхронизация с Obsidian</p>
          </div>
          {saving ? (
            <span className="text-xs text-muted-foreground">Сохранение…</span>
          ) : saveError ? (
            <span className="text-xs text-destructive">Ошибка сохранения: {saveError}</span>
          ) : null}
        </div>
      </header>
      <div className="app-scrollbar min-h-0 flex-1 space-y-5 overflow-y-auto p-6">
        <SettingsSection icon={Palette} title="Общие">
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Тема">
              <Select
                value={settings.theme}
                onChange={(event) => update("theme", event.target.value as AppSettings["theme"])}
              >
                <option value="system">Системная</option>
                <option value="light">Светлая</option>
                <option value="dark">Тёмная</option>
              </Select>
            </Field>
            <Field label="Формат экспорта по умолчанию">
              <Select
                value={settings.default_export_format}
                onChange={(event) =>
                  update("default_export_format", event.target.value as AppSettings["default_export_format"])
                }
              >
                <option value="anki">Anki</option>
                <option value="quizlet">Quizlet</option>
              </Select>
            </Field>
          </div>
        </SettingsSection>

        <LlmSettingsSection settings={settings} update={update} persistPatch={persistPatch} />

        <SettingsSection icon={ScrollText} title="Obsidian">
          <div
            className={`flex items-center justify-between gap-4 rounded-[10px] border px-4 py-3 text-sm ${
              settings.obsidian_sync_enabled
                ? "border-purple-700/25 bg-purple-700/5 text-purple-800"
                : "border-line bg-panel-raised/40 text-muted-foreground"
            }`}
          >
            <div className="flex items-center gap-2.5">
              <span className={`h-2 w-2 rounded-full ${settings.obsidian_sync_enabled ? "bg-purple-400" : "bg-muted-foreground"}`} />
              <div>
                <label htmlFor="obsidian-enabled-switch" className="font-medium">Синхронизация с Obsidian</label>
                <p className="mt-0.5 text-xs opacity-75">Добавлять подходящие слова из библиотеки в Obsidian.</p>
              </div>
            </div>
            <Switch
              id="obsidian-enabled-switch"
              checked={settings.obsidian_sync_enabled}
              onCheckedChange={(value) => update("obsidian_sync_enabled", value)}
              aria-label="Включить синхронизацию с Obsidian"
            />
          </div>
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Путь к хранилищу Obsidian" hint="Абсолютный путь до папки vault">
              <Input
                value={settings.obsidian_vault_path}
                onChange={(event) => update("obsidian_vault_path", event.target.value)}
                placeholder="/Users/…/Documents/Obsidian Vault"
              />
            </Field>
            <Field label="Папка для карточек" hint="Папка внутри vault">
              <Input
                value={settings.obsidian_cards_path}
                onChange={(event) => update("obsidian_cards_path", event.target.value)}
                placeholder="Kindle Cards"
              />
            </Field>
          </div>
          <div className="flex items-center gap-3 rounded-[10px] border border-line bg-panel-raised/40 p-3 transition hover:bg-panel-raised">
            <Switch
              id="obsidian-backup-switch"
              checked={settings.obsidian_backup_enabled}
              onCheckedChange={(value) => update("obsidian_backup_enabled", value)}
              aria-label="Создавать резервную копию"
            />
            <div>
              <label htmlFor="obsidian-backup-switch" className="text-sm font-medium">
                Создавать резервную копию
              </label>
              <p className="text-xs text-muted-foreground">Перед синхронизацией сохранить текущее состояние папки карточек.</p>
            </div>
          </div>
        </SettingsSection>
      </div>
    </div>
  );
}

type LlmSettingsSectionProps = {
  settings: AppSettings;
  update: <K extends keyof AppSettings>(key: K, value: AppSettings[K]) => void;
  persistPatch: (patch: Partial<AppSettings>) => void;
};

function LlmSettingsSection({ settings, update, persistPatch }: LlmSettingsSectionProps) {
  const llm = useLlmConfig(settings, persistPatch);
  const [apiKey, setApiKey] = React.useState("");
  const [replacingKey, setReplacingKey] = React.useState(false);
  const preset = llm.preset;
  const showKeyInput = Boolean(preset?.needs_key) && (!llm.hasKey || replacingKey);
  const models = llm.models.status === "done" ? llm.models.value : [];

  async function saveKey() {
    await llm.saveKey(apiKey);
    setApiKey("");
    setReplacingKey(false);
  }

  return (
    <SettingsSection icon={Brain} title="Перевод через ИИ">
      <div className="flex items-start justify-between gap-4 rounded-[10px] border border-line bg-panel-raised/40 p-4">
        <div className="flex items-start gap-3">
          <div className="grid h-9 w-9 place-items-center rounded-[8px] bg-secondary text-primary">
            <Shield size={16} />
          </div>
          <div>
            <label htmlFor="llm-enabled-switch" className="text-sm font-medium">Переводить слова по контексту</label>
            <p className="mt-0.5 max-w-[520px] text-xs leading-5 text-muted-foreground">
              ИИ определяет значение слова в предложении из книги и добавляет в карточку перевод, определение и пример.
              Облачному провайдеру отправляются только слово и предложения из книги; локальные модели работают без интернета.
            </p>
          </div>
        </div>
        <Switch id="llm-enabled-switch" checked={settings.llm_enabled} onCheckedChange={(value) => update("llm_enabled", value)} aria-label="Переводить слова по контексту" />
      </div>

      {llm.configError ? <p className="text-xs text-destructive">Не удалось загрузить провайдеров: {llm.configError}</p> : null}

      <div className="grid gap-5 sm:grid-cols-2">
        <Field label="Провайдер" hint={preset?.hint}>
          <Select value={settings.llm_provider} onChange={(event) => llm.selectProvider(event.target.value)} disabled={!llm.config}>
            <option value="">Не выбран</option>
            {llm.config?.presets.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
          </Select>
        </Field>

        <Field label="Модель" hint={llm.models.status === "error" ? llm.models.error : preset?.default_model ? `По умолчанию: ${preset.default_model}` : "Выберите из списка или впишите название"}>
          <div className="flex gap-2">
            <Input
              list="llm-model-options"
              value={settings.llm_model}
              onChange={(event) => update("llm_model", event.target.value)}
              placeholder={preset?.default_model || "название модели"}
              disabled={!preset}
            />
            <datalist id="llm-model-options">{models.map((model) => <option key={model} value={model} />)}</datalist>
            <Button type="button" variant="secondary" size="sm" className="h-9 shrink-0" onClick={() => void llm.loadModels()} disabled={!llm.ready || llm.models.status === "running"} title="Загрузить список моделей провайдера">
              {llm.models.status === "running" ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
              Список
            </Button>
          </div>
        </Field>

        {preset?.id === "custom" ? (
          <Field label="Адрес API" hint="OpenAI-совместимый адрес, например https://example.com/v1">
            <Input value={settings.llm_base_url} onChange={(event) => update("llm_base_url", event.target.value)} placeholder="https://…/v1" />
          </Field>
        ) : null}

        {preset?.needs_key ? (
          <Field label="Ключ API" hint="Хранится в системном хранилище паролей, а не в файлах приложения">
            {showKeyInput ? (
              <div className="flex gap-2">
                <Input type="password" autoComplete="off" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder="Вставьте ключ" />
                <Button type="button" size="sm" className="h-9 shrink-0" onClick={() => void saveKey()} disabled={!apiKey.trim() || llm.keyState.status === "running"}>
                  {llm.keyState.status === "running" ? <Loader2 size={14} className="animate-spin" /> : <KeyRound size={14} />}
                  Сохранить
                </Button>
              </div>
            ) : (
              <div className="flex h-9 items-center justify-between gap-2 rounded-[10px] border border-line bg-panel-raised/40 px-3 text-sm">
                <span className="flex items-center gap-2 text-success"><Check size={14} /> Ключ сохранён</span>
                <span className="flex items-center gap-1">
                  <Button type="button" variant="ghost" size="sm" onClick={() => setReplacingKey(true)}>Заменить</Button>
                  <Button type="button" variant="ghost" size="sm" onClick={() => void llm.deleteKey()} disabled={llm.keyState.status === "running"} aria-label="Удалить ключ"><Trash2 size={14} /></Button>
                </span>
              </div>
            )}
            {llm.keyState.status === "error" ? <p className="text-xs text-destructive">{llm.keyState.error}</p> : null}
          </Field>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-[10px] border border-line bg-panel-raised/40 p-3">
        <Button type="button" variant="secondary" size="sm" onClick={() => void llm.runTest()} disabled={!llm.ready || llm.test.status === "running"}>
          {llm.test.status === "running" ? <Loader2 size={14} className="animate-spin" /> : <PlugZap size={14} />}
          {llm.test.status === "running" ? "Проверяем…" : "Проверить подключение"}
        </Button>
        <p className="min-w-0 flex-1 text-xs leading-5" aria-live="polite">
          {llm.test.status === "idle" ? <span className="text-muted-foreground">{llm.ready ? "Переведём одно пробное слово — ваши данные не отправляются." : "Выберите провайдера и добавьте ключ."}</span> : null}
          {llm.test.status === "running" ? <span className="text-muted-foreground">Локальной модели может понадобиться до минуты.</span> : null}
          {llm.test.status === "done" ? <span className="text-success">Работает: {llm.test.value.model}, {llm.test.value.seconds} с. glimpse → {llm.test.value.sample.meaning_ru}</span> : null}
          {llm.test.status === "error" ? <span className="text-destructive">{llm.test.error}</span> : null}
        </p>
      </div>

      <div className="flex items-center gap-3 rounded-[10px] border border-line bg-panel-raised/40 p-3 transition hover:bg-panel-raised">
        <Switch id="llm-auto-switch" checked={settings.llm_auto_enrich} onCheckedChange={(value) => update("llm_auto_enrich", value)} disabled={!settings.llm_enabled} aria-label="Переводить новые слова автоматически" />
        <div>
          <label htmlFor="llm-auto-switch" className="text-sm font-medium">Переводить новые слова автоматически</label>
          <p className="text-xs text-muted-foreground">Иначе — кнопкой «Перевести» на экране слов. Каждое слово отправляется провайдеру только один раз.</p>
        </div>
      </div>
    </SettingsSection>
  );
}
