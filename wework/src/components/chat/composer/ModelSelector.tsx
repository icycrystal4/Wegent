import { Check, ChevronDown } from 'lucide-react'
import { useCallback, useMemo, useRef, useState } from 'react'
import { useTranslation } from '@/hooks/useTranslation'
import {
  getModelDisplayLabel,
  getModelUiMetadata,
  groupModelsByFamily,
  inferModelFamily,
} from '@/lib/model-ui'
import type { ModelOptions, UnifiedModel } from '@/types/api'
import { useOutsideClick } from './useOutsideClick'

interface ModelSelectorProps {
  models: UnifiedModel[]
  selectedModel: UnifiedModel | null
  selectedModelOptions: ModelOptions
  disabled: boolean
  onSelectModel: (model: UnifiedModel | null) => void
  onSelectModelOption: (optionId: string, value: string) => void
  menuPlacement?: 'above' | 'below'
  buttonClassName?: string
  menuClassName?: string
}

export function ModelSelector({
  models,
  selectedModel,
  selectedModelOptions,
  disabled,
  onSelectModel,
  onSelectModelOption,
  menuPlacement = 'above',
  buttonClassName = '',
  menuClassName = '',
}: ModelSelectorProps) {
  const { t } = useTranslation('common')
  const containerRef = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  const familyGroups = useMemo(() => groupModelsByFamily(models), [models])
  const selectedFamily = selectedModel ? inferModelFamily(selectedModel) : familyGroups[0]?.config.id
  const [activeFamilyId, setActiveFamilyId] = useState(selectedFamily ?? '')
  const displayedFamilyId =
    activeFamilyId || selectedFamily || familyGroups[0]?.config.id || ''
  const activeGroup =
    familyGroups.find(group => group.config.id === displayedFamilyId) ?? familyGroups[0]
  const closeMenu = useCallback(() => setOpen(false), [])

  useOutsideClick(containerRef, open, closeMenu)

  const menuPositionClass =
    menuPlacement === 'below' ? 'top-[52px] right-0' : 'bottom-[52px] right-0'
  const buttonLabel =
    getModelDisplayLabel(selectedModel, selectedModelOptions) ||
    t('workbench.default_model')

  return (
    <div ref={containerRef} className="relative">
      {open && (
        <div
          data-testid="model-selector-menu"
          className={[
            'absolute z-40 w-[min(36rem,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-border bg-base shadow-[0_16px_44px_rgba(0,0,0,0.16)]',
            menuPositionClass,
            menuClassName,
          ].join(' ')}
        >
          <div className="grid max-h-[min(28rem,calc(100vh-8rem))] min-h-64 grid-cols-[8.5rem_minmax(0,1fr)] overflow-hidden">
            <div className="border-r border-border bg-surface/60 p-2">
              <div className="px-3 pb-2 pt-1 text-sm font-semibold text-text-muted">
                {t('workbench.model_family')}
              </div>
              <div className="space-y-1">
                {familyGroups.map(group => {
                  const active = group.config.id === activeGroup?.config.id
                  return (
                    <button
                      key={group.config.id}
                      type="button"
                      data-testid={`model-family-${group.config.id}`}
                      onClick={() => setActiveFamilyId(group.config.id)}
                      className={[
                        'flex h-10 w-full items-center rounded-xl px-3 text-left text-sm font-medium',
                        active
                          ? 'bg-base text-text-primary shadow-sm'
                          : 'text-text-secondary hover:bg-base/70 hover:text-text-primary',
                      ].join(' ')}
                    >
                      <span className="min-w-0 flex-1 truncate">{group.config.label}</span>
                    </button>
                  )
                })}
              </div>
            </div>

            <div className="min-w-0 overflow-y-auto p-2">
              {!activeGroup ? (
                <div className="px-4 py-3 text-sm text-text-muted">
                  {t('workbench.no_models')}
                </div>
              ) : (
                <div className="space-y-2">
                  {activeGroup.config.controls.map(control => (
                    <div key={control.id}>
                      <div className="px-3 pb-1 pt-1 text-sm font-semibold text-text-muted">
                        {control.label}
                      </div>
                      <div className="space-y-1">
                        {control.options
                          .slice()
                          .sort((a, b) => a.order - b.order)
                          .map(option => {
                            const selected =
                              (selectedModelOptions[control.id] ?? control.defaultValue) ===
                              option.value
                            return (
                              <button
                                key={option.value}
                                type="button"
                                data-testid={`model-control-${control.id}-${option.value}`}
                                onClick={() => onSelectModelOption(control.id, option.value)}
                                className="flex min-h-10 w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm text-text-primary hover:bg-muted"
                              >
                                <span className="min-w-0 flex-1">
                                  <span className="block font-medium">{option.label}</span>
                                  {option.description && (
                                    <span className="mt-0.5 block text-xs text-text-muted">
                                      {option.description}
                                    </span>
                                  )}
                                </span>
                                {selected && <Check className="h-4 w-4 shrink-0 text-text-secondary" />}
                              </button>
                            )
                          })}
                      </div>
                    </div>
                  ))}

                  {activeGroup.config.controls.length > 0 && (
                    <div className="mx-3 border-t border-border" />
                  )}

                  <div>
                    <div className="px-3 pb-1 pt-1 text-sm font-semibold text-text-muted">
                      {t('workbench.model_version')}
                    </div>
                    <div className="space-y-1">
                      {activeGroup.models.map(model => {
                        const selected =
                          model.name === selectedModel?.name && model.type === selectedModel?.type
                        const metadata = getModelUiMetadata(model)
                        return (
                          <button
                            key={`${model.type}:${model.name}`}
                            type="button"
                            data-testid={`model-option-${model.name}`}
                            onClick={() => {
                              onSelectModel(model)
                              setOpen(false)
                            }}
                            className="flex min-h-11 w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm text-text-primary hover:bg-muted"
                          >
                            <span className="min-w-0 flex-1">
                              <span className="block truncate font-medium">
                                {getModelDisplayLabel(model, selectedModelOptions)}
                              </span>
                              <span className="mt-0.5 block truncate text-xs text-text-muted">
                                {metadata.modelLabel}
                              </span>
                            </span>
                            {selected && <Check className="h-4 w-4 shrink-0 text-text-secondary" />}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
      <button
        type="button"
        data-testid="model-selector-button"
        onClick={() => {
          if (disabled) return
          setOpen(current => {
            const nextOpen = !current
            if (nextOpen) {
              setActiveFamilyId(selectedFamily ?? familyGroups[0]?.config.id ?? '')
            }
            return nextOpen
          })
        }}
        disabled={disabled}
        className={[
          'flex h-11 min-w-[44px] max-w-64 items-center gap-1 rounded-full px-2 text-sm font-medium text-text-primary hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50',
          buttonClassName,
        ].join(' ')}
        aria-expanded={open}
        aria-label={t('workbench.model_selector')}
      >
        <span className="min-w-0 truncate">{buttonLabel}</span>
        <ChevronDown className="h-4 w-4 shrink-0 text-text-secondary" />
      </button>
    </div>
  )
}
