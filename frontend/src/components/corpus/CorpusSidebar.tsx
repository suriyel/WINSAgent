import { useCorpusStore } from "../../stores/corpusStore";

/** Heading navigation sidebar for corpus file preview. */
export default function CorpusSidebar() {
  const { fileMeta, loadFileChunks, activeFile } = useCorpusStore();

  if (!fileMeta || !fileMeta.headings.length) {
    return (
      <div className="p-3 text-xs text-text-weak">
        无目录结构
      </div>
    );
  }

  const handleClick = (chunkIndex: number) => {
    if (!activeFile) return;
    loadFileChunks(activeFile, undefined, undefined, String(chunkIndex));
    useCorpusStore.setState({ anchorChunkId: chunkIndex });
  };

  return (
    <div className="p-2">
      <div className="text-xs font-semibold text-text-secondary mb-2 px-1">
        目录导航
      </div>
      <nav className="space-y-0.5">
        {fileMeta.headings.map((h, i) => {
          // Determine indent level from heading path
          const depth = (h.heading_path.match(/>/g) || []).length;
          return (
            <button
              key={i}
              onClick={() => handleClick(h.chunk_index)}
              className="w-full text-left text-xs text-text-secondary hover:text-primary hover:bg-primary/5 rounded px-2 py-1.5 truncate transition-colors"
              style={{ paddingLeft: `${8 + depth * 12}px` }}
              title={h.heading_path}
            >
              {h.heading_path.split(" > ").pop()?.replace(/^#+\s*/, "") || h.heading_path}
            </button>
          );
        })}
      </nav>
    </div>
  );
}
