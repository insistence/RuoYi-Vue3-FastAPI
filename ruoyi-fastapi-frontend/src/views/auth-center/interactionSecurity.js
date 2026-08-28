export function readInteractionCsrf(hash) {
  if (typeof hash !== 'string') return ''
  return new URLSearchParams(hash.startsWith('#') ? hash.slice(1) : hash).get('csrf') || ''
}

export function interactionRouteLocation(path, interactionId) {
  return `${path}?interaction=${encodeURIComponent(interactionId)}`
}

export function trustedCompletionUrl(url, origin, interactionId) {
  if (typeof url !== 'string' || !url || typeof interactionId !== 'string' || !interactionId) return null
  let target
  try {
    target = new URL(url, origin)
  } catch {
    return null
  }
  const expectedPath = `/auth/interaction/${encodeURIComponent(interactionId)}/complete`
  return target.origin === origin && target.pathname === expectedPath ? target : null
}
