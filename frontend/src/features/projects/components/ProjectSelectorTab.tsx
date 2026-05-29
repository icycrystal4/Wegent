// SPDX-FileCopyrightText: 2025 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

'use client'

import { ChevronDown, FolderOpen, FolderX } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { useProjectContext } from '../contexts/projectContext'
import { useChatStreamContext } from '@/features/tasks/contexts/chatStreamContext'
import { useTaskContext } from '@/features/tasks/contexts/taskContext'
import type { ProjectWithTasks } from '@/types/api'
import { useTranslation } from '@/hooks/useTranslation'
import { paths } from '@/config/paths'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown'
import { saveLastWorkspaceProjectId } from '../utils/projectSelection'

interface ProjectSelectorTabProps {
  projectId?: number | null
  disabled?: boolean
}

export function ProjectSelectorTab({ projectId, disabled }: ProjectSelectorTabProps) {
  const router = useRouter()
  const { t } = useTranslation('projects')
  const { projects, setSelectedProjectTaskId } = useProjectContext()
  const { clearAllStreams } = useChatStreamContext()
  const { setSelectedTask } = useTaskContext()

  const currentProject = projects.find(p => p.id === projectId)
  const workspaceProjects = projects.filter(p => p.config?.mode === 'workspace')
  const displayName = currentProject?.name ?? t('workspace.enterProjectWork')

  const handleSwitchProject = (project: ProjectWithTasks) => {
    if (project.id === projectId) return
    clearAllStreams()
    setSelectedTask(null)
    setSelectedProjectTaskId(null)
    saveLastWorkspaceProjectId(project.id)
    const params = new URLSearchParams()
    params.set('projectId', String(project.id))
    const deviceId = project.config?.execution?.deviceId
    if (deviceId) {
      params.set('deviceId', deviceId)
    }
    router.push(`/devices/chat?${params.toString()}`)
  }

  const handleUseNoProject = () => {
    clearAllStreams()
    setSelectedTask(null)
    setSelectedProjectTaskId(null)
    const params = new URLSearchParams()
    params.set('projectMode', 'none')
    router.push(`${paths.chat.getHref()}?${params.toString()}`)
  }

  if (disabled) {
    return (
      <div
        data-testid="project-selector-tab"
        className="flex items-center gap-1 min-w-0 rounded-[24px] pl-2.5 pr-3 py-2.5 h-9 bg-transparent text-text-primary opacity-80 cursor-not-allowed"
      >
        <FolderOpen className="w-4 h-4 flex-shrink-0" />
        <span className="max-w-[120px] truncate text-xs min-w-0">{displayName}</span>
      </div>
    )
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        data-testid="project-selector-tab"
        className="flex items-center gap-1 min-w-0 rounded-[24px] pl-2.5 pr-3 py-2.5 h-9 bg-transparent text-text-primary hover:bg-hover transition-colors focus:outline-none focus:ring-0"
      >
        <FolderOpen className="w-4 h-4 flex-shrink-0" />
        <span className="max-w-[120px] truncate text-xs min-w-0">{displayName}</span>
        <ChevronDown className="w-2.5 h-2.5 flex-shrink-0 opacity-60" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-[160px]">
        {workspaceProjects.map(project => (
          <DropdownMenuItem
            key={project.id}
            onClick={() => handleSwitchProject(project)}
            className={project.id === projectId ? 'bg-primary/10' : ''}
          >
            <FolderOpen className="w-3.5 h-3.5 mr-2 text-primary" />
            <span className="truncate">{project.name}</span>
          </DropdownMenuItem>
        ))}
        {currentProject && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={handleUseNoProject}
              data-testid="project-selector-no-project"
            >
              <FolderX className="w-3.5 h-3.5 mr-2 text-text-muted" />
              <span className="truncate">{t('workspace.noProject')}</span>
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
