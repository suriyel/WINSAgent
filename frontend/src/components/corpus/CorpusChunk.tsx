import React, { useRef, useEffect } from "react";
import type { CorpusChunk as CorpusChunkData } from "../../stores/corpusStore";

interface Props {
  chunk: CorpusChunkData;
  highlightKeywords: string[];
  isAnchor: boolean;
}

/** Highlight keywords in text by wrapping matches in <mark> tags. */
function highlightText(text: string, keywords: string[]): React.ReactNode[] {
  if (!keywords.length) return [text];

  const escaped = keywords.map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const pattern = new RegExp(`(${escaped.join("|")})`, "gi");
  const parts = text.split(pattern);

  return parts.map((part, i) => {
    if (keywords.some((k) => k.toLowerCase() === part.toLowerCase())) {
      return (
        <mark key={i} className="bg-yellow-200 text-text-primary rounded px-0.5">
          {part}
        </mark>
      );
    }
    return part;
  });
}

export default function CorpusChunkItem({ chunk, highlightKeywords, isAnchor }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isAnchor && ref.current) {
      ref.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [isAnchor]);

  return (
    <div
      ref={ref}
      data-chunk-index={chunk.chunk_index}
      className={`px-4 py-3 border-b border-gray-100 ${
        isAnchor ? "bg-primary/5 border-l-2 border-l-primary" : ""
      }`}
    >
      {/* Heading path */}
      {chunk.heading_path && (
        <div className="text-xs text-text-weak mb-1 font-medium">
          {chunk.heading_path}
        </div>
      )}

      {/* Content */}
      <div className="text-sm text-text-primary whitespace-pre-wrap leading-relaxed">
        {highlightKeywords.length > 0
          ? highlightText(chunk.content, highlightKeywords)
          : chunk.content}
      </div>

      {/* Image refs indicator */}
      {chunk.has_images && chunk.image_refs.length > 0 && (
        <div className="mt-2 space-y-2">
          {chunk.image_refs.map((ref, i) => (
            <img
              key={i}
              src={`/corpus/${ref}`}
              alt={`Image ${i + 1}`}
              className="max-w-full rounded border border-gray-200"
              loading="lazy"
            />
          ))}
        </div>
      )}

      {/* Chunk index badge */}
      <div className="mt-1 text-xs text-text-weak">
        #{chunk.chunk_index}
      </div>
    </div>
  );
}
