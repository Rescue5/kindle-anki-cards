import * as React from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { FoxFigure } from "@/components/light/fox-figure";
import { PencilButton, PencilLink } from "@/components/ui/pencil-controls";
import { PencilFrame, PencilRule } from "@/components/sketch/sketch";
import "./fox-tour.css";

const steps = [
  {
    screen: "Главная",
    title: "Загрузим слова",
    speech: "Я покажу, как взять слова из книги с собой. Подключите читалку по USB, выберите файл со словами или начните с примера.",
    preview: <ul className="fox-tour-preview-list"><li>Загрузить слова с читалки</li><li>Выбрать файл</li></ul>,
  },
  {
    screen: "Слова",
    title: "Посветим на важное",
    speech: "В «Словах» я расставляю находки по приоритету. Начните с 1. Поиск и фильтры помогут найти нужное слово, а в карточке можно выбрать «Учить» или «Не учить».",
    preview: <div className="fox-tour-preview-word"><strong lang="en">borrow</strong><span>Приоритет 2</span><small>Часто встречается в современных романах.</small></div>,
  },
  {
    screen: "Карточка слова",
    title: "Оставим вашу фразу",
    speech: "Я покажу, где встретилось слово. Выберите фразу из книги и поправьте перевод. Если хотите, включите помощь ИИ в Настройках.",
    preview: <div className="fox-tour-preview-card"><strong lang="en">borrow</strong><span>одолжить, взять взаймы</span><blockquote lang="en">She asked to borrow the book.</blockquote></div>,
  },
  {
    screen: "Главная → Выгрузка",
    title: "Заберём слова с собой",
    speech: "Я помогу собрать слова для выгрузки. Возьмите всю библиотеку, выбранные уровни или порцию новых слов. Куда их сохранить, выберите в Настройках.",
    preview: <dl className="fox-tour-preview-export"><div><dt>Что выгрузить</dt><dd>Порция новых слов</dd></div><div><dt>Куда</dt><dd>Anki</dd></div></dl>,
  },
] as const;

type FoxTourProps = { open: boolean; onDismiss: () => void };

export function FoxTour({ open, onDismiss }: FoxTourProps) {
  const trigger = React.useRef<HTMLElement | null>(null);

  return (
    <Dialog.Root open={open} onOpenChange={(next) => { if (!next) onDismiss(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fox-tour-overlay" />
        <FoxTourPanel trigger={trigger} />
      </Dialog.Portal>
    </Dialog.Root>
  );
}

const FoxTourPanel = React.forwardRef<HTMLDivElement, { trigger: React.MutableRefObject<HTMLElement | null> }>(function FoxTourPanel({ trigger }, ref) {
  const [index, setIndex] = React.useState(0);
  const previousIndex = React.useRef(index);
  const heading = React.useRef<HTMLHeadingElement>(null);
  const scroller = React.useRef<HTMLDivElement>(null);
  const step = steps[index];
  const final = index === steps.length - 1;

  React.useEffect(() => {
    if (index === previousIndex.current) return;
    previousIndex.current = index;
    if (scroller.current) scroller.current.scrollTop = 0;
    heading.current?.focus({ preventScroll: true });
  }, [index]);

  return (
    <Dialog.Content ref={ref} className="fox-tour"
      onInteractOutside={(event) => event.preventDefault()}
      onOpenAutoFocus={(event) => {
        event.preventDefault();
        const active = document.activeElement;
        trigger.current = active instanceof HTMLElement && active !== document.body ? active : null;
        heading.current?.focus({ preventScroll: true });
      }}
      onCloseAutoFocus={(event) => {
        event.preventDefault();
        const opener = trigger.current;
        trigger.current = null;
        if (opener?.isConnected && !opener.matches(":disabled") && opener.getClientRects().length > 0) {
          opener.focus({ preventScroll: true });
        } else {
          document.getElementById("home-title")?.focus({ preventScroll: true });
        }
      }}>
      <header className="fox-tour-header">
        <Dialog.Title className="fox-tour-title">Экскурсия с лисом</Dialog.Title>
        <Dialog.Description className="sr-only">Знакомство с Kindle Cards в четырёх шагах.</Dialog.Description>
        <span className="fox-tour-count" aria-hidden="true">{index + 1} из {steps.length}</span>
      </header>
      <div ref={scroller} className="fox-tour-scroll app-scrollbar">
        <p className="fox-tour-screen">{step.screen}</p>
        <h3 key={index} ref={heading} tabIndex={-1} className="fox-tour-step">
          <span className="sr-only">Шаг {index + 1} из {steps.length}. </span>{step.title}
        </h3>
        <div className="fox-tour-illustration">
          <div className="fox-tour-speech">
            <PencilFrame variant={1} />
            <p>{step.speech}</p>
            <svg className="fox-tour-speech-tail" aria-hidden="true" viewBox="0 0 34 24" fill="none">
              <path d="M0 1 Q12 14 31 18 Q12 20 0 23" vectorEffect="non-scaling-stroke" />
            </svg>
          </div>
          <figure className="fox-tour-preview">
            <figcaption>Учебный пример</figcaption>
            {step.preview}
          </figure>
          <div className="fox-tour-fox" aria-hidden="true"><FoxFigure /></div>
        </div>
      </div>
      <footer className="fox-tour-footer">
        <PencilRule />
        <Dialog.Close asChild><PencilLink>Пропустить</PencilLink></Dialog.Close>
        <div className="fox-tour-navigation">
          {index > 0 ? <PencilButton onClick={() => setIndex(index - 1)}>Назад</PencilButton> : null}
          {final ? <Dialog.Close asChild><PencilButton look="lit">Готово</PencilButton></Dialog.Close>
            : <PencilButton look="lit" onClick={() => setIndex(index + 1)}>Далее</PencilButton>}
        </div>
      </footer>
    </Dialog.Content>
  );
});
