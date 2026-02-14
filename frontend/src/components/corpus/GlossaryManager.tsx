import { useState, useEffect, useCallback } from "react";

interface GlossaryInfo {
  files: string[];
  total_terms: number;
  total_synonyms?: number;
}

const BASE = "/api/corpus";

/** Expert glossary management UI — upload/view/delete terminology files. */
export default function GlossaryManager() {
  const [info, setInfo] = useState<GlossaryInfo | null>(null);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState("");

  const loadGlossary = useCallback(async () => {
    try {
      const res = await fetch(`${BASE}/glossary`);
      if (res.ok) {
        setInfo(await res.json());
      }
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    loadGlossary();
  }, [loadGlossary]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setMessage("");

    try {
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch(`${BASE}/glossary/upload`, {
        method: "POST",
        body: formData,
      });

      if (res.ok) {
        setMessage(`已上传: ${file.name}`);
        loadGlossary();
      } else {
        const data = await res.json();
        setMessage(`上传失败: ${data.detail || "未知错误"}`);
      }
    } catch {
      setMessage("上传失败: 网络错误");
    } finally {
      setUploading(false);
      // Reset input
      e.target.value = "";
    }
  };

  const handleDelete = async (filename: string) => {
    try {
      const res = await fetch(`${BASE}/glossary/${filename}`, { method: "DELETE" });
      if (res.ok) {
        setMessage(`已删除: ${filename}`);
        loadGlossary();
      }
    } catch {
      setMessage("删除失败");
    }
  };

  return (
    <div className="p-4 space-y-4">
      <div className="text-sm font-semibold text-text-primary">专家词表管理</div>

      {/* Stats */}
      {info && (
        <div className="flex gap-4 text-xs text-text-secondary">
          <span>术语: {info.total_terms} 条</span>
          {info.total_synonyms !== undefined && (
            <span>同义词组: {info.total_synonyms} 组</span>
          )}
        </div>
      )}

      {/* Upload */}
      <div>
        <label className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-gray-200 text-sm text-text-secondary hover:border-primary hover:text-primary cursor-pointer transition-colors">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
          </svg>
          {uploading ? "上传中..." : "上传词表 (JSON/CSV)"}
          <input
            type="file"
            accept=".json,.csv"
            onChange={handleUpload}
            disabled={uploading}
            className="hidden"
          />
        </label>
      </div>

      {/* File list */}
      {info && info.files.length > 0 && (
        <div className="space-y-1">
          <div className="text-xs font-medium text-text-secondary">已上传文件</div>
          {info.files.map((filename) => (
            <div
              key={filename}
              className="flex items-center justify-between px-3 py-2 rounded-lg bg-surface text-sm"
            >
              <span className="text-text-primary truncate">{filename}</span>
              <button
                onClick={() => handleDelete(filename)}
                className="text-xs text-error hover:text-error/80 shrink-0 ml-2"
              >
                删除
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Message */}
      {message && (
        <div className="text-xs text-text-secondary">{message}</div>
      )}
    </div>
  );
}
