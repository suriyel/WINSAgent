interface Props {
  params: Record<string, unknown>;
  schema: Record<string, unknown>;
  onChange: (params: Record<string, unknown>) => void;
}

export default function DynamicForm({ params, onChange }: Props) {
  const handleChange = (key: string, value: string) => {
    // Attempt to parse JSON for complex types
    let parsed: unknown = value;
    try {
      parsed = JSON.parse(value);
    } catch {
      parsed = value;
    }
    onChange({ ...params, [key]: parsed });
  };

  return (
    <div className="space-y-3">
      {Object.entries(params).map(([key, value]) => {
        const isComplex = typeof value === "object";
        return (
          <div key={key}>
            <label className="block text-xs font-medium text-text-secondary mb-1">{key}</label>
            {isComplex ? (
              <textarea
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm
                           text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/40
                           focus:border-primary transition-shadow resize-none"
                rows={3}
                value={JSON.stringify(value, null, 2)}
                onChange={(e) => handleChange(key, e.target.value)}
              />
            ) : (
              <input
                type="text"
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm
                           text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/40
                           focus:border-primary transition-shadow"
                value={String(value ?? "")}
                onChange={(e) => handleChange(key, e.target.value)}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
