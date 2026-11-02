import { cn } from "@/lib/utils";

type BookJacketProps = {
  title: string;
  author?: string;
  coverDataUrl?: string;
  /** The jacket sits in a lamp's pool and catches its light. */
  lit?: boolean;
  size?: "lg" | "sm";
  className?: string;
};

/** A book as a drawn jacket, or the real cover when Kindle or Open Library has one. */
export function BookJacket({ title, author, coverDataUrl, lit = false, size = "lg", className }: BookJacketProps) {
  return (
    <div className={cn("book-jacket", `book-jacket-${size}`, lit && "is-lit", className)} aria-hidden="true">
      {coverDataUrl ? (
        <img className="book-jacket-image" src={coverDataUrl} alt="" />
      ) : (
        <>
          <svg className="book-jacket-art" viewBox="0 0 212 310" preserveAspectRatio="none">
            <rect x="16" y="14" width="180" height="282" rx="2" />
            <rect className="book-jacket-art-soft" x="21" y="19" width="170" height="272" rx="1" />
            {size === "lg" ? (
              <>
                <path className="book-jacket-art-soft" d="M156.9 217.2 L190.1 210.1 M153.5 206.8 L173.6 197.9 M148.1 197.4 L175.6 177.5 M140.8 189.4 L155.5 173 M132 183 L149 153.5 M122.1 178.5 L128.9 157.6 M111.4 176.3 L115 142.5 M100.6 176.3 L98.3 154.4 M89.9 178.5 L79.4 146.2 M80 183 L69 163.9 M71.2 189.4 L48.5 164.1 M63.9 197.4 L46.1 184.5 M58.5 206.8 L27.4 193 M55.1 217.2 L33.6 212.6" />
                <path d="M58 228 A48 48 0 0 1 154 228 M74 228 A32 32 0 0 1 138 228 M36 228 L176 228" />
              </>
            ) : (
              <path d="M74 228 A32 32 0 0 1 138 228 M50 228 L162 228" />
            )}
          </svg>
          <span className="book-jacket-title">{title}</span>
          {author && size === "lg" ? <span className="book-jacket-author">{author}</span> : null}
        </>
      )}
      <span className="book-jacket-light" />
    </div>
  );
}
