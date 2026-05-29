// SPDX-FileCopyrightText: 2026 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

import type { ProjectWithTasks } from '@/types/api'
import { isWorkspaceProject } from './projectClassification'

const LAST_WORKSPACE_PROJECT_ID_KEY = 'wegent:last-workspace-project-id'

export function saveLastWorkspaceProjectId(projectId: number): void {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(LAST_WORKSPACE_PROJECT_ID_KEY, String(projectId))
}

export function getLastWorkspaceProjectId(projects: ProjectWithTasks[]): number | null {
  if (typeof window === 'undefined') return null
  const rawProjectId = window.localStorage.getItem(LAST_WORKSPACE_PROJECT_ID_KEY)
  if (!rawProjectId) return null

  const projectId = Number(rawProjectId)
  if (!Number.isInteger(projectId)) return null

  const project = projects.find(item => item.id === projectId)
  if (!project || !isWorkspaceProject(project)) return null

  return projectId
}
