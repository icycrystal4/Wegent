import type { ModelOptions, UnifiedModel } from '@/types/api'

export interface ModelControlOption {
  value: string
  label: string
  description?: string
  order: number
}

export interface ModelControlConfig {
  id: string
  label: string
  defaultValue: string
  includeInLabel?: 'always' | 'whenNonDefault' | 'never'
  options: ModelControlOption[]
}

export interface ModelFamilyConfig {
  id: string
  label: string
  order: number
  controls: ModelControlConfig[]
}

interface ModelUiMetadata {
  family: string
  region?: string
  modelLabel: string
  sortOrder: number
}

const REGION_LABELS: Record<string, string> = {
  intranet: '内网',
  public: '公网',
  overseas: '海外',
}

const FAMILY_ORDER = ['claude', 'gpt', 'gemini', 'kimi']

export const MODEL_FAMILY_CONFIGS: ModelFamilyConfig[] = [
  { id: 'claude', label: 'Claude', order: 10, controls: [] },
  {
    id: 'gpt',
    label: 'GPT',
    order: 20,
    controls: [
      {
        id: 'reasoning',
        label: 'Reasoning',
        defaultValue: 'high',
        includeInLabel: 'always',
        options: [
          { value: 'low', label: 'Low', order: 10 },
          { value: 'medium', label: 'Medium', order: 20 },
          { value: 'high', label: 'High', order: 30 },
          { value: 'extra_high', label: 'Extra High', order: 40 },
        ],
      },
      {
        id: 'speed',
        label: 'Speed',
        defaultValue: 'standard',
        includeInLabel: 'whenNonDefault',
        options: [
          {
            value: 'standard',
            label: 'Standard',
            description: 'Default speed',
            order: 10,
          },
          {
            value: 'fast',
            label: 'Fast',
            description: '1.5x speed, increased usage',
            order: 20,
          },
        ],
      },
    ],
  },
  { id: 'gemini', label: 'Gemini', order: 30, controls: [] },
  { id: 'kimi', label: 'Kimi', order: 40, controls: [] },
]

function getConfigUi(model: UnifiedModel): Record<string, unknown> {
  const ui = model.config?.ui
  return ui && typeof ui === 'object' && !Array.isArray(ui)
    ? (ui as Record<string, unknown>)
    : {}
}

function textForModel(model: UnifiedModel): string {
  return [model.name, model.displayName, model.modelId, model.provider]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
}

export function inferModelFamily(model: UnifiedModel): string {
  const explicit = getConfigUi(model).family
  if (typeof explicit === 'string' && explicit.trim()) {
    return explicit.trim().toLowerCase()
  }

  const text = textForModel(model)
  if (text.includes('kimi')) return 'kimi'
  if (text.includes('gemini')) return 'gemini'
  if (text.includes('claude') || text.includes('opus') || text.includes('sonnet')) {
    return 'claude'
  }
  if (text.includes('gpt') || text.includes('openai')) return 'gpt'
  return 'other'
}

export function getFamilyConfig(familyId: string): ModelFamilyConfig {
  return (
    MODEL_FAMILY_CONFIGS.find(config => config.id === familyId) ?? {
      id: familyId,
      label: familyId.replace(/^\w/, letter => letter.toUpperCase()),
      order: 100,
      controls: [],
    }
  )
}

function inferRegion(model: UnifiedModel): string | undefined {
  const explicit = getConfigUi(model).region
  if (typeof explicit === 'string' && explicit.trim()) return explicit.trim()

  const text = [model.displayName, model.name].filter(Boolean).join(' ')
  if (text.includes('海外') || /overseas/i.test(text)) return 'overseas'
  if (text.includes('公网') || /public/i.test(text)) return 'public'
  if (text.includes('内网') || /intranet|internal/i.test(text)) return 'intranet'
  return undefined
}

function stripRegionPrefix(label: string): string {
  return label.replace(/^(内网|公网|海外)\s*[:：]\s*/, '').trim()
}

export function getModelUiMetadata(model: UnifiedModel): ModelUiMetadata {
  const ui = getConfigUi(model)
  const modelLabel =
    typeof ui.modelLabel === 'string' && ui.modelLabel.trim()
      ? ui.modelLabel.trim()
      : stripRegionPrefix(model.displayName || model.modelId || model.name)
  const sortOrder = typeof ui.sortOrder === 'number' ? ui.sortOrder : 100

  return {
    family: inferModelFamily(model),
    region: inferRegion(model),
    modelLabel,
    sortOrder,
  }
}

export function getModelDisplayLabel(
  model: UnifiedModel | null,
  options: ModelOptions = {},
): string {
  if (!model) return ''

  const metadata = getModelUiMetadata(model)
  const familyConfig = getFamilyConfig(metadata.family)
  const regionLabel = metadata.region ? REGION_LABELS[metadata.region] ?? metadata.region : ''
  const controlLabels = familyConfig.controls
    .filter(control => control.includeInLabel !== 'never')
    .map(control => {
      const selected = options[control.id] ?? control.defaultValue
      if (control.includeInLabel === 'whenNonDefault' && selected === control.defaultValue) {
        return ''
      }
      return control.options.find(option => option.value === selected)?.label ?? ''
    })
    .filter(Boolean)

  return [
    regionLabel ? `${regionLabel}:${metadata.modelLabel}` : metadata.modelLabel,
    ...controlLabels,
  ].join(' ')
}

export function getDefaultModelOptions(model: UnifiedModel | null): ModelOptions {
  if (!model) return {}
  const familyConfig = getFamilyConfig(inferModelFamily(model))
  return Object.fromEntries(
    familyConfig.controls.map(control => [control.id, control.defaultValue]),
  )
}

export function normalizeModelOptions(
  model: UnifiedModel | null,
  options: ModelOptions,
): ModelOptions {
  if (!model) return {}
  const familyConfig = getFamilyConfig(inferModelFamily(model))
  return Object.fromEntries(
    familyConfig.controls.map(control => [
      control.id,
      options[control.id] ?? control.defaultValue,
    ]),
  )
}

export function groupModelsByFamily(models: UnifiedModel[]) {
  const groups = new Map<string, UnifiedModel[]>()
  for (const model of models) {
    const family = inferModelFamily(model)
    groups.set(family, [...(groups.get(family) ?? []), model])
  }

  return [...groups.entries()]
    .map(([familyId, familyModels]) => ({
      config: getFamilyConfig(familyId),
      models: [...familyModels].sort((a, b) => {
        const left = getModelUiMetadata(a)
        const right = getModelUiMetadata(b)
        return left.sortOrder - right.sortOrder || left.modelLabel.localeCompare(right.modelLabel)
      }),
    }))
    .sort((a, b) => {
      const leftOrder = FAMILY_ORDER.indexOf(a.config.id)
      const rightOrder = FAMILY_ORDER.indexOf(b.config.id)
      const normalizedLeft = leftOrder >= 0 ? leftOrder : a.config.order
      const normalizedRight = rightOrder >= 0 ? rightOrder : b.config.order
      return normalizedLeft - normalizedRight || a.config.label.localeCompare(b.config.label)
    })
}

export function isSupportedModelFamily(model: UnifiedModel): boolean {
  return inferModelFamily(model) !== 'other'
}
