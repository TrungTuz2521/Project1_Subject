import { notificationsService } from './notifications';
import { proposalsService } from './proposals';
import type { Notification, Proposal } from '../types/api';

/** Refresh only inbox data, without resetting forms or reloading the whole page. */
export function watchMatchmakingInbox(onUpdate: (data: { notifications?: Notification[]; proposals?: Proposal[] }) => void) {
  let active = true;
  let inFlight = false;
  const controller = new AbortController();
  const refresh = async () => {
    if (!active || inFlight || document.visibilityState === 'hidden') return;
    inFlight = true;
    try {
      const [notifications, proposals] = await Promise.allSettled([
        notificationsService.list(1, undefined, controller.signal),
        proposalsService.list(1, undefined, controller.signal),
      ]);
      if (!active) return;
      // A temporary network error keeps the last successfully loaded information visible.
      onUpdate({ ...(notifications.status === 'fulfilled' ? { notifications: notifications.value.data } : {}),
        ...(proposals.status === 'fulfilled' ? { proposals: proposals.value.data } : {}) });
    } finally { inFlight = false; }
  };
  const onFocus = () => { void refresh(); };
  const timer = window.setInterval(onFocus, 10_000);
  window.addEventListener('focus', onFocus);
  document.addEventListener('visibilitychange', onFocus);
  return { refresh, stop() {
    active = false; controller.abort(); window.clearInterval(timer);
    window.removeEventListener('focus', onFocus);
    document.removeEventListener('visibilitychange', onFocus);
  } };
}
