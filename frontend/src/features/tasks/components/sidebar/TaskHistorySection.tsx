// SPDX-FileCopyrightText: 2025 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

'use client'

import { useCallback, useMemo } from 'react'
import { Archive, ChevronDown, MoreHorizontal, Plus, Search, Settings2 } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { useTranslation } from '@/hooks/useTranslation'
import { DroppableHistory, ProjectSection, useProjectContext } from '@/features/projects'
import type { Task } from '@/types/api'
import TaskListSection from './TaskListSection'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown'
import { Button } from '@/components/ui/button'
import { paths } from '@/config/paths'
import { useChatStreamContext } from '@/features/tasks/contexts/chatStreamContext'
import { useTaskContext } from '@/features/tasks/contexts/taskContext'
import { taskApis } from '@/apis/tasks'
import { toast } from 'sonner'

interface TaskHistorySectionProps {
  groupTasks: Task[]
  personalTasks: Task[]
  isCollapsed: boolean
  hasMorePersonalTasks: boolean
  loadMorePersonalTasks: () => void
  loadingMorePersonalTasks: boolean
  viewStatusVersion: number
  getUnreadCount: (tasks: Task[]) => number
  totalUnreadCount: number
  handleMarkAllAsViewed: () => void
  handleOpenSearchDialog: () => void
  shortcutDisplayText: string
  setIsMobileSidebarOpen: (open: boolean) => void
  isSearchResult: boolean
  onTaskSelect: () => void
  setIsHistoryManageDialogOpen?: (open: boolean) => void
}

/**
 * Uses useProjectContext to filter tasks.
 * This component must be rendered within ProjectProvider.
 */
export default function TaskHistorySection({
  groupTasks,
  personalTasks,
  isCollapsed,
  hasMorePersonalTasks,
  loadMorePersonalTasks,
  loadingMorePersonalTasks,
  viewStatusVersion,
  getUnreadCount,
  totalUnreadCount,
  handleMarkAllAsViewed,
  handleOpenSearchDialog,
  shortcutDisplayText,
  setIsMobileSidebarOpen,
  isSearchResult,
  onTaskSelect,
  setIsHistoryManageDialogOpen,
}: TaskHistorySectionProps) {
  const { t } = useTranslation()
  const router = useRouter()
  const { clearAllStreams } = useChatStreamContext()
  const { refreshTasks, setSelectedTask } = useTaskContext()
  const { projectTaskIds, projects, setSelectedProjectTaskId } = useProjectContext()

  // Filter out tasks that are already in projects from history lists.
  const filteredPersonalTasks = useMemo(
    () => personalTasks.filter(task => !projectTaskIds.has(task.id)),
    [personalTasks, projectTaskIds]
  )
  const filteredGroupTasks = useMemo(
    () => groupTasks.filter(task => !projectTaskIds.has(task.id)),
    [groupTasks, projectTaskIds]
  )

  const hasProjectsWithTasks = projects.some(project => project.tasks && project.tasks.length > 0)

  const handleNewChat = useCallback(() => {
    clearAllStreams()
    setSelectedTask(null)
    setSelectedProjectTaskId(null)
    const params = new URLSearchParams()
    params.set('projectMode', 'none')
    router.push(`${paths.chat.getHref()}?${params.toString()}`)
    setIsMobileSidebarOpen(false)
    onTaskSelect()
  }, [
    clearAllStreams,
    onTaskSelect,
    router,
    setIsMobileSidebarOpen,
    setSelectedProjectTaskId,
    setSelectedTask,
  ])

  const handleArchiveAllChats = useCallback(async () => {
    try {
      const response = await taskApis.archiveAllChats()
      clearAllStreams()
      setSelectedTask(null)
      setSelectedProjectTaskId(null)
      router.replace(`${paths.chat.getHref()}?projectMode=none`)
      await refreshTasks()
      toast.success(t('common:tasks.archive_all_success', { count: response.count }))
    } catch (err) {
      console.error('[TaskHistorySection] Failed to archive chats:', err)
      toast.error(t('common:tasks.archive_all_failed'))
    }
  }, [clearAllStreams, refreshTasks, router, setSelectedProjectTaskId, setSelectedTask, t])

  if (
    filteredGroupTasks.length === 0 &&
    filteredPersonalTasks.length === 0 &&
    !hasProjectsWithTasks &&
    isCollapsed
  ) {
    return (
      <div className="text-center py-8 text-xs text-text-muted">{t('common:tasks.no_tasks')}</div>
    )
  }

  return (
    <>
      {!isCollapsed && !isSearchResult && <ProjectSection onTaskSelect={onTaskSelect} />}

      {(!isSearchResult || filteredPersonalTasks.length > 0) && (
        <DroppableHistory>
          {!isCollapsed && (
            <div className="px-1 pb-1 pt-2 mt-1.5 border-t border-border-light text-xs font-medium text-text-muted flex items-center justify-between">
              <div className="flex items-center gap-1">
                {setIsHistoryManageDialogOpen ? (
                  <TooltipProvider>
                    <Tooltip delayDuration={300}>
                      <TooltipTrigger asChild>
                        <button
                          onClick={() => setIsHistoryManageDialogOpen(true)}
                          className="flex items-center gap-1 hover:text-text-primary transition-colors group"
                          data-testid="chats-history-manage-button"
                        >
                          <span className="group-hover:underline">
                            {t('common:tasks.chats_title')}
                          </span>
                          <Settings2 className="h-3 w-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                        </button>
                      </TooltipTrigger>
                      <TooltipContent side="right">
                        <p>{t('history:actions.search')}</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                ) : (
                  <span>{t('common:tasks.chats_title')}</span>
                )}
              </div>
              <div className="flex items-center gap-1">
                {totalUnreadCount > 0 && (
                  <button
                    onClick={handleMarkAllAsViewed}
                    className="text-xs text-text-muted hover:text-text-primary transition-colors whitespace-nowrap"
                  >
                    {t('common:tasks.mark_all_read')}
                  </button>
                )}
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-5 w-5 p-0 text-text-muted hover:text-text-primary transition-colors rounded"
                      data-testid="chats-section-menu-button"
                      title={t('common:tasks.more_actions')}
                    >
                      <MoreHorizontal className="h-3.5 w-3.5" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-36">
                    <DropdownMenuItem
                      onClick={handleArchiveAllChats}
                      data-testid="archive-all-chats-menu-item"
                    >
                      <Archive className="h-3.5 w-3.5 mr-2" />
                      {t('common:tasks.archive_all')}
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-5 w-5 p-0 text-text-muted hover:text-text-primary transition-colors rounded"
                  onClick={handleNewChat}
                  data-testid="chats-new-conversation-button"
                  title={t('common:tasks.new_conversation')}
                >
                  <Plus className="h-3.5 w-3.5" />
                </Button>
                <TooltipProvider>
                  <Tooltip delayDuration={300}>
                    <TooltipTrigger asChild>
                      <button
                        onClick={handleOpenSearchDialog}
                        className="p-0.5 text-text-muted hover:text-text-primary transition-colors rounded"
                        aria-label={t('common:tasks.search_placeholder_chat')}
                      >
                        <Search className="h-3.5 w-3.5" />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="right">
                      <p>
                        {shortcutDisplayText
                          ? t('common:tasks.search_hint_with_shortcut', {
                              shortcut: shortcutDisplayText,
                            })
                          : t('common:tasks.search_placeholder_chat')}
                      </p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </div>
            </div>
          )}
          {filteredPersonalTasks.length > 0 ? (
            <TaskListSection
              tasks={filteredPersonalTasks}
              title=""
              unreadCount={getUnreadCount(filteredPersonalTasks)}
              onTaskClick={() => setIsMobileSidebarOpen(false)}
              isCollapsed={isCollapsed}
              showTitle={false}
              enableDrag={true}
              key={`regular-tasks-${viewStatusVersion}`}
            />
          ) : (
            !isCollapsed && (
              <div className="px-4 py-2 text-xs text-text-muted">{t('common:tasks.no_tasks')}</div>
            )
          )}
          {hasMorePersonalTasks && !isCollapsed && (
            <button
              type="button"
              data-testid="load-more-personal-tasks-button"
              onClick={() => {
                void loadMorePersonalTasks()
              }}
              disabled={loadingMorePersonalTasks}
              className="flex h-11 min-w-[44px] w-full items-center gap-1 rounded-xl px-3 text-xs font-medium text-text-muted transition-colors hover:bg-hover hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-60"
            >
              <ChevronDown className="h-3.5 w-3.5" />
              <span>
                {loadingMorePersonalTasks ? t('common:tasks.loading') : t('common:tasks.load_more')}
              </span>
            </button>
          )}
          {loadingMorePersonalTasks && (
            <div className="text-center py-2 text-xs text-text-muted">
              {t('common:tasks.loading')}
            </div>
          )}
        </DroppableHistory>
      )}
    </>
  )
}
