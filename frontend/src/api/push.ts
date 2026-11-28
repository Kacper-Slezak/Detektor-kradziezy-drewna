// Web Push endpoints (api.md, section 6). Only a forester gets pushes

import { USE_MOCK, apiFetch, getToken } from './client'
import { mockDeletePushSubscription, mockSavePushSubscription, mockVapidPublicKey } from './mock'
import type { PushSubscriptionBody } from './types'

// Server key for pushManager.subscribe, base64url. Not built into the app: it comes from the backend
export async function getVapidPublicKey(): Promise<string> {
  if (USE_MOCK) return mockVapidPublicKey(getToken())
  const { public_key } = await apiFetch<{ public_key: string }>('/push/vapid-public-key')
  return public_key
}

// The same endpoint sent again replaces the keys and the owner, so it is safe to send on every sign-in
export function savePushSubscription(subscription: PushSubscriptionBody): Promise<void> {
  if (USE_MOCK) return mockSavePushSubscription(getToken(), subscription)
  return apiFetch<void>('/push/subscriptions', {
    method: 'POST',
    body: JSON.stringify(subscription),
  })
}

// On logout. The token is passed in, because logout clears it before this request is sent
export function deletePushSubscription(endpoint: string, token = getToken()): Promise<void> {
  if (USE_MOCK) return mockDeletePushSubscription(token, endpoint)
  return apiFetch<void>(`/push/subscriptions?endpoint=${encodeURIComponent(endpoint)}`, {
    method: 'DELETE',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
}
