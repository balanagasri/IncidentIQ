import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';

describe('IncidentIQ UI source', () => {
  it('labels synthetic data and shows the Hindsight evidence workflow', () => {
    const source = readFileSync(new URL('./App.tsx', import.meta.url), 'utf8');
    expect(source).toContain('SYNTHETIC DEMO DATA');
    expect(source).toContain('Hindsight evidence');
    expect(source).toContain('Record outcome + retain memory');
    expect(source).toContain('UNKNOWN');
  });
});
