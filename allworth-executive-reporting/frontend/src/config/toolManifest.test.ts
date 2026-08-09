import { describe, expect, it } from 'vitest';
import { assignableTools, assignmentPresets, toolManifest, tools } from './toolManifest';

describe('canonical tool manifest', () => {
  it('contains unique tool ids and navigation targets', () => {
    expect(new Set(tools.map((tool) => tool.id)).size).toBe(tools.length);
    for (const tool of tools) {
      expect(tool.id).toMatch(/^[a-z0-9_]+$/);
      for (const item of tool.navigation) {
        expect(item.href.startsWith('/')).toBe(true);
        expect(item.matches.length).toBeGreaterThan(0);
      }
    }
  });

  it('keeps unavailable tools out of assignment presets', () => {
    const assignableIds = new Set(assignableTools.map((tool) => tool.id));
    for (const preset of Object.values(assignmentPresets)) {
      expect(new Set(preset).size).toBe(preset.length);
      expect(preset.every((toolId) => assignableIds.has(toolId))).toBe(true);
    }
  });

  it('provides functional widgets for every assignable tool', () => {
    for (const tool of assignableTools) expect(tool.widget, tool.id).toBeDefined();
  });

  it('uses a supported manifest schema version', () => {
    expect(toolManifest.version).toBe(1);
  });
});
