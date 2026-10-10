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

  it('distinguishes recalled, selected, and recommendation-cited memories', () => {
    const source = readFileSync(new URL('./App.tsx', import.meta.url), 'utf8');
    expect(source).toContain('evidence_memory_ids');
    expect(source).toContain('selected for reasoning');
    expect(source).toContain('Based on recalled Hindsight memory:');
    expect(source).toContain('citation?.reason');
    expect(source).toContain('No recalled memory was cited by the recommendation.');
    expect(source).toContain('compactEvidence(text)');
  });

  it('exposes measured analytics, live retrieval evaluation, comparisons, and postmortems', () => {
    const source = readFileSync(new URL('./App.tsx', import.meta.url), 'utf8');
    expect(source).toContain('Memory analytics');
    expect(source).toContain('/api/evaluations/run');
    expect(source).toContain('SIMILAR INCIDENT COMPARISON');
    expect(source).toContain('Finalize + retain in Hindsight');
    expect(source).toContain('Integration status');
    expect(source).toContain('does not probe remote services');
  });
});
