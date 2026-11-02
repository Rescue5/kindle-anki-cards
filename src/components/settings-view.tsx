import * as React from "react";
import { Check, KeyRound, Loader2, PlugZap, RefreshCw, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useLlmConfig } from "@/features/llm/use-llm-config";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { PageHead } from "@/components/page-head";
import { PencilRule } from "@/components/sketch/sketch";
import { callBackend } from "@/lib/backend";
import type { AppSettings } from "@/types";

type SettingsSectionProps = {
  title: string;
  description: string;
  children: React.ReactNode;
};

/** A settings group: what it is about on the left, the controls on the right. */
function SettingsSection({ title, description, children }: SettingsSectionProps) {
  return (
    <section className="settings-section">
      <PencilRule variant={1} />
      <div className="settings-section-grid">
        <div className="settings-section-head">
          <h2>{title}</h2>
          <p>{description}</p>
        </div>
        <div className="settings-section-body">{children}</div>
      </div>
    </section>
  );
}

/** A switch with its label and explanation, laid out as one row. */
function SwitchRow({ id, label, hint, checked, onChange, disabled }: { id: string; label: string; hint: string; checked: boolean; onChange: (value: boolean) => void; disabled?: boolean }) {
  return (
    <div className="settings-switch-row">
      <div>
        <label htmlFor={id}>{label}</label>
        <p>{hint}</p>
      </div>
      <Switch id={id} checked={checked} onCheckedChange={onChange} disabled={disabled} aria-label={label} />
    </div>
  );
}

type FieldProps = {
  label: string;
  hint?: string;
  children: React.ReactNode;
};

function Field({ label, hint, children }: FieldProps) {
  return (
    <label className="settings-field">
      <span className="settings-field-label">{label}</span>
      {children}
      {hint ? <span className="settings-field-hint">{hint}</span> : null}
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


  return (
    <main className="reading-page app-scrollbar">
      <div className="screen-page settings-page">
        <PageHead title="Настройки" lede="Внешний вид, перевод через ИИ и синхронизация с Obsidian.">
          {saving ? <span className="home-note">сохраняем…</span> : saveError ? <span className="screen-error-note" role="alert">Ошибка сохранения: {saveError}</span> : <span className="reading-count">Изменения сохраняются сразу</span>}
        </PageHead>

        <SettingsSection title="Общие" description="Тема повторяет выключатель внизу меню; экспорт — формат кнопки на экране слов.">
          <div className="settings-grid">
            <Field label="Тема">
              <Select value={settings.theme} onChange={(event) => update("theme", event.target.value as AppSettings["theme"])}>
                <option value="system">Как в системе</option>
                <option value="light">Дневной свет</option>
                <option value="dark">Ночной свет</option>
              </Select>
            </Field>
            <Field label="Формат экспорта по умолчанию">
              <Select value={settings.default_export_format} onChange={(event) => update("default_export_format", event.target.value as AppSettings["default_export_format"])}>
                <option value="anki">Anki</option>
                <option value="quizlet">Quizlet</option>
              </Select>
            </Field>
          </div>
        </SettingsSection>

        <LlmSettingsSection settings={settings} update={update} persistPatch={persistPatch} />

        <SettingsSection title="Obsidian" description="Подходящие слова дописываются в хранилище Obsidian; сами заметки приложение не читает как источник.">
          <SwitchRow id="obsidian-enabled-switch" label="Синхронизация с Obsidian" hint="Добавлять подходящие слова из библиотеки в Obsidian." checked={settings.obsidian_sync_enabled} onChange={(value) => update("obsidian_sync_enabled", value)} />
          <div className="settings-grid">
            <Field label="Путь к хранилищу Obsidian" hint="Абсолютный путь до папки vault">
              <Input value={settings.obsidian_vault_path} onChange={(event) => update("obsidian_vault_path", event.target.value)} placeholder="/Users/…/Documents/Obsidian Vault" />
            </Field>
            <Field label="Папка для карточек" hint="Папка внутри vault">
              <Input value={settings.obsidian_cards_path} onChange={(event) => update("obsidian_cards_path", event.target.value)} placeholder="Kindle Cards" />
            </Field>
          </div>
          <SwitchRow id="obsidian-backup-switch" label="Создавать резервную копию" hint="Перед синхронизацией сохранить текущее состояние папки карточек." checked={settings.obsidian_backup_enabled} onChange={(value) => update("obsidian_backup_enabled", value)} />
        </SettingsSection>
      </div>
    </main>
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
    <SettingsSection title="Перевод через ИИ" description="Без ИИ значения берутся из встроенного Викисловаря. ИИ переводит слово именно в том смысле, что в книге, и добавляет определение и пример. Облачному провайдеру уходят только слово и предложения из книги; локальные модели работают без интернета.">
      <SwitchRow id="llm-enabled-switch" label="Переводить слова по контексту" hint="Нужен ключ облачного провайдера или локальная модель в LM Studio или Ollama." checked={settings.llm_enabled} onChange={(value) => update("llm_enabled", value)} />

      {llm.configError ? <p className="screen-error-note">Не удалось загрузить провайдеров: {llm.configError}</p> : null}

      <div className="settings-grid">
        <Field label="Провайдер" hint={preset?.hint}>
          <Select value={settings.llm_provider} onChange={(event) => llm.selectProvider(event.target.value)} disabled={!llm.config}>
            <option value="">Не выбран</option>
            {llm.config?.presets.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
          </Select>
        </Field>

        <Field label="Модель" hint={llm.models.status === "error" ? llm.models.error : preset?.default_model ? `По умолчанию: ${preset.default_model}` : "Выберите из списка или впишите название"}>
          <div className="settings-inline">
            <Input
              list="llm-model-options"
              value={settings.llm_model}
              onChange={(event) => update("llm_model", event.target.value)}
              placeholder={preset?.default_model || "название модели"}
              disabled={!preset}
            />
            <datalist id="llm-model-options">{models.map((model) => <option key={model} value={model} />)}</datalist>
            <Button type="button" variant="secondary" size="sm" className="shrink-0" onClick={() => void llm.loadModels()} disabled={!llm.ready || llm.models.status === "running"} title="Загрузить список моделей провайдера">
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
              <div className="settings-inline">
                <Input type="password" autoComplete="off" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder="Вставьте ключ" />
                <Button type="button" size="sm" className="shrink-0" onClick={() => void saveKey()} disabled={!apiKey.trim() || llm.keyState.status === "running"}>
                  {llm.keyState.status === "running" ? <Loader2 size={14} className="animate-spin" /> : <KeyRound size={14} />}
                  Сохранить
                </Button>
              </div>
            ) : (
              <div className="settings-key-saved">
                <span><Check size={15} /> Ключ сохранён</span>
                <span className="settings-inline">
                  <Button type="button" variant="ghost" size="sm" onClick={() => setReplacingKey(true)}>Заменить</Button>
                  <Button type="button" variant="ghost" size="sm" onClick={() => void llm.deleteKey()} disabled={llm.keyState.status === "running"} aria-label="Удалить ключ"><Trash2 size={14} /></Button>
                </span>
              </div>
            )}
            {llm.keyState.status === "error" ? <span className="screen-error-note">{llm.keyState.error}</span> : null}
          </Field>
        ) : null}
      </div>

      <div className="settings-test">
        <Button type="button" variant="secondary" size="sm" onClick={() => void llm.runTest()} disabled={!llm.ready || llm.test.status === "running"}>
          {llm.test.status === "running" ? <Loader2 size={14} className="animate-spin" /> : <PlugZap size={14} />}
          {llm.test.status === "running" ? "Проверяем…" : "Проверить подключение"}
        </Button>
        <p className="settings-test-result" aria-live="polite">
          {llm.test.status === "idle" ? <span className="text-muted-foreground">{llm.ready ? "Переведём одно пробное слово — ваши данные не отправляются." : "Выберите провайдера и добавьте ключ."}</span> : null}
          {llm.test.status === "running" ? <span className="text-muted-foreground">Локальной модели может понадобиться до минуты.</span> : null}
          {llm.test.status === "done" ? <span className="text-success">Работает: {llm.test.value.model}, {llm.test.value.seconds} с. glimpse → {llm.test.value.sample.meaning_ru}</span> : null}
          {llm.test.status === "error" ? <span className="text-destructive">{llm.test.error}</span> : null}
        </p>
      </div>

      <SwitchRow id="llm-auto-switch" label="Переводить новые слова автоматически" hint="Иначе — кнопкой «Перевести» на экране слов. Каждое слово отправляется провайдеру только один раз." checked={settings.llm_auto_enrich} onChange={(value) => update("llm_auto_enrich", value)} disabled={!settings.llm_enabled} />
    </SettingsSection>
  );
}
