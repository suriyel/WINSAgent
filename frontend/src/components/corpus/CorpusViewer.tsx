import { useEffect } from "react";
import { useCorpusStore } from "../../stores/corpusStore";
import CorpusChunkItem from "./CorpusChunk";
import CorpusSidebar from "./CorpusSidebar";

/**
 * Main corpus viewer component — replaces TaskPanel when a corpus file is opened.
 *
 * Renders chunks in a scrollable list with heading navigation sidebar.
 * Virtual scrolling for 10MB+ files is achieved via pagination (load more on scroll).
 */
export default function CorpusViewer() {
  const {
    activeFile,
    activeFilename,
    anchorChunkId,
    highlightKeywords,
    chunks,
    totalChunks,
    isLoading,
    closeCorpusViewer,
    loadFileChunks,
  } = useCorpusStore();

  // Load more chunks when scrolling to bottom
  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 200;

    if (nearBottom && !isLoading && chunks.length < totalChunks && activeFile) {
      loadFileChunks(activeFile, chunks.length, 50);
    }
  };

  if (!activeFile) return null;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100 bg-card shrink-0">
        <button
          onClick={closeCorpusViewer}
          className="w-7 h-7 rounded-md flex items-center justify-center hover:bg-gray-100 text-text-secondary transition-colors"
          title="返回任务面板"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-text-primary truncate">
            {activeFilename || "语料预览"}
          </div>
          <div className="text-xs text-text-weak">
            {totalChunks} 段落
            {highlightKeywords.length > 0 && (
              <span className="ml-2">
                高亮: {highlightKeywords.join(", ")}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Body: sidebar + content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Mini heading sidebar */}
        <div className="w-36 border-r border-gray-100 overflow-y-auto shrink-0 hidden lg:block">
          <CorpusSidebar />
        </div>

        {/* Chunk list (paginated scroll) */}
        <div
          className="flex-1 overflow-y-auto"
          onScroll={handleScroll}
        >
          {chunks.map((chunk) => (
            <CorpusChunkItem
              key={chunk.chunk_index}
              chunk={chunk}
              highlightKeywords={highlightKeywords}
              isAnchor={chunk.chunk_index === anchorChunkId}
            />
          ))}

          {isLoading && (
            <div className="py-4 text-center text-xs text-text-weak">
              加载中...
            </div>
          )}

          {!isLoading && chunks.length === 0 && (
            <div className="py-8 text-center text-sm text-text-weak">
              暂无内容
            </div>
          )}

          {!isLoading && chunks.length > 0 && chunks.length >= totalChunks && (
            <div className="py-4 text-center text-xs text-text-weak">
              -- 共 {totalChunks} 段落 --
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
