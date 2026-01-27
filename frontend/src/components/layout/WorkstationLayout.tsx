import React from "react";

interface Props {
  sidebar: React.ReactNode;
  main: React.ReactNode;
  panel: React.ReactNode;
}

export default function WorkstationLayout({ sidebar, main, panel }: Props) {
  return (
    <div className="h-screen flex flex-col">
      {/* Header */}
      <header className="h-14 flex items-center justify-between px-6 border-b border-gray-100 bg-card shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary to-secondary flex items-center justify-center">
            <span className="text-white text-sm font-bold">W</span>
          </div>
          <h1 className="text-lg font-semibold text-text-primary">WINS Agent 工作台</h1>
        </div>
        <div className="w-8 h-8 rounded-full bg-gray-200" />
      </header>

      {/* Body: three-column layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left sidebar */}
        <aside className="w-64 border-r border-gray-100 bg-card overflow-y-auto shrink-0">
          {sidebar}
        </aside>

        {/* Center: chat area */}
        <main className="flex-1 flex flex-col overflow-hidden bg-surface">
          {main}
        </main>

        {/* Right panel */}
        <aside className="w-72 border-l border-gray-100 bg-card overflow-y-auto shrink-0">
          {panel}
        </aside>
      </div>
    </div>
  );
}
