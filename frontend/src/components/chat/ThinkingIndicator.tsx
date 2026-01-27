export default function ThinkingIndicator() {
  return (
    <div className="flex items-center gap-1.5 py-1">
      <span className="w-2 h-2 rounded-full bg-secondary animate-bounce [animation-delay:0ms]" />
      <span className="w-2 h-2 rounded-full bg-secondary animate-bounce [animation-delay:150ms]" />
      <span className="w-2 h-2 rounded-full bg-secondary animate-bounce [animation-delay:300ms]" />
      <span className="text-xs text-text-weak ml-2">思考中</span>
    </div>
  );
}
