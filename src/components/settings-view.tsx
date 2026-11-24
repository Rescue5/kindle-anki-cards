import * as React from "react";
import { Check, KeyRound, Loader2, PlugZap, RefreshCw, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useLlmConfig } from "@/features/llm/use-llm-config";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { PageHead } from "@/components/page-head";
import { PencilRule } from "@/components/sketch/sketch";
import { obsidianConfig, type ObsidianCheck } from "@/features/library/load-library";
import { EXPORT_BATCH_SIZE_DEFAULT, type AppSettings, type Operation } from "@/types";

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
  onSave: (patch: Partial<AppSettings>) => Promise<void>;
  saving: boolean;
  demo: boolean;
  busy: boolean;
  obsidianCheck: ObsidianCheck;
  operation: Operation;
  onCheckObsidian: () => void;
  onSyncObsidian: () => void;
};

export function SettingsView({ settings, onSave, saving, demo, busy, obsidianCheck, operation, onCheckObsidian, onSyncObsidian }: SettingsViewProps) {
  const [saveError, setSaveError] = React.useState("");
  const latestSave = React.useRef(0);
  const batchSize = settings.export_batch_size ?? EXPORT_BATCH_SIZE_DEFAULT;
  const batchSizes = [5, 10, 15, 20, 25, 30, 40, 50, 75, 100];
  if (!batchSizes.includes(batchSize)) batchSizes.push(batchSize);
  batchSizes.sort((left, right) => left - right);

  async function persist(patch: Partial<AppSettings>) {
    const revision = ++latestSave.current;
    setSaveError("");
    try {
      await onSave(patch);
    } catch (error) {
      if (revision === latestSave.current) setSaveError(String(error));
    }
  }

  function update<K extends keyof AppSettings>(key: K, value: AppSettings[K]) {
    void persist({ [key]: value });
  }

  function persistPatch(patch: Partial<AppSettings>) {
    void persist(patch);
  }

  const obsidianRunning = operation.kind === "obsidian" && operation.status === "running";
  const obsidianDisabled = !settings.obsidian_sync_enabled || !obsidianConfig(settings);
  const obsidianResult = operation.kind === "obsidian" && (operation.status === "completed" || operation.status === "error")
    ? (operation.error || operation.message)
    : "";

  return (
    <main className="reading-page app-scrollbar">
      <div className="screen-page settings-page">
        <PageHead title="Настройки" lede="Внешний вид, экспорт, перевод через ИИ и Obsidian.">
          {saving ? <span className="home-note">сохраняем…</span> : saveError ? <span className="screen-error-note" role="alert">Ошибка сохранения: {saveError}</span> : <span className="reading-count">Настройки сохраняются автоматически</span>}
        </PageHead>

        <SettingsSection title="Общие" description="Выберите освещение и настройте выгрузку слов с главной.">
          <div className="settings-grid">
            <Field label="Тема">
              <Select value={settings.theme} onChange={(event) => update("theme", event.target.value as AppSettings["theme"])}>
                <option value="system">Как в системе</option>
                <option value="light">Дневной свет</option>
                <option value="dark">Ночной свет</option>
              </Select>
            </Field>
            <Field label="Куда выгружать слова" hint="Выбор действует на следующие выгрузки.">
              <Select value={settings.export_destination ?? "anki"} onChange={(event) => update("export_destination", event.target.value === "csv" ? "csv" : "anki")}>
                {settings.export_destination === "obsidian" ? <option value="obsidian" disabled>Выберите Anki или файл</option> : null}
                <option value="anki">Anki</option>
                <option value="csv">Файл TSV для Quizlet и таблиц</option>
              </Select>
            </Field>
            <Field label="Порция новых слов по умолчанию" hint="На Главной можно указать другое число или выбрать всю библиотеку.">
              <Select value={batchSize} onChange={(event) => update("export_batch_size", Number(event.target.value))}>
                {batchSizes.map((size) => <option key={size} value={size}>{size}</option>)}
              </Select>
            </Field>
          </div>
        </SettingsSection>

        <LlmSettingsSection settings={settings} update={update} persistPatch={persistPatch} />

        <SettingsSection title="Obsidian" description="Приложение сверяет существующие карточки. По кнопке синхронизации добавляет подходящие слова из библиотеки.">
          <SwitchRow id="obsidian-enabled-switch" label="Синхронизация с Obsidian" hint="Добавлять подходящие слова из библиотеки в Obsidian." checked={settings.obsidian_sync_enabled} disabled={obsidianRunning} onChange={(value) => update("obsidian_sync_enabled", value)} />
          <div className="settings-grid">
            <Field label="Путь к хранилищу Obsidian" hint="Абсолютный путь до папки vault">
              <Input key={settings.obsidian_vault_path} defaultValue={settings.obsidian_vault_path} disabled={obsidianRunning} onBlur={(event) => {
                const value = event.target.value.trim();
                if (value !== settings.obsidian_vault_path) update("obsidian_vault_path", value);
              }} placeholder="Путь к папке Obsidian" />
            </Field>
            <Field label="Папка для карточек" hint="Папка внутри vault">
              <Input key={settings.obsidian_cards_path} defaultValue={settings.obsidian_cards_path} disabled={obsidianRunning} onBlur={(event) => {
                const value = event.target.value.trim();
                if (value !== settings.obsidian_cards_path) update("obsidian_cards_path", value);
              }} placeholder="Kindle Cards" />
            </Field>
          </div>
          <SwitchRow id="obsidian-backup-switch" label="Создавать резервную копию" hint="Перед синхронизацией сохранить текущее состояние папки карточек." checked={settings.obsidian_backup_enabled} disabled={obsidianRunning} onChange={(value) => update("obsidian_backup_enabled", value)} />
          {settings.obsidian_sync_enabled ? (
            <div>
              <Button type="button" variant="secondary" size="sm" onClick={onSyncObsidian} disabled={demo || busy || saving || obsidianDisabled || obsidianCheck.status !== "ready"}>
                {obsidianRunning ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : <RefreshCw size={14} aria-hidden="true" />}
                {obsidianRunning ? "Синхронизируем…" : "Синхронизировать с Obsidian"}
              </Button>
              {obsidianCheck.status === "error" ? (
                <>
                  <p className="screen-error-note" role="alert">{obsidianCheck.message}</p>
                  <Button type="button" variant="ghost" size="sm" onClick={() => onCheckObsidian()} disabled={demo || busy || saving}>Повторить проверку папки</Button>
                </>
              ) : (
                <p className={operation.kind === "obsidian" && operation.status === "error" ? "screen-error-note" : "settings-field-hint"} role={operation.kind === "obsidian" && operation.status === "error" ? "alert" : "status"}>
                  {demo ? "Закройте пример на главной, чтобы синхронизировать свою библиотеку."
                    : obsidianDisabled ? "Укажите хранилище и папку карточек."
                      : obsidianCheck.status === "checking" ? "Сверяем существующие карточки…"
                        : obsidianResult || (obsidianCheck.status === "ready" ? "Папка карточек доступна." : "")}
                </p>
              )}
            </div>
          ) : null}
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
