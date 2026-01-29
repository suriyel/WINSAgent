import { useState } from "react";
import type { ParamsPending, ParamSchema } from "../../types";
import { useChatStore } from "../../stores/chatStore";

interface Props {
  paramsPending: ParamsPending;
}

/** Check if a schema declares an array type. */
function isArraySchema(schema?: ParamSchema): boolean {
  if (!schema) return false;
  const t = Array.isArray(schema.type) ? schema.type[0] : schema.type;
  return t === "array";
}

/** Get the item type for an array schema (e.g. "string", "integer"). */
function getArrayItemType(schema?: ParamSchema): string {
  const items = schema?.items as Record<string, unknown> | undefined;
  return (items?.type as string) || "string";
}

/** Derive an empty default from schema type. */
function emptyValue(schema?: ParamSchema): unknown {
  if (!schema) return "";
  if (isArraySchema(schema)) return [];
  return "";
}

/**
 * Coerce a raw value into a proper array based on schema.
 * Handles cases like: "[P001]", "P001, P002", already-parsed arrays, etc.
 */
function coerceToArray(value: unknown, schema?: ParamSchema): unknown[] {
  if (Array.isArray(value)) return value;
  if (typeof value !== "string") return [];
  const trimmed = value.trim();
  if (!trimmed) return [];
  // Try JSON.parse first
  try {
    const parsed = JSON.parse(trimmed);
    if (Array.isArray(parsed)) return parsed;
  } catch {
    // not valid JSON
  }
  // Strip brackets and split by comma
  const stripped = trimmed.replace(/^\[|\]$/g, "").trim();
  if (!stripped) return [];
  return stripped.split(/\s*,\s*/).map((s) => s.replace(/^["']|["']$/g, "").trim()).filter(Boolean);
}

/** Coerce an item value based on item type. */
function coerceItem(raw: string, itemType: string): unknown {
  if (itemType === "integer") {
    const n = parseInt(raw, 10);
    return isNaN(n) ? 0 : n;
  }
  if (itemType === "number") {
    const n = parseFloat(raw);
    return isNaN(n) ? 0 : n;
  }
  return raw;
}

// ---------------------------------------------------------------------------
// ArrayInput: renders each array item as its own input row
// ---------------------------------------------------------------------------
function ArrayInput({
  items,
  schema,
  onChange,
  isMissing,
}: {
  items: unknown[];
  schema?: ParamSchema;
  onChange: (items: unknown[]) => void;
  isMissing: boolean;
}) {
  const itemType = getArrayItemType(schema);
  const isNumeric = itemType === "integer" || itemType === "number";

  const handleItemChange = (index: number, raw: string) => {
    const newItems = [...items];
    newItems[index] = isNumeric ? coerceItem(raw, itemType) : raw;
    onChange(newItems);
  };

  const handleAdd = () => {
    onChange([...items, isNumeric ? 0 : ""]);
  };

  const handleRemove = (index: number) => {
    onChange(items.filter((_, i) => i !== index));
  };

  const borderCls = isMissing ? "border-blue-300 bg-white" : "border-gray-200 bg-gray-50";

  return (
    <div className="space-y-2">
      {items.map((item, index) => (
        <div key={index} className="flex items-center gap-2">
          <input
            type={isNumeric ? "number" : "text"}
            className={`flex-1 rounded-lg border px-3 py-1.5 text-sm text-text-primary
              focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary
              transition-shadow ${borderCls}`}
            value={String(item ?? "")}
            onChange={(e) => handleItemChange(index, e.target.value)}
          />
          <button
            type="button"
            className="w-7 h-7 flex items-center justify-center rounded-md
                       text-gray-400 hover:text-red-500 hover:bg-red-50
                       transition-colors text-lg leading-none"
            onClick={() => handleRemove(index)}
            title="移除"
          >
            &times;
          </button>
        </div>
      ))}
      <button
        type="button"
        className="flex items-center gap-1 px-2 py-1 text-xs font-medium
                   text-blue-600 hover:text-blue-800 hover:bg-blue-50
                   rounded-md transition-colors"
        onClick={handleAdd}
      >
        <span className="text-base leading-none">+</span> 添加一项
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ParamsInlineCard
// ---------------------------------------------------------------------------
export default function ParamsInlineCard({ paramsPending }: Props) {
  const submitParams = useChatStore((s) => s.submitParams);

  // Build initial params: known values + empty slots for every missing param
  const [editedParams, setEditedParams] = useState<Record<string, unknown>>(
    () => {
      const init: Record<string, unknown> = {};
      // Process current_params with type coercion
      for (const [key, val] of Object.entries(paramsPending.current_params)) {
        const schema = paramsPending.params_schema[key];
        if (isArraySchema(schema)) {
          init[key] = coerceToArray(val, schema);
        } else {
          init[key] = val;
        }
      }
      // Fill missing params with empty defaults
      for (const key of paramsPending.missing_params) {
        if (!(key in init)) {
          init[key] = emptyValue(paramsPending.params_schema[key]);
        }
      }
      return init;
    }
  );

  const handleScalarChange = (key: string, raw: string) => {
    setEditedParams((prev) => ({ ...prev, [key]: raw }));
  };

  const handleArrayChange = (key: string, items: unknown[]) => {
    setEditedParams((prev) => ({ ...prev, [key]: items }));
  };

  const handleSubmit = () => {
    // Final coercion pass: ensure arrays have correct item types
    const coerced: Record<string, unknown> = {};
    for (const [key, val] of Object.entries(editedParams)) {
      const schema = paramsPending.params_schema[key];
      if (isArraySchema(schema) && Array.isArray(val)) {
        const itemType = getArrayItemType(schema);
        coerced[key] = val.map((v) => coerceItem(String(v), itemType));
      } else {
        coerced[key] = val;
      }
    }
    submitParams("submit", coerced);
  };

  const handleCancel = () => {
    submitParams("cancel");
  };

  const missingSet = new Set(paramsPending.missing_params);

  // Render order: missing params first, then known params
  const orderedKeys = [
    ...paramsPending.missing_params,
    ...Object.keys(editedParams).filter((k) => !missingSet.has(k)),
  ];

  return (
    <div className="rounded-xl border-2 border-blue-200 bg-blue-50/50 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 bg-blue-100/50 border-b border-blue-200">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
          <span className="text-sm font-semibold text-blue-800">
            参数填写
          </span>
        </div>
        <p className="text-xs text-blue-700 mt-1">
          {paramsPending.description || `请补充 ${paramsPending.tool_name} 所需的参数`}
        </p>
      </div>

      {/* Body: param form */}
      <div className="px-4 py-3 space-y-3">
        {orderedKeys.map((key) => {
          const value = editedParams[key];
          const schema = paramsPending.params_schema[key];
          const isMissing = missingSet.has(key);
          const label = schema?.title || key;
          const desc = schema?.description;
          const placeholder = schema?.placeholder || "";
          const isArray = isArraySchema(schema);

          return (
            <div key={key}>
              <label className="block text-xs font-medium text-text-secondary mb-1">
                {label}
                {isMissing && (
                  <span className="ml-1 text-blue-500 font-normal">
                    *必填
                  </span>
                )}
              </label>
              {desc && <p className="text-xs text-text-weak mb-1">{desc}</p>}
              {isArray ? (
                <ArrayInput
                  items={Array.isArray(value) ? value : coerceToArray(value, schema)}
                  schema={schema}
                  onChange={(items) => handleArrayChange(key, items)}
                  isMissing={isMissing}
                />
              ) : (
                <input
                  type="text"
                  className={`w-full rounded-lg border px-3 py-2 text-sm text-text-primary
                    focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary
                    transition-shadow ${
                      isMissing
                        ? "border-blue-300 bg-white"
                        : "border-gray-200 bg-gray-50"
                    }`}
                  placeholder={placeholder}
                  value={String(value ?? "")}
                  onChange={(e) => handleScalarChange(key, e.target.value)}
                />
              )}
            </div>
          );
        })}
      </div>

      {/* Actions */}
      <div className="px-4 py-3 border-t border-blue-200 bg-blue-50/30 flex flex-wrap gap-2">
        <button
          className="px-3 py-1.5 text-sm font-medium rounded-lg
                     bg-gray-100 text-gray-700 hover:bg-gray-200
                     transition-colors"
          onClick={handleCancel}
        >
          取消
        </button>
        <button
          className="px-3 py-1.5 text-sm font-medium rounded-lg
                     bg-blue-100 text-blue-700 hover:bg-blue-200
                     transition-colors"
          onClick={handleSubmit}
        >
          提交参数
        </button>
      </div>
    </div>
  );
}
