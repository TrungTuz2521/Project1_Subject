export function selectedProposalFromHash(hash: string): number | null {
  const [route, query = ''] = hash.replace(/^#/, '').split('?');
  if (route !== '/notifications') return null;
  const value = new URLSearchParams(query).get('proposal_id');
  if (!value || !/^[1-9]\d*$/.test(value)) return null;
  const id = Number(value);
  return Number.isSafeInteger(id) ? id : null;
}
