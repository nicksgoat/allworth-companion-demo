import manifestJson from '../../../tool-manifest.json';
import type { AssignmentType } from '../services/admin';

export type ToolStatus = 'live' | 'new' | 'soon';
export type ToolCategory = 'live' | 'analytics' | 'utilities';

export interface ToolNavigationItem {
  href: string;
  label: string;
  advisor_label?: string;
  matches: string[];
  group: string;
}

export interface ToolWidgetConfig {
  kind?: 'core';
  endpoint?: string;
  count_path?: string[];
  count_label?: string;
  action?: 'search';
  eyebrow?: string;
}

export interface ToolDefinition {
  id: string;
  name: string;
  kicker: string;
  description: string;
  url: string | null;
  category: ToolCategory;
  color: 'navy' | 'orange' | 'sky' | 'slate' | 'teal';
  status: ToolStatus;
  icon: string;
  navigation: ToolNavigationItem[];
  widget?: ToolWidgetConfig;
}

interface ToolManifest {
  version: number;
  assignment_presets: Record<AssignmentType, string[]>;
  sections: Record<ToolCategory, { label: string; nav_label: string; description: string }>;
  tools: ToolDefinition[];
}

export const toolManifest = manifestJson as ToolManifest;
export const tools = toolManifest.tools;
export const assignableTools = tools.filter((tool) => tool.status !== 'soon');
export const assignmentPresets = toolManifest.assignment_presets;
export const toolById = new Map(tools.map((tool) => [tool.id, tool]));

export function toolsForCategory(category: ToolCategory): ToolDefinition[] {
  return tools.filter((tool) => tool.category === category);
}
