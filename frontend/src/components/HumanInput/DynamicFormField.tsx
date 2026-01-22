import { useState } from 'react'
import { Plus, Trash2, ChevronDown, ChevronRight } from 'lucide-react'
import { cn } from '@/utils/cn'
import type { ConfigFormField } from '@/types'

interface DynamicFormFieldProps {
  field: ConfigFormField
  value: unknown
  onChange: (value: unknown) => void
  disabled?: boolean
  depth?: number
}

export function DynamicFormField({
  field,
  value,
  onChange,
  disabled = false,
  depth = 0,
}: DynamicFormFieldProps) {
  const [isExpanded, setIsExpanded] = useState(true)

  // 基础输入样式
  const inputClass = cn(
    'w-full px-3 py-2 border border-gray-200 rounded-lg transition-colors bg-white',
    'focus:outline-none focus:ring-2 focus:ring-primary-400/50 focus:border-primary-400',
    disabled && 'opacity-60 cursor-not-allowed bg-gray-50'
  )

  // 根据字段类型渲染不同控件
  switch (field.field_type) {
    case 'text':
      return (
        <input
          type="text"
          value={(value as string) || ''}
          onChange={(e) => onChange(e.target.value)}
          placeholder={field.placeholder || ''}
          className={inputClass}
          disabled={disabled}
        />
      )

    case 'number':
      return (
        <input
          type="number"
          value={(value as number) ?? ''}
          onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
          placeholder={field.placeholder || ''}
          className={inputClass}
          disabled={disabled}
        />
      )

    case 'textarea':
      return (
        <textarea
          value={(value as string) || ''}
          onChange={(e) => onChange(e.target.value)}
          placeholder={field.placeholder || ''}
          rows={3}
          className={cn(inputClass, 'resize-none')}
          disabled={disabled}
        />
      )

    case 'select':
      return (
        <select
          value={(value as string) || ''}
          onChange={(e) => onChange(e.target.value)}
          className={inputClass}
          disabled={disabled}
        >
          <option value="">请选择...</option>
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
          onClick={() => !disabled && onChange(!value)}
          disabled={disabled}
          className={cn(
            'relative w-12 h-6 rounded-full transition-colors',
            value ? 'bg-primary-400' : 'bg-gray-200',
            disabled && 'opacity-60 cursor-not-allowed'
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
                  if (!disabled) {
                    const newValue = isSelected
                      ? selectedChips.filter((v) => v !== String(opt.value))
                      : [...selectedChips, String(opt.value)]
                    onChange(newValue)
                  }
                }}
                disabled={disabled}
                className={cn(
                  'px-3 py-1.5 rounded-full text-sm transition-colors',
                  isSelected
                    ? 'bg-primary-400 text-white'
                    : 'bg-gray-100 text-text-secondary hover:bg-gray-200',
                  disabled && 'opacity-60 cursor-not-allowed'
                )}
              >
                {opt.label}
              </button>
            )
          })}
        </div>
      )

    case 'object':
      // 嵌套对象类型
      const objectValue = (value as Record<string, unknown>) || {}
      return (
        <div className={cn('border border-gray-200 rounded-lg overflow-hidden', depth > 0 && 'ml-4')}>
          <button
            type="button"
            onClick={() => setIsExpanded(!isExpanded)}
            className="w-full flex items-center gap-2 px-3 py-2 bg-gray-50 hover:bg-gray-100 transition-colors text-left"
          >
            {isExpanded ? (
              <ChevronDown className="w-4 h-4 text-gray-500" />
            ) : (
              <ChevronRight className="w-4 h-4 text-gray-500" />
            )}
            <span className="text-sm font-medium text-text-primary">{field.label}</span>
          </button>
          {isExpanded && field.children && (
            <div className="p-3 space-y-3 bg-white">
              {field.children.map((childField) => (
                <div key={childField.name}>
                  <label className="block mb-1.5">
                    <span className="text-sm font-medium text-text-primary">
                      {childField.label}
                    </span>
                    {childField.required && (
                      <span className="text-error-400 ml-1">*</span>
                    )}
                  </label>
                  <DynamicFormField
                    field={childField}
                    value={objectValue[childField.name]}
                    onChange={(newValue) => {
                      onChange({ ...objectValue, [childField.name]: newValue })
                    }}
                    disabled={disabled}
                    depth={depth + 1}
                  />
                  {childField.description && (
                    <p className="text-xs text-text-muted mt-1">{childField.description}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )

    case 'array':
      // 数组类型
      const arrayValue = (value as unknown[]) || []
      const itemType = field.item_type

      const addItem = () => {
        if (!itemType) return
        // 根据 item_type 创建默认值
        let defaultItem: unknown = ''
        if (itemType.field_type === 'number') defaultItem = 0
        if (itemType.field_type === 'switch') defaultItem = false
        if (itemType.field_type === 'object') defaultItem = {}
        if (itemType.field_type === 'array') defaultItem = []
        onChange([...arrayValue, defaultItem])
      }

      const removeItem = (index: number) => {
        onChange(arrayValue.filter((_, i) => i !== index))
      }

      const updateItem = (index: number, newValue: unknown) => {
        const newArray = [...arrayValue]
        newArray[index] = newValue
        onChange(newArray)
      }

      return (
        <div className={cn('border border-gray-200 rounded-lg overflow-hidden', depth > 0 && 'ml-4')}>
          <div className="flex items-center justify-between px-3 py-2 bg-gray-50">
            <button
              type="button"
              onClick={() => setIsExpanded(!isExpanded)}
              className="flex items-center gap-2 hover:bg-gray-100 rounded px-1 -ml-1 transition-colors"
            >
              {isExpanded ? (
                <ChevronDown className="w-4 h-4 text-gray-500" />
              ) : (
                <ChevronRight className="w-4 h-4 text-gray-500" />
              )}
              <span className="text-sm font-medium text-text-primary">
                {field.label} ({arrayValue.length})
              </span>
            </button>
            {!disabled && (
              <button
                type="button"
                onClick={addItem}
                className="flex items-center gap-1 px-2 py-1 text-xs text-primary-600 hover:bg-primary-50 rounded transition-colors"
              >
                <Plus className="w-3 h-3" />
                添加
              </button>
            )}
          </div>
          {isExpanded && (
            <div className="p-3 space-y-3 bg-white">
              {arrayValue.length === 0 ? (
                <p className="text-sm text-text-muted text-center py-2">暂无数据</p>
              ) : (
                arrayValue.map((item, index) => (
                  <div key={index} className="flex gap-2 items-start">
                    <div className="flex-1">
                      {itemType && (
                        <DynamicFormField
                          field={{ ...itemType, name: `${field.name}[${index}]`, label: `#${index + 1}` }}
                          value={item}
                          onChange={(newValue) => updateItem(index, newValue)}
                          disabled={disabled}
                          depth={depth + 1}
                        />
                      )}
                    </div>
                    {!disabled && (
                      <button
                        type="button"
                        onClick={() => removeItem(index)}
                        className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded transition-colors mt-1"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      )

    default:
      return (
        <input
          type="text"
          value={String(value || '')}
          onChange={(e) => onChange(e.target.value)}
          placeholder={field.placeholder || ''}
          className={inputClass}
          disabled={disabled}
        />
      )
  }
}
