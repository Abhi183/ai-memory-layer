"use client";

import { Memory } from "@/lib/api";

interface Props {
  memory: Memory;
  onDelete: (id: string) => void;
  similarityScore?: number;
}

const PLATFORM_ICONS: Record<string, string> = {
  chatgpt: "💬",
  claude: "🤖",
  cursor: "⌨️",
  notion: "📄",
};

const TYPE_COLORS: Record<string, string> = {
  long_term: "bg-violet-900 text-violet-300",
  short_term: "bg-blue-900 text-blue-300",
  semantic: "bg-emerald-900 text-emerald-300",
};

const STATUS_COLORS: Record<string, string> = {
  active: "bg-emerald-500",
  pending: "bg-amber-500",
  processing: "bg-blue-500 animate-pulse",
  failed: "bg-red-500",
  archived: "bg-slate-500",
};

export default function MemoryCard({ memory, onDelete, similarityScore }: Props) {
  const icon = PLATFORM_ICONS[memory.source_platform || ""] || "🧠";
  const displayText = memory.summary || memory.content;
  const facts = memory.extracted_facts?.facts || [];
  const date = new Date(memory.captured_at).toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric",
  });

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 hover:border-slate-700 transition-colors group">
      {/* Header */}
      <div className="flex items-start gap-3 mb-3">
        <span className="text-xl shrink-0">{icon}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${TYPE_COLORS[memory.memory_type] || "bg-slate-700 text-slate-300"}`}>
              {memory.memory_type.replace("_", " ")}
            </span>
            {memory.source_platform && (
              <span className="text-xs text-slate-500">{memory.source_platform}</span>
            )}
            {similarityScore !== undefined && (
              <span className="text-xs text-indigo-400 ml-auto">
                {(similarityScore * 100).toFixed(0)}% match
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            onClick={() => onDelete(memory.id)}
            className="text-slate-500 hover:text-red-400 transition-colors text-xs"
            title="Delete memory"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Content */}
      <p className="text-sm text-slate-300 line-clamp-3 mb-3 leading-relaxed">
        {displayText}
      </p>

      {/* Facts */}
      {facts.length > 0 && (
        <div className="mb-3 space-y-1">
          {facts.slice(0, 3).map((fact, i) => (
            <div key={i} className="flex items-start gap-2 text-xs text-slate-400">
              <span className="text-indigo-500 shrink-0">▸</span>
              <span>{fact}</span>
            </div>
          ))}
        </div>
      )}

      {/* Tags */}
      {memory.tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          {memory.tags.map((tag) => (
            <span key={tag.id} className="text-xs bg-slate-800 text-slate-400 px-2 py-0.5 rounded-full">
              #{tag.name}
            </span>
          ))}
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between text-xs text-slate-500">
        <span>{date}</span>
        <div className="flex items-center gap-2">
          <span>{memory.access_count} accesses</span>
          <span
            className={`w-2 h-2 rounded-full ${STATUS_COLORS[memory.status] || "bg-slate-500"}`}
            title={memory.status}
          />
        </div>
      </div>
    </div>
  );
}
