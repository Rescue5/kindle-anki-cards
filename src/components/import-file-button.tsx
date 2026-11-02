import * as React from "react";
import { FileUp } from "lucide-react";
import { Button } from "@/components/ui/button";

/** Where each reader keeps its words, for people copying the file by hand. */
export const READER_FILE_HELP = "Kindle — system/vocabulary/vocab.db · KOReader на PocketBook, Kobo, Boox — koreader/settings/vocabulary_builder.sqlite3 · Kobo — .kobo/KoboReader.sqlite";

type ImportFileButtonProps = {
  onFile: (file: File) => void;
  disabled?: boolean;
  /** `drawn` is a pencil-framed button; `text` reads as an underlined link inside a sentence. */
  look?: "drawn" | "text";
  children?: React.ReactNode;
};

/** Picks a words database: Kindle vocab.db, KOReader vocabulary_builder.sqlite3 or Kobo KoboReader.sqlite. */
export function ImportFileButton({ onFile, disabled, look = "drawn", children }: ImportFileButtonProps) {
  const input = React.useRef<HTMLInputElement>(null);
  const pick = () => input.current?.click();
  return (
    <>
      <input
        ref={input}
        type="file"
        accept=".db,.sqlite,.sqlite3"
        hidden
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file) onFile(file);
        }}
      />
      {look === "text" ? (
        <button type="button" className="reading-text-button import-file-link" onClick={pick} disabled={disabled} title={READER_FILE_HELP}>
          {children ?? "выберите файл со словами"}
        </button>
      ) : (
        <Button type="button" variant="secondary" size="sm" onClick={pick} disabled={disabled} title={READER_FILE_HELP}>
          <FileUp size={15} />
          {children ?? "Файл со словами"}
        </Button>
      )}
    </>
  );
}
