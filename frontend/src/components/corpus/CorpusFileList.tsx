import { useEffect } from "react";
import { useCorpusStore } from "../../stores/corpusStore";

/** List of parsed corpus files — displayed when no specific file is active. */
export default function CorpusFileList() {
  const { fileList, loadFileList, openCorpusViewer } = useCorpusStore();

  useEffect(() => {
    loadFileList();
  }, [loadFileList]);

  if (fileList.length === 0) {
    return (
      <div className="p-4 text-sm text-text-weak text-center">
        语料库为空。请通过 API 触发构建。
      </div>
    );
  }

  return (
    <div className="p-3 space-y-1">
      <div className="text-xs font-semibold text-text-secondary mb-2">
        语料文件 ({fileList.length})
      </div>
      {fileList.map((file) => (
        <button
          key={file.file_id}
          onClick={() => openCorpusViewer(file.file_id)}
          className="w-full text-left px-3 py-2 rounded-lg hover:bg-primary/5 text-sm transition-colors group"
        >
          <div className="text-text-primary group-hover:text-primary truncate">
            {file.filename}
          </div>
          <div className="text-xs text-text-weak">
            {(file.size_bytes / 1024).toFixed(1)} KB
          </div>
        </button>
      ))}
    </div>
  );
}
