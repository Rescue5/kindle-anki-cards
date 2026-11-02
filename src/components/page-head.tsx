import * as React from "react";
import { PencilRule } from "@/components/sketch/sketch";

/** The heading of a reading screen: a title, an italic lede and tools, underlined in pencil. */
export function PageHead({ title, lede, children }: { title: string; lede?: string; children?: React.ReactNode }) {
  return (
    <>
      <header className="page-head">
        <div>
          <h1>{title}</h1>
          {lede ? <p className="page-head-lede">{lede}</p> : null}
        </div>
        {children ? <div className="page-head-tools">{children}</div> : null}
      </header>
      <PencilRule variant={2} />
    </>
  );
}
