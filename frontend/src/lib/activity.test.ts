import { describe, expect, it } from 'vitest';
import { describeActivity } from './activity';
import type { Step } from './types';

const step = (over: Partial<Step>): Step => ({ id: 's', kind: 'tool', title: 'Searching the web', status: 'done', ts: '', ...over });

describe('describeActivity', () => {
  it('says what is being searched, quoting the query', () => {
    const a = describeActivity([step({ id: 'c1', tool: 'web_search', detail: 'Nvidia stock price current value', status: 'running' })], 'agent');
    expect(a.phrases).toEqual(['Searching “Nvidia stock price current value”…']);
  });

  it('lists the sites being read once results arrive', () => {
    const a = describeActivity(
      [step({ id: 'c1', tool: 'web_search', items: [{ title: 'NVDA', url: 'https://www.reuters.com/a' }, { title: 'x', url: 'https://finance.yahoo.com/b' }] })],
      'agent',
    );
    expect(a.phrases).toEqual(['Reading reuters.com…', 'Reading finance.yahoo.com…', 'Putting the answer together…']);
    expect(a.sites).toEqual(['reuters.com', 'finance.yahoo.com']);
  });

  it('follows Deep research stages and parallel searches', () => {
    expect(describeActivity([step({ id: 'research-plan', kind: 'thinking', status: 'running' })], 'agent').phrases[0]).toBe('Planning the research…');
    const parallel = describeActivity(
      [step({ id: 'research-1-0', detail: 'vanguard holdings', status: 'running' }), step({ id: 'research-1-1', detail: 'vanguard 13f', status: 'running' })],
      'agent',
    );
    expect(parallel.phrases).toEqual(['Searching “vanguard holdings”…', 'Searching “vanguard 13f”…']);
    expect(describeActivity([step({ id: 'research-write', kind: 'thinking', status: 'running' })], 'agent').phrases[0]).toBe('Writing the report…');
  });

  it('never mentions memory steps, and falls back to the route', () => {
    const a = describeActivity([step({ id: 'memory-save', kind: 'memory', title: 'Updated long-term memory' })], 'chat');
    expect(a.phrases).toEqual(['Thinking…']);
    expect(describeActivity([], undefined).phrases[1]).toBe('Choosing a route…');
    expect(describeActivity([step({ id: 'q', tool: 'query_spreadsheet', status: 'running', title: 'Calculating' })], 'agent').phrases).toEqual(['Crunching the numbers…']);
  });
});
