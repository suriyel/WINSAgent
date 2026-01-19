import { useState, useEffect } from 'react'
import { X } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/utils/cn'
import type { PendingConfig, ConfigFormField } from '@/types'

interface ConfigModalProps {
  config: PendingConfig | null
  onSubmit: (values: Record<string, unknown>) => void
  onCancel: () => void
}

export function ConfigModal({ config, onSubmit, onCancel }: ConfigModalProps) {
  const [values, setValues] = useState<Record<string, unknown>>({})

  // 初始化默认值
  useEffect(() => {
    if (config) {
      const defaults: Record<string, unknown> = {}
      config.fields.forEach((field) => {
        defaults[field.name] = config.values[field.name] ?? field.default ?? ''
      })
      setValues(defaults)
    }
  }, [config])

  const handleChange = (name: string, value: unknown) => {
    setValues((prev) => ({ ...prev, [name]: value }))
  }

  const handleSubmit = () => {
    onSubmit(values)
  }

  const renderField = (field: ConfigFormField) => {
    const value = values[field.name]

    switch (field.field_type) {
      case 'text':
      case 'number':
        return (
          <input
            type={field.field_type}
            value={value as string | number || ''}
            onChange={(e) =>
              handleChange(
                field.name,
                field.field_type === 'number'
                  ? Number(e.target.value)
                  : e.target.value
              )
            }
            placeholder={field.placeholder}
            className="input"
          />
        )

      case 'textarea':
        return (
          <textarea
            value={value as string || ''}
            onChange={(e) => handleChange(field.name, e.target.value)}
            placeholder={field.placeholder}
            rows={3}
            className="input resize-none"
          />
        )

      case 'select':
        return (
          <select
            value={value as string || ''}
            onChange={(e) => handleChange(field.name, e.target.value)}
            className="input"
          >
            <option value="">Select...</option>
            {field.options?.map((opt) => (
              <option key={String(opt.value)} value={String(opt.value)}>
                {opt.label}
              </option>
            ))}
          </select>
        )

      case 'switch':
        return (
          <button
            type="button"
            onClick={() => handleChange(field.name, !value)}
            className={cn(
              'relative w-12 h-6 rounded-full transition-colors',
              value ? 'bg-primary-400' : 'bg-gray-200'
            )}
          >
            <div
              className={cn(
                'absolute top-1 w-4 h-4 rounded-full bg-white shadow transition-transform',
                value ? 'translate-x-7' : 'translate-x-1'
              )}
            />
          </button>
        )

      case 'chips':
        const selectedChips = (value as string[]) || []
        return (
          <div className="flex flex-wrap gap-2">
            {field.options?.map((opt) => {
              const isSelected = selectedChips.includes(String(opt.value))
              return (
                <button
                  key={String(opt.value)}
                  type="button"
                  onClick={() => {
                    const newValue = isSelected
                      ? selectedChips.filter((v) => v !== String(opt.value))
                      : [...selectedChips, String(opt.value)]
                    handleChange(field.name, newValue)
                  }}
                  className={cn(
                    'px-3 py-1.5 rounded-full text-sm transition-colors',
                    isSelected
                      ? 'bg-primary-400 text-white'
                      : 'bg-gray-100 text-text-secondary hover:bg-gray-200'
                  )}
                >
                  {opt.label}
                </button>
              )
            })}
          </div>
        )

      default:
        return null
    }
  }

  return (
    <AnimatePresence>
      {config && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
        >
          {/* 背景遮罩 */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onCancel}
            className="absolute inset-0 bg-black/20 backdrop-blur-sm"
          />

          {/* 模态框 */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            className="relative bg-white rounded-2xl shadow-elevated w-full max-w-lg max-h-[80vh] overflow-hidden"
          >
            {/* 头部 */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
              <div>
                <h3 className="font-semibold text-text-primary">
                  {config.title}
                </h3>
                {config.description && (
                  <p className="text-sm text-text-muted mt-1">
                    {config.description}
                  </p>
                )}
              </div>
              <button
                onClick={onCancel}
                className="p-2 rounded-lg hover:bg-gray-100 transition-colors"
              >
                <X className="w-5 h-5 text-text-muted" />
              </button>
            </div>

            {/* 表单内容 */}
            <div className="p-6 overflow-y-auto max-h-[50vh] space-y-5">
              {config.fields.map((field) => (
                <div key={field.name}>
                  <label className="block mb-2">
                    <span className="text-sm font-medium text-text-primary">
                      {field.label}
                    </span>
                    {field.required && (
                      <span className="text-error-400 ml-1">*</span>
                    )}
                  </label>
                  {renderField(field)}
                  {field.description && (
                    <p className="text-xs text-text-muted mt-1">
                      {field.description}
                    </p>
                  )}
                </div>
              ))}
            </div>

            {/* 底部按钮 */}
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-gray-100 bg-gray-50">
              <button onClick={onCancel} className="btn-secondary">
                Cancel
              </button>
              <button onClick={handleSubmit} className="btn-primary">
                Confirm
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
