import { useCallback, useEffect, useState } from 'react'
import {
  getDefaultModelOptions,
  inferModelFamily,
  isSupportedModelFamily,
  normalizeModelOptions,
} from '@/lib/model-ui'
import type { ModelOptions, UnifiedModel, UnifiedModelListResponse } from '@/types/api'

interface WorkbenchModelApi {
  listModels: () => Promise<UnifiedModelListResponse>
}

interface UseWorkbenchModelsOptions {
  api: WorkbenchModelApi
  locked: boolean
}

export function useWorkbenchModels({ api, locked }: UseWorkbenchModelsOptions) {
  const [models, setModels] = useState<UnifiedModel[]>([])
  const [selectedModel, setSelectedModelState] = useState<UnifiedModel | null>(null)
  const [selectedModelOptions, setSelectedModelOptions] = useState<ModelOptions>({})
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    let cancelled = false

    async function loadModels() {
      setIsLoading(true)
      setError(null)
      try {
        const response = await api.listModels()
        if (!cancelled) {
          const filtered = response.data.filter(isSupportedModelFamily)
          setModels(filtered)
          if (filtered.length > 0) {
            setSelectedModelState(filtered[0])
            setSelectedModelOptions(getDefaultModelOptions(filtered[0]))
          } else {
            setSelectedModelState(null)
            setSelectedModelOptions({})
          }
        }
      } catch (nextError) {
        if (!cancelled) {
          setError(nextError instanceof Error ? nextError : new Error('Failed to load models'))
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false)
        }
      }
    }

    loadModels()
    return () => {
      cancelled = true
    }
  }, [api])

  const setSelectedModel = useCallback(
    (model: UnifiedModel | null) => {
      if (locked) return
      const currentFamily = selectedModel ? inferModelFamily(selectedModel) : null
      const nextFamily = model ? inferModelFamily(model) : null
      setSelectedModelState(model)
      setSelectedModelOptions(current =>
        currentFamily === nextFamily
          ? normalizeModelOptions(model, current)
          : getDefaultModelOptions(model)
      )
    },
    [locked, selectedModel]
  )

  const setSelectedModelOption = useCallback(
    (optionId: string, value: string) => {
      if (locked) return
      setSelectedModelOptions(current => ({ ...current, [optionId]: value }))
    },
    [locked]
  )

  return {
    models,
    selectedModel,
    selectedModelOptions,
    setSelectedModel,
    setSelectedModelOption,
    isLoading,
    error,
  }
}
