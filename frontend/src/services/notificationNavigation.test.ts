import { expect, it } from 'vitest';
import { selectedProposalFromHash } from './notificationNavigation';
it('reads a proposal email target only from the notifications route and rejects malformed IDs', () => {
  expect(selectedProposalFromHash('#/notifications?proposal_id=30002')).toBe(30002);
  expect(selectedProposalFromHash('#/matchmaking?proposal_id=30002')).toBeNull();
  for (const value of ['', '0', '-1', '1.5', '1e3', '9007199254740993', 'abc']) {
    expect(selectedProposalFromHash(`#/notifications?proposal_id=${value}`)).toBeNull();
  }
});
