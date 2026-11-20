import { BridgeError, callBackend } from "@/lib/backend";
import { ERROR_TEXTS, type DecisionValue, type LibraryResult, type SaveCardEditResult, type SetDecisionResult } from "@/types";

export type CardChanges = { meaning_ru?: string; example_occurrence_id?: string };

/** Versions cover the whole snapshot, including ranks of words other than the edited one. */
export class LibraryEdits {
  private version = 0;
  private read = 0;
  private session = 0;
  private activeWrite = false;
  private pendingWrites = 0;
  private writes: Promise<void> = Promise.resolve();

  invalidate() { this.version += 1; }
  getVersion() { return this.version; }
  acceptsVersion(version: number) { return !this.activeWrite && version === this.version; }
  switchLibrary() { this.session += 1; this.invalidate(); }
  isWriting() { return this.pendingWrites > 0; }
  beginRead() { return { version: this.version, read: ++this.read }; }
  accepts(ticket: ReturnType<LibraryEdits["beginRead"]>) {
    return !this.activeWrite && ticket.version === this.version && ticket.read === this.read;
  }

  constructor(
    private editable: (id: string) => boolean,
    private apply: (library: LibraryResult) => void,
    private applyEntry: (result: SaveCardEditResult | SetDecisionResult) => void,
  ) {}

  saveCardEdit = (id: string, changes: CardChanges) =>
    this.write("save_card_edit", id, changes);

  setWordDecision = (id: string, decision: DecisionValue | null) =>
    this.write("set_decision", id, { decision });

  private write(action: string, id: string, changes: CardChanges | { decision: DecisionValue | null }): Promise<void> {
    if (!this.editable(id)) return Promise.reject(new Error("Дождитесь загрузки своей библиотеки и откройте слово заново"));
    const session = this.session;
    this.pendingWrites += 1;
    this.invalidate();
    const saved = this.writes.then(async () => {
      if (session !== this.session || !this.editable(id)) throw new Error("Библиотека изменилась. Откройте слово заново");
      this.invalidate();
      this.activeWrite = true;
      try {
        const result = await callBackend<SaveCardEditResult | SetDecisionResult>(action, { lexeme_id: id, ...changes });
        if (session !== this.session) return;
        // Invalidate snapshots captured while the write was running, too.
        this.invalidate();
        this.activeWrite = false;
        this.applyEntry(result);
        const ticket = this.beginRead();
        try {
          const library = await callBackend<LibraryResult>("load_library", {});
          if (this.accepts(ticket) && session === this.session) this.apply(library);
        } catch {
          throw new Error("Правка сохранена. Не удалось обновить список слов. Обновите библиотеку");
        }
      } catch (error) {
        if (error instanceof BridgeError) throw new BridgeError(error.code ? ERROR_TEXTS[error.code] : error.message, error.code);
        if (error instanceof Error && /[а-яё]/i.test(error.message)) throw error;
        throw new Error(action === "save_card_edit" ? "Не удалось сохранить карточку. Попробуйте снова" : "Не удалось сохранить решение. Попробуйте снова");
      } finally {
        this.activeWrite = false;
      }
    }).finally(() => { this.pendingWrites -= 1; });
    this.writes = saved.catch(() => undefined);
    return saved;
  }
}
