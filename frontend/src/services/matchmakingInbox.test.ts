import { afterEach, beforeEach, expect, it, vi } from 'vitest';
const { listNotifications, listProposals } = vi.hoisted(() => ({ listNotifications: vi.fn(), listProposals: vi.fn() }));
vi.mock('./notifications', () => ({ notificationsService: { list: listNotifications } }));
vi.mock('./proposals', () => ({ proposalsService: { list: listProposals } }));
import { watchMatchmakingInbox } from './matchmakingInbox';
let stop: (() => void) | undefined;
beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal('window', Object.assign(new EventTarget(), { setInterval: globalThis.setInterval, clearInterval: globalThis.clearInterval }));
  vi.stubGlobal('document', Object.assign(new EventTarget(), { visibilityState: 'visible' }));
  listNotifications.mockReset().mockResolvedValue({ data: [{ notification_id: 5, is_read: false }] });
  listProposals.mockReset().mockResolvedValue({ data: [{ proposal_id: 42 }] });
});
afterEach(() => { stop?.(); stop = undefined; vi.useRealTimers(); vi.unstubAllGlobals(); });

it('refreshes unread notifications and proposals after ten seconds, and stops on unmount', async () => {
  const update = vi.fn();
  const inbox = watchMatchmakingInbox(update); stop = inbox.stop;
  await vi.advanceTimersByTimeAsync(10_000);
  expect(update).toHaveBeenCalledWith({ notifications: [{ notification_id: 5, is_read: false }], proposals: [{ proposal_id: 42 }] });
  inbox.stop();
  await vi.advanceTimersByTimeAsync(20_000);
  expect(listNotifications).toHaveBeenCalledTimes(1);
});

it('pauses hidden tabs and refreshes when returning to the window', async () => {
  const inbox = watchMatchmakingInbox(vi.fn()); stop = inbox.stop;
  Object.assign(document, { visibilityState: 'hidden' });
  await vi.advanceTimersByTimeAsync(10_000);
  expect(listNotifications).not.toHaveBeenCalled();
  Object.assign(document, { visibilityState: 'visible' });
  window.dispatchEvent(new Event('focus'));
  await vi.advanceTimersByTimeAsync(0);
  expect(listNotifications).toHaveBeenCalledTimes(1);
});

it('keeps the last notifications on a temporary failure and still refreshes proposals', async () => {
  listNotifications.mockRejectedValueOnce(new Error('offline'));
  const update = vi.fn();
  const inbox = watchMatchmakingInbox(update); stop = inbox.stop;
  await inbox.refresh();
  expect(update).toHaveBeenCalledWith({ proposals: [{ proposal_id: 42 }] });
  await inbox.refresh();
  expect(update.mock.lastCall?.[0].notifications).toEqual([{ notification_id: 5, is_read: false }]);
});

it('does not issue overlapping polls or update an unmounted page from an old response', async () => {
  let finish!: (value: unknown) => void;
  listNotifications.mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
  const update = vi.fn();
  const inbox = watchMatchmakingInbox(update); stop = inbox.stop;
  const first = inbox.refresh();
  await inbox.refresh();
  expect(listNotifications).toHaveBeenCalledTimes(1);
  inbox.stop();
  finish({ data: [] });
  await first;
  expect(update).not.toHaveBeenCalled();
});
