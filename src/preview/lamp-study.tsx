import * as React from "react";
import { createRoot } from "react-dom/client";
import { BookOpen, Moon, Sun } from "lucide-react";
import { MascotLamp } from "@/components/light/mascot-lamp";
import { PencilDefs, PencilRule } from "@/components/sketch/sketch";
import { PencilButton, PencilLink } from "@/components/ui/pencil-controls";
import { HomeView } from "@/features/home/home-view";
import { listMeaning, shortList, type ExportUi } from "@/features/home/home-domain";
import type { LexemeRecord, LibraryResultV4 } from "@/types";
import sample from "../../tests/fixtures/bridge_library_v4.json";
import "@fontsource-variable/literata/opsz.css";
import "@fontsource-variable/literata/opsz-italic.css";
import "@fontsource-variable/caveat";
import "@/index.css";
import "@/design/night-reading.css";
import "@/design/cabinet.css";
import "@/features/reading/reading.css";
import "@/features/home/home.css";
import "./lamp-study.css";

// The same invented library used to verify the desktop contract. No device or backend is involved.
const library = sample as LibraryResultV4;
const words = shortList(library.entries, library.newBatch.ids);
const total = library.entries.length;
const foxStudy = document.documentElement.dataset.character === "fox";
const noop = () => {};

function exampleFor(entry: LexemeRecord, chosenId?: string) {
  const id = chosenId ?? entry.card?.example_occurrence_id;
  return entry.occurrences.find((item) => item.id === id) ?? entry.occurrences[0];
}

function WordExample({ entry, exampleId, onChoose, onClose }: {
  entry: LexemeRecord;
  exampleId?: string;
  onChoose: (id: string) => void;
  onClose: () => void;
}) {
  const dialog = React.useRef<HTMLDialogElement>(null);
  React.useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);
  const example = exampleFor(entry, exampleId);
  return <dialog ref={dialog} className="study-card" aria-labelledby="study-word" onClose={onClose}>
    <h2 id="study-word" lang="en">{entry.lemma}</h2>
    <p>{listMeaning(entry)}</p>
    <PencilRule />
    {entry.occurrences.length > 1 ? <label className="study-example-choice">Предложение из книги
      <select value={example?.id} onChange={(event) => onChoose(event.target.value)}>
        {entry.occurrences.map((item) => <option key={item.id} value={item.id}>{item.context}</option>)}
      </select>
    </label> : null}
    {example ? <blockquote><p lang="en">{example.context}</p><cite>{example.book_title}</cite></blockquote> : null}
    <PencilButton onClick={() => dialog.current?.close()}>К подборке</PencilButton>
  </dialog>;
}

function LampStudy() {
  const [night, setNight] = React.useState(true);
  const [motion, setMotion] = React.useState(true);
  const [processed, setProcessed] = React.useState(0);
  const [exportUi, setExportUi] = React.useState<ExportUi>({ kind: "idle" });
  const [selected, setSelected] = React.useState<LexemeRecord>();
  const [examples, setExamples] = React.useState<Record<string, string>>({});
  const preparing = processed < total;

  React.useLayoutEffect(() => {
    document.documentElement.classList.toggle("dark", night);
    document.documentElement.classList.toggle("light", !night);
  }, [night]);

  React.useEffect(() => {
    if (!preparing) return;
    let timer: number | undefined;
    const resume = () => {
      window.clearInterval(timer);
      if (!document.hidden) {
        timer = window.setInterval(() => setProcessed((count) => Math.min(total, count + 1)), 3800);
      }
    };
    resume();
    document.addEventListener("visibilitychange", resume);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", resume);
    };
  }, [preparing]);

  function exportExamples() {
    const rows = words.map((entry) => {
      const example = exampleFor(entry, examples[entry.id]);
      return [entry.lemma, listMeaning(entry), example?.context ?? "", example?.book_title ?? ""]
        .map((field) => field.replace(/[\t\r\n]+/g, " ")).join("\t");
    });
    const url = URL.createObjectURL(new Blob(["\ufeff", rows.join("\r\n")], { type: "text/tab-separated-values;charset=utf-8" }));
    const download = document.createElement("a");
    download.href = url;
    download.download = "kindle-cards-example.tsv";
    download.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1500);
    setExportUi({ kind: "done", run: { destination: "csv", exported: words.length, path: download.download, pushed: 0, runId: "study", message: "" } });
  }

  return <div className={foxStudy ? "character-study fox-study" : "character-study lamp-study"}>
    <PencilDefs />
    <header className="study-header">
      <div className="study-brand"><BookOpen size={23} aria-hidden="true" /><strong>Kindle Cards</strong></div>
      <p>{foxStudy ? "Лис-фонарщик" : "Проба маскота"} <span>·</span> пример слов</p>
      <div className="study-controls" role="group" aria-label="Настройки сцены">
        <PencilLink onClick={() => { setProcessed(preparing ? total : 0); setExportUi({ kind: "idle" }); }}>
          {preparing ? "Показать подборку" : "Повторить подготовку"}
        </PencilLink>
        <button className="study-motion" type="button" aria-pressed={motion} onClick={() => setMotion((value) => !value)}>
          <span aria-hidden="true" />{foxStudy ? "Движения лиса" : "Движения лампы"}
        </button>
        <button className="study-theme" type="button" aria-label={night ? "Включить дневной свет" : "Включить ночной свет"}
          title={night ? "Включить дневной свет" : "Включить ночной свет"} onClick={() => setNight((value) => !value)}>
          {night ? <Sun size={19} /> : <Moon size={19} />}
        </button>
      </div>
    </header>
    <HomeView mode={preparing ? "preparing" : "list"} mascotMotion={motion}
      deskLamp={foxStudy ? undefined : <MascotLamp phase={preparing ? "preparing" : "ready"} motion={motion} />}
      words={preparing ? [] : words} sinceLine={null} roughNote={null} demo={false} exportUi={exportUi} destination="csv"
      openState="idle" folderState="hidden" exportBlocked={preparing} listChanging={preparing}
      processingProgress={preparing ? { phase: "processing", current: processed, total } : null}
      onOpenWord={(id) => setSelected(words.find((word) => word.id === id))} onExport={exportExamples}
      onOpenResult={noop} onOpenFolder={noop} onSync={noop} onImportFile={noop} onDemo={noop} onExitDemo={noop} onRetryProcessing={noop} />
    {selected ? <WordExample entry={selected} exampleId={examples[selected.id]} onClose={() => setSelected(undefined)}
      onChoose={(id) => setExamples((previous) => ({ ...previous, [selected.id]: id }))} /> : null}
  </div>;
}

createRoot(document.getElementById("root")!).render(<LampStudy />);
