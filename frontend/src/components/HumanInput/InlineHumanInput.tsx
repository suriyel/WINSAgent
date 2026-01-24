import { useState, useEffect } from 'react'
import { Check, X, Pencil, Bot, AlertTriangle, FileInput } from 'lucide-react'
import { motion } from 'framer-motion'
import { cn } from '@/utils/cn'
import { DynamicFormField } from './DynamicFormField'
import type { PendingConfig } from '@/types'

interface InlineHumanInputProps {
  config: PendingConfig
  onApprove: () => void
  onSubmit: (values: Record<string, unknown>) => void
  onReject: () => void
}

export function InlineHumanInput({
  config,
  onApprove,
  onSubmit,
  onReject,
}: InlineHumanInputProps) {
  const [mode, setMode] = useState<'view' | 'edit'>('view')
  const [values, setValues] = useState<Record<string, unknown>>({})

  const isAuthorization = config.interrupt_type === 'authorization'
  const isParamRequired = config.interrupt_type === 'param_required'

  // 参数补充场景始终可编辑，授权场景依赖 mode 状态
  const effectiveMode = isParamRequired ? 'edit' : mode

  // 调试信息
  console.log('[InlineHumanInput] FULL config:', JSON.stringify(config, null, 2))
  console.log('[InlineHumanInput] interrupt_type:', config.interrupt_type, '| isParamRequired:', isParamRequired, '| effectiveMode:', effectiveMode)

  // 初始化值
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

  const handleSubmit = () => {
    onSubmit(values)
  }

  const handleCancel = () => {
    onReject()
  }

  // 获取场景配置
  const getSceneConfig = () => {
    if (isAuthorization) {
      return {
        icon: <AlertTriangle className="w-4 h-4" />,
        headerBg: 'bg-gradient-to-r from-amber-50 to-orange-50',
        headerBorder: 'border-amber-100',
        badge: '需要授权',
        badgeColor: 'bg-amber-100 text-amber-700',
        dotColor: 'bg-amber-400',
      }
    }
    return {
      icon: <FileInput className="w-4 h-4" />,
      headerBg: 'bg-gradient-to-r from-blue-50 to-indigo-50',
      headerBorder: 'border-blue-100',
      badge: '参数补充',
      badgeColor: 'bg-blue-100 text-blue-700',
      dotColor: 'bg-blue-400',
    }
  }

  const scene = getSceneConfig()

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
        <div className={cn(
          'bg-white shadow-soft rounded-2xl rounded-tl-md overflow-hidden border',
          scene.headerBorder
        )}>
          {/* 头部 */}
          <div className={cn('px-4 py-3 border-b', scene.headerBg, scene.headerBorder)}>
            <div className="flex items-center gap-2">
              <div className={cn('w-2 h-2 rounded-full animate-pulse', scene.dotColor)} />
              <h4 className="font-medium text-text-primary">{config.title}</h4>
              <span className={cn('text-xs px-2 py-0.5 rounded-full', scene.badgeColor)}>
                {scene.badge}
              </span>
            </div>
            {config.description && (
              <p className="text-sm text-text-muted mt-1.5 whitespace-pre-wrap">
                {config.description}
              </p>
            )}
            {/* 授权场景显示工具名 */}
            {isAuthorization && config.tool_name && (
              <div className="mt-2 flex items-center gap-2">
                <span className="text-xs text-text-muted">工具:</span>
                <code className="text-xs px-2 py-0.5 bg-gray-100 rounded font-mono">
                  {config.tool_name}
                </code>
              </div>
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
                <DynamicFormField
                  field={field}
                  value={values[field.name]}
                  onChange={(newValue) => handleChange(field.name, newValue)}
                  disabled={effectiveMode === 'view'}
                />
                {field.description && (
                  <p className="text-xs text-text-muted mt-1">{field.description}</p>
                )}
              </div>
            ))}
          </div>

          {/* 操作按钮 */}
          <div className="px-4 py-3 bg-gray-50 border-t border-gray-100 flex items-center gap-2">
            {isAuthorization ? (
              // 授权场景: approve / edit / reject
              mode === 'view' ? (
                <>
                  <button
                    onClick={handleApprove}
                    className="flex items-center gap-1.5 px-4 py-2 bg-success-500 text-white rounded-lg hover:bg-success-600 transition-colors text-sm font-medium"
                  >
                    <Check className="w-4 h-4" />
                    批准
                  </button>
                  <button
                    onClick={() => setMode('edit')}
                    className="flex items-center gap-1.5 px-4 py-2 bg-primary-400 text-white rounded-lg hover:bg-primary-500 transition-colors text-sm font-medium"
                  >
                    <Pencil className="w-4 h-4" />
                    编辑
                  </button>
                  <button
                    onClick={handleCancel}
                    className="flex items-center gap-1.5 px-4 py-2 bg-gray-100 text-text-secondary rounded-lg hover:bg-red-50 hover:text-red-600 transition-colors text-sm font-medium"
                  >
                    <X className="w-4 h-4" />
                    拒绝
                  </button>
                </>
              ) : (
                <>
                  <button
                    onClick={handleSubmit}
                    className="flex items-center gap-1.5 px-4 py-2 bg-primary-400 text-white rounded-lg hover:bg-primary-500 transition-colors text-sm font-medium"
                  >
                    <Check className="w-4 h-4" />
                    提交修改
                  </button>
                  <button
                    onClick={() => setMode('view')}
                    className="flex items-center gap-1.5 px-4 py-2 bg-gray-100 text-text-secondary rounded-lg hover:bg-gray-200 transition-colors text-sm font-medium"
                  >
                    取消
                  </button>
                </>
              )
            ) : (
              // 参数补充场景: confirm / cancel
              <>
                <button
                  onClick={handleSubmit}
                  className="flex items-center gap-1.5 px-4 py-2 bg-primary-400 text-white rounded-lg hover:bg-primary-500 transition-colors text-sm font-medium"
                >
                  <Check className="w-4 h-4" />
                  确认
                </button>
                <button
                  onClick={handleCancel}
                  className="flex items-center gap-1.5 px-4 py-2 bg-gray-100 text-text-secondary rounded-lg hover:bg-gray-200 transition-colors text-sm font-medium"
                >
                  <X className="w-4 h-4" />
                  取消
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </motion.div>
  )
}
