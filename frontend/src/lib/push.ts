// Web Push in the browser: support check, permission, subscription (api.md, section 6).
// The requests to the backend are in api/push.ts

import { deletePushSubscription, getVapidPublicKey, savePushSubscription } from '@/api/push'
import type { PushSubscriptionBody } from '@/api/types'

// unsupported: no push here (http, an old browser, iOS, which we do not support, see docs/frontend/pwa.md,
//   or the dev server, which has no service worker)
// denied: blocked in the browser settings, the app cannot ask again
export type PushState = 'unsupported' | 'denied' | 'disabled' | 'enabled'

function hasPushApi(): boolean {
  return window.isSecureContext && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window
}

// the service worker is registered only in the build (npm run build && npm run preview), not by npm run dev
async function registration(): Promise<ServiceWorkerRegistration | null> {
  if (!('serviceWorker' in navigator)) return null
  return (await navigator.serviceWorker.getRegistration()) ?? null
}

export async function getPushState(): Promise<PushState> {
  if (!hasPushApi()) return 'unsupported'
  const reg = await registration()
  if (!reg) return 'unsupported'
  if (Notification.permission === 'denied') return 'denied'
  if (Notification.permission !== 'granted') return 'disabled'
  return (await reg.pushManager.getSubscription()) ? 'enabled' : 'disabled'
}

// base64url (the format of the VAPID key) -> bytes for pushManager.subscribe
export function keyToBytes(key: string): Uint8Array<ArrayBuffer> {
  const base64 = (key + '='.repeat((4 - (key.length % 4)) % 4)).replace(/-/g, '+').replace(/_/g, '/')
  return Uint8Array.from(atob(base64), (c) => c.charCodeAt(0))
}

function sameKey(a: ArrayBuffer | null | undefined, b: Uint8Array): boolean {
  if (!a || a.byteLength !== b.length) return false
  const bytes = new Uint8Array(a)
  return bytes.every((byte, i) => byte === b[i])
}

// e.g. "Android – Chrome", so the forester can tell their devices apart
export function deviceLabel(userAgent = navigator.userAgent): string {
  const system = /Android/.test(userAgent)
    ? 'Android'
    : /iPhone|iPod/.test(userAgent)
      ? 'iPhone'
      : /iPad/.test(userAgent)
        ? 'iPad'
        : /Windows/.test(userAgent)
          ? 'Windows'
          : /Mac OS X/.test(userAgent)
            ? 'macOS'
            : /Linux/.test(userAgent)
              ? 'Linux'
              : null
  // order matters: Edge and Samsung Internet also say "Chrome", Chrome also says "Safari"
  const browser = /Edg/.test(userAgent)
    ? 'Edge'
    : /SamsungBrowser/.test(userAgent)
      ? 'Samsung Internet'
      : /Firefox|FxiOS/.test(userAgent)
        ? 'Firefox'
        : /Chrome|CriOS/.test(userAgent)
          ? 'Chrome'
          : /Safari/.test(userAgent)
            ? 'Safari'
            : null
  return [system, browser].filter(Boolean).join(' – ') || 'Nieznane urządzenie'
}

// Asks for permission and registers this device. Call it from a click: browsers ignore
// a permission request that the user did not start. Also safe to call again when already enabled
export async function enablePush(): Promise<PushState> {
  const reg = await registration()
  if (!reg || !hasPushApi()) return 'unsupported'

  const permission = await Notification.requestPermission()
  if (permission === 'denied') return 'denied'
  if (permission !== 'granted') return 'disabled'

  const key = keyToBytes(await getVapidPublicKey())
  let subscription = await reg.pushManager.getSubscription()
  // made with another server key (e.g. new keys on the server): the browser would refuse to subscribe again
  if (subscription && !sameKey(subscription.options.applicationServerKey, key)) {
    await subscription.unsubscribe()
    subscription = null
  }
  subscription ??= await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key })

  await savePushSubscription({ ...(subscription.toJSON() as PushSubscriptionBody), device_label: deviceLabel() })
  return 'enabled'
}

// On logout: the next person on this phone must not get the previous user's alarms.
// Never fails: logging out must work also without the network
export async function disablePush(token: string | null): Promise<void> {
  try {
    const subscription = await (await registration())?.pushManager.getSubscription()
    if (!subscription) return
    await deletePushSubscription(subscription.endpoint, token).catch(() => {})
    await subscription.unsubscribe()
  } catch {
    // best effort: logging out must not get stuck on this
  }
}
