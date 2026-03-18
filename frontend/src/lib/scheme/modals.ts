// SPDX-FileCopyrightText: 2025 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * Modal handlers for wegent://modal/* scheme URLs
 */

import { registerScheme } from './registry'
import type { SchemeHandlerContext } from './types'

/**
 * Initializes modal mappings
 * This should be called once during app initialization
 */
export function initializeModalMappings(): void {
  registerScheme('modal-dingtalk-mcp-config', {
    pattern: 'wegent://modal/dingtalk-mcp-config',
    handler: (context: SchemeHandlerContext) => {
      const event = new CustomEvent('wegent:open-dialog', {
        detail: {
          type: 'dingtalk-mcp-config',
          params: context.parsed.params,
        },
      })
      window.dispatchEvent(event)
    },
    requireAuth: true,
    description: 'Open DingTalk MCP configuration dialog',
    examples: [
      'wegent://modal/dingtalk-mcp-config',
      'wegent://modal/dingtalk-mcp-config?service=docs',
    ],
  })
}
