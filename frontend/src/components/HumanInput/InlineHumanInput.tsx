import { useState, useEffect } from 'react'
import { Check, X, Pencil, Bot } from 'lucide-react'
import { motion } from 'framer-motion'
import { cn } from '@/utils/cn'
import type { PendingConfig, ConfigFormField } from '@/types'

export type HumanInputAction = 'approve' | 'edit' | 'reject'

interface InlineHumanInputProps {
  config: PendingConfig
  onApprove: () => void
  onSubmit: (values: Record<string, unknown>) => void
  onReject: (reason?: string) => void
}

export function InlineHumanInput({
  config,
  onApprove,
  onSubmit,
  onReject,
}: InlineHumanInputProps) {
  const [mode, setMode] = useState<'view' | 'edit'>('view')
  const [values, setValues] = useState<Record<string, unknown>>({})
  const [rejectReason, setRejectReason] = useState('')
  const [showRejectInput, setShowRejectInput] = useState(false)

  // 初始化默认值
  useEffect(() => {
    const defaults: Record<string, unknown> = {}
    config.fields.forEach((field) => {
      defaults[field.name] = config.values[field.name] ?? field.default ?? ''
    })
    setValues(defaults)
  }, [config])

  const handleChange = (name: string, value: unknown) => {
    setValues((prev) => ({ ...prev, [name]: value }))
  }

  const handleApprove = () => {
    onApprove()
  }

  const handleSubmitEdit = () => {
    onSubmit(values)
  }

  const handleReject = () => {
    if (showRejectInput) {
      onReject(rejectReason || undefined)
    } else {
      setShowRejectInput(true)
    }
  }

  const handleCancelReject = () => {
    setShowRejectInput(false)
    setRejectReason('')
  }

  const renderField = (field: ConfigFormField) => {
    const value = values[field.name]

    switch (field.field_type) {
      case 'text':
      case 'number':
        return (
          <input
            type={field.field_type}
            value={(value as string | number) || ''}
            onChange={(e) =>
              handleChange(
                field.name,
                field.field_type === 'number'
                  ? Number(e.target.value)
                  : e.target.value
              )
            }
            placeholder={field.placeholder}
            className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-400/50 focus:border-primary-400 transition-colors bg-white"
            disabled={mode === 'view'}
          />
        )

      case 'textarea':
        return (
          <textarea
            value={(value as string) || ''}
            onChange={(e) => handleChange(field.name, e.target.value)}
            placeholder={field.placeholder}
            rows={3}
            className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-400/50 focus:border-primary-400 transition-colors bg-white resize-none"
            disabled={mode === 'view'}
          />
        )

      case 'select':
        return (
          <select
            value={(value as string) || ''}
            onChange={(e) => handleChange(field.name, e.target.value)}
            className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-400/50 focus:border-primary-400 transition-colors bg-white"
            disabled={mode === 'view'}
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
            onClick={() => mode === 'edit' && handleChange(field.name, !value)}
            disabled={mode === 'view'}
            className={cn(
              'relative w-12 h-6 rounded-full transition-colors',
              value ? 'bg-primary-400' : 'bg-gray-200',
              mode === 'view' && 'opacity-60 cursor-not-allowed'
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
                    if (mode === 'edit') {
                      const newValue = isSelected
                        ? selectedChips.filter((v) => v !== String(opt.value))
                        : [...selectedChips, String(opt.value)]
                      handleChange(field.name, newValue)
                    }
                  }}
                  disabled={mode === 'view'}
                  className={cn(
                    'px-3 py-1.5 rounded-full text-sm transition-colors',
                    isSelected
                      ? 'bg-primary-400 text-white'
                      : 'bg-gray-100 text-text-secondary hover:bg-gray-200',
                    mode === 'view' && 'opacity-60 cursor-not-allowed'
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
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex gap-3 animate-fade-in"
    >
      {/* AI 头像 */}
      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-primary-400 to-secondary-400 flex items-center justify-center flex-shrink-0">
        <Bot className="w-4 h-4 text-white" />
      </div>

      {/* 内容区域 */}
      <div className="flex-1 max-w-[85%]">
        <div className="bg-white shadow-soft rounded-2xl rounded-tl-md overflow-hidden border border-amber-100">
          {/* 头部 - 标题和状态指示 */}
          <div className="px-4 py-3 bg-gradient-to-r from-amber-50 to-orange-50 border-b border-amber-100">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
              <h4 className="font-medium text-text-primary">{config.title}</h4>
              <span className="text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-700">
                需要您的确认
              </span>
            </div>
            {config.description && (
              <p className="text-sm text-text-muted mt-1.5">
                {config.description}
              </p>
            )}
          </div>

          {/* 表单内容 */}
          <div className="p-4 space-y-4">
            {config.fields.map((field) => (
              <div key={field.name}>
                <label className="block mb-1.5">
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

          {/* 拒绝原因输入 */}
          {showRejectInput && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              className="px-4 pb-4"
            >
              <div className="p-3 bg-red-50 rounded-lg border border-red-100">
                <label className="block mb-2 text-sm font-medium text-red-700">
                  拒绝原因（可选）
                </label>
                <textarea
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  placeholder="请说明拒绝的原因..."
                  rows={2}
                  className="w-full px-3 py-2 border border-red-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-400/50 focus:border-red-400 transition-colors bg-white resize-none text-sm"
                />
                <div className="flex gap-2 mt-2">
                  <button
                    onClick={() => onReject(rejectReason || undefined)}
                    className="px-3 py-1.5 text-sm bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors"
                  >
                    确认拒绝
                  </button>
                  <button
                    onClick={handleCancelReject}
                    className="px-3 py-1.5 text-sm bg-gray-100 text-text-secondary rounded-lg hover:bg-gray-200 transition-colors"
                  >
                    取消
                  </button>
                </div>
              </div>
            </motion.div>
          )}

          {/* 操作按钮 */}
          {!showRejectInput && (
            <div className="px-4 py-3 bg-gray-50 border-t border-gray-100 flex items-center gap-2">
              {mode === 'view' ? (
                <>
                  {/* Approve 按钮 */}
                  <button
                    onClick={handleApprove}
                    className="flex items-center gap-1.5 px-4 py-2 bg-success-500 text-white rounded-lg hover:bg-success-600 transition-colors text-sm font-medium"
                  >
                    <Check className="w-4 h-4" />
                    批准
                  </button>

                  {/* Edit 按钮 */}
                  <button
                    onClick={() => setMode('edit')}
                    className="flex items-center gap-1.5 px-4 py-2 bg-primary-400 text-white rounded-lg hover:bg-primary-500 transition-colors text-sm font-medium"
                  >
                    <Pencil className="w-4 h-4" />
                    编辑
                  </button>

                  {/* Reject 按钮 */}
                  <button
                    onClick={handleReject}
                    className="flex items-center gap-1.5 px-4 py-2 bg-gray-100 text-text-secondary rounded-lg hover:bg-red-50 hover:text-red-600 transition-colors text-sm font-medium"
                  >
                    <X className="w-4 h-4" />
                    拒绝
                  </button>
                </>
              ) : (
                <>
                  {/* 提交编辑 */}
                  <button
                    onClick={handleSubmitEdit}
                    className="flex items-center gap-1.5 px-4 py-2 bg-primary-400 text-white rounded-lg hover:bg-primary-500 transition-colors text-sm font-medium"
                  >
                    <Check className="w-4 h-4" />
                    提交修改
                  </button>

                  {/* 取消编辑 */}
                  <button
                    onClick={() => setMode('view')}
                    className="flex items-center gap-1.5 px-4 py-2 bg-gray-100 text-text-secondary rounded-lg hover:bg-gray-200 transition-colors text-sm font-medium"
                  >
                    取消
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </motion.div>
  )
}
