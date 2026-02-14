/** Zustand store for corpus viewer state. */

import { create } from "zustand";

export interface CorpusChunk {
  chunk_index: number;
  heading_path: string;
  content: string;
  has_images: boolean;
  image_refs: string[];
}

export interface CorpusFileInfo {
  file_id: string;
  filename: string;
  size_bytes: number;
}

export interface CorpusFileMeta {
  file_id: string;
  filename: string;
  size_bytes: number;
  total_chunks: number;
  headings: { heading_path: string; chunk_index: number }[];
}

interface CorpusState {
  // Viewer state
  activeFile: string | null;       // file_id currently open
  activeFilename: string | null;
  anchorChunkId: number | null;    // chunk_index to scroll to
  highlightKeywords: string[];

  // Data
  chunks: CorpusChunk[];
  totalChunks: number;
  fileMeta: CorpusFileMeta | null;
  fileList: CorpusFileInfo[];

  // Loading state
  isLoading: boolean;

  // Actions
  openCorpusViewer: (fileId: string, chunkId?: number, keywords?: string[]) => void;
  closeCorpusViewer: () => void;
  loadFileList: () => Promise<void>;
  loadFileChunks: (fileId: string, offset?: number, limit?: number, anchor?: string) => Promise<void>;
  loadFileMeta: (fileId: string) => Promise<void>;
}

const BASE = "/api/corpus";

export const useCorpusStore = create<CorpusState>((set, get) => ({
  activeFile: null,
  activeFilename: null,
  anchorChunkId: null,
  highlightKeywords: [],
  chunks: [],
  totalChunks: 0,
  fileMeta: null,
  fileList: [],
  isLoading: false,

  openCorpusViewer(fileId: string, chunkId?: number, keywords?: string[]) {
    set({
      activeFile: fileId,
      anchorChunkId: chunkId ?? null,
      highlightKeywords: keywords ?? [],
      chunks: [],
      totalChunks: 0,
      fileMeta: null,
    });

    // Load data
    const state = get();
    state.loadFileMeta(fileId);
    state.loadFileChunks(fileId, undefined, undefined, chunkId?.toString());
  },

  closeCorpusViewer() {
    set({
      activeFile: null,
      activeFilename: null,
      anchorChunkId: null,
      highlightKeywords: [],
      chunks: [],
      totalChunks: 0,
      fileMeta: null,
    });
  },

  async loadFileList() {
    try {
      const res = await fetch(`${BASE}/files`);
      if (res.ok) {
        const files: CorpusFileInfo[] = await res.json();
        set({ fileList: files });
      }
    } catch {
      // Ignore fetch errors
    }
  },

  async loadFileChunks(fileId: string, offset = 0, limit = 50, anchor?: string) {
    set({ isLoading: true });
    try {
      const params = new URLSearchParams({ offset: String(offset), limit: String(limit) });
      if (anchor) params.set("anchor", anchor);

      const res = await fetch(`${BASE}/files/${fileId}?${params}`);
      if (res.ok) {
        const data = await res.json();
        set({
          chunks: data.chunks,
          totalChunks: data.total_chunks,
          activeFilename: data.filename,
        });
      }
    } catch {
      // Ignore fetch errors
    } finally {
      set({ isLoading: false });
    }
  },

  async loadFileMeta(fileId: string) {
    try {
      const res = await fetch(`${BASE}/files/${fileId}/meta`);
      if (res.ok) {
        const meta: CorpusFileMeta = await res.json();
        set({ fileMeta: meta, activeFilename: meta.filename });
      }
    } catch {
      // Ignore fetch errors
    }
  },
}));
