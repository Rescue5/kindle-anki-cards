import * as React from "react";
import { callBackend } from "@/lib/backend";
import type { AppSettings, LlmConfig, LlmPreset, LlmTestResult } from "@/types";

type AsyncState<T> = { status: "idle" } | { status: "running" } | { status: "done"; value: T } | { status: "error"; error: string };

const idle = { status: "idle" } as const;

const errorText = (error: unknown) => String(error).replace(/^Error:\s*/, "");

/**
 * Provider configuration for the settings screen. The API key goes straight to
 * the OS keychain through the backend; the frontend only learns whether one is
 * stored.
 */
export function useLlmConfig(settings: AppSettings, persist: (patch: Partial<AppSettings>) => void) {
  const [config, setConfig] = React.useState<LlmConfig | null>(null);
  const [configError, setConfigError] = React.useState("");
  const [keyState, setKeyState] = React.useState<AsyncState<true>>(idle);
  const [models, setModels] = React.useState<AsyncState<string[]>>(idle);
  const [test, setTest] = React.useState<AsyncState<LlmTestResult>>(idle);

  const refresh = React.useCallback(async () => {
    try {
      setConfig(await callBackend<LlmConfig>("llm_config", {}));
      setConfigError("");
    } catch (error) {
      setConfigError(errorText(error));
    }
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  const preset: LlmPreset | undefined = config?.presets.find((item) => item.id === settings.llm_provider);
  const hasKey = Boolean(config?.has_key[settings.llm_provider]);
  const ready = Boolean(preset) && (!preset?.needs_key || hasKey);

  const selectProvider = React.useCallback((id: string) => {
    const next = config?.presets.find((item) => item.id === id);
    persist({
      llm_provider: id,
      llm_model: next?.default_model ?? "",
      llm_base_url: next?.id === "custom" ? settings.llm_base_url : (next?.base_url ?? ""),
    });
    setModels(idle);
    setTest(idle);
  }, [config, persist, settings.llm_base_url]);

  const saveKey = React.useCallback(async (apiKey: string) => {
    setKeyState({ status: "running" });
    try {
      await callBackend("save_llm_key", { provider: settings.llm_provider, api_key: apiKey });
      setKeyState({ status: "done", value: true });
      setTest(idle);
      await refresh();
    } catch (error) {
      setKeyState({ status: "error", error: errorText(error) });
    }
  }, [refresh, settings.llm_provider]);

  const deleteKey = React.useCallback(async () => {
    setKeyState({ status: "running" });
    try {
      await callBackend("delete_llm_key", { provider: settings.llm_provider });
      setKeyState(idle);
      setTest(idle);
      await refresh();
    } catch (error) {
      setKeyState({ status: "error", error: errorText(error) });
    }
  }, [refresh, settings.llm_provider]);

  const loadModels = React.useCallback(async () => {
    setModels({ status: "running" });
    try {
      const result = await callBackend<{ models: string[] }>("list_llm_models", {
        provider: settings.llm_provider,
        model: settings.llm_model,
        base_url: settings.llm_base_url,
      });
      setModels({ status: "done", value: result.models });
    } catch (error) {
      setModels({ status: "error", error: errorText(error) });
    }
  }, [settings.llm_base_url, settings.llm_model, settings.llm_provider]);

  const runTest = React.useCallback(async () => {
    setTest({ status: "running" });
    try {
      const result = await callBackend<LlmTestResult>("test_llm", {
        provider: settings.llm_provider,
        model: settings.llm_model,
        base_url: settings.llm_base_url,
      });
      setTest({ status: "done", value: result });
    } catch (error) {
      setTest({ status: "error", error: errorText(error) });
    }
  }, [settings.llm_base_url, settings.llm_model, settings.llm_provider]);

  return { config, configError, preset, hasKey, ready, keyState, models, test, selectProvider, saveKey, deleteKey, loadModels, runTest };
}
