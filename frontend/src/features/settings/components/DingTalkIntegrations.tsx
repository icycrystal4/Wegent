// SPDX-FileCopyrightText: 2025 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

'use client'

import { useEffect, useState } from 'react'
import { ExternalLink, Loader2 } from 'lucide-react'

import { userApis, type DingTalkMcpServiceConfig } from '@/apis/user'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { useToast } from '@/hooks/use-toast'
import { useTranslation } from '@/hooks/useTranslation'

type EditableService = DingTalkMcpServiceConfig & {
  draftUrl: string
}

function DingTalkServiceCard({
  service,
  loading,
  onToggle,
  onUrlChange,
  onSave,
}: {
  service: EditableService
  loading: boolean
  onToggle: (serviceId: string, enabled: boolean) => void
  onUrlChange: (serviceId: string, value: string) => void
  onSave: (serviceId: string) => void
}) {
  const { t } = useTranslation('common')
  const baseKey = `dingtalk.services.${service.service_id}`

  return (
    <div className="space-y-3 rounded-md border border-border bg-base p-4">
      <div className="space-y-1">
        <h3 className="text-base font-medium text-text-primary">{t(`${baseKey}.title`)}</h3>
        <p className="text-sm text-text-muted">{t(`${baseKey}.description`)}</p>
      </div>

      <div className="flex items-center justify-between rounded-md border border-border/70 bg-surface px-3 py-2.5">
        <div className="space-y-0.5 pr-4">
          <Label htmlFor={`dingtalk-${service.service_id}-enabled`} className="text-sm font-medium">
            {t(`${baseKey}.enable_label`)}
          </Label>
          <p className="text-xs text-text-muted">{t(`${baseKey}.enable_hint`)}</p>
        </div>
        <Switch
          id={`dingtalk-${service.service_id}-enabled`}
          checked={service.enabled}
          onCheckedChange={checked => onToggle(service.service_id, checked)}
          disabled={loading}
          data-testid={`toggle-dingtalk-${service.service_id}-switch`}
        />
      </div>

      {service.enabled && (
        <div className="space-y-1.5">
          <Label htmlFor={`dingtalk-${service.service_id}-url`}>{t('dingtalk.url_label')}</Label>
          <Input
            id={`dingtalk-${service.service_id}-url`}
            value={service.draftUrl}
            onChange={event => onUrlChange(service.service_id, event.target.value)}
            placeholder={t('dingtalk.url_placeholder')}
            disabled={loading}
            data-testid={`dingtalk-${service.service_id}-url-input`}
          />
          <p className="text-xs text-text-muted">{t('dingtalk.url_hint')}</p>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 pt-1">
        <Button
          variant="outline"
          type="button"
          onClick={() => window.open(service.detail_url, '_blank', 'noopener,noreferrer')}
          disabled={loading}
          data-testid={`open-dingtalk-${service.service_id}-link-button`}
        >
          <ExternalLink className="mr-2 h-4 w-4" />
          {t('dingtalk.open_link')}
        </Button>
        <Button
          variant="primary"
          type="button"
          onClick={() => onSave(service.service_id)}
          disabled={loading || (service.enabled && !service.draftUrl.trim())}
          data-testid={`save-dingtalk-${service.service_id}-button`}
        >
          {loading ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              {t('dingtalk.saving')}
            </>
          ) : (
            t('dingtalk.save')
          )}
        </Button>
      </div>
    </div>
  )
}

export default function DingTalkIntegrations() {
  const { t } = useTranslation('common')
  const { toast } = useToast()
  const [loading, setLoading] = useState(true)
  const [savingServiceId, setSavingServiceId] = useState<string | null>(null)
  const [services, setServices] = useState<EditableService[]>([])

  useEffect(() => {
    const loadServices = async () => {
      try {
        setLoading(true)
        const configs = await userApis.getDingTalkMcpServices()
        setServices(configs.map(service => ({ ...service, draftUrl: service.url })))
      } catch {
        toast({
          variant: 'destructive',
          title: t('dingtalk.load_failed'),
        })
      } finally {
        setLoading(false)
      }
    }

    loadServices()
  }, [toast, t])

  const updateServiceState = (
    serviceId: string,
    updater: (service: EditableService) => EditableService
  ) => {
    setServices(current =>
      current.map(service => (service.service_id === serviceId ? updater(service) : service))
    )
  }

  const handleToggle = (serviceId: string, enabled: boolean) => {
    updateServiceState(serviceId, service => ({ ...service, enabled }))
  }

  const handleUrlChange = (serviceId: string, draftUrl: string) => {
    updateServiceState(serviceId, service => ({ ...service, draftUrl }))
  }

  const handleSave = async (serviceId: string) => {
    const current = services.find(service => service.service_id === serviceId)
    if (!current) return

    try {
      setSavingServiceId(serviceId)
      const saved = await userApis.updateDingTalkMcpService(serviceId, {
        enabled: current.enabled,
        url: current.draftUrl,
      })

      updateServiceState(serviceId, () => ({ ...saved, draftUrl: saved.url }))
      toast({
        title: t(`dingtalk.services.${serviceId}.save_success`),
      })
    } catch (error) {
      toast({
        variant: 'destructive',
        title: (error as Error)?.message || t(`dingtalk.services.${serviceId}.save_failed`),
      })
    } finally {
      setSavingServiceId(null)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-border bg-base p-4 text-sm text-text-muted">
        <Loader2 className="h-4 w-4 animate-spin" />
        {t('dingtalk.loading')}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {services.map(service => (
        <DingTalkServiceCard
          key={service.service_id}
          service={service}
          loading={savingServiceId === service.service_id}
          onToggle={handleToggle}
          onUrlChange={handleUrlChange}
          onSave={handleSave}
        />
      ))}
    </div>
  )
}
