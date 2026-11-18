async function req(path, opts = {}) {
  const r = await fetch('/api' + path, {
    headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
    ...opts,
  })
  const text = await r.text()
  let data = null
  try { data = text ? JSON.parse(text) : null } catch { data = text }
  if (!r.ok) {
    const detail = (data && data.detail) || text || r.statusText
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return data
}

const q = (day) => (day ? `?business_day=${encodeURIComponent(day)}` : '')

export const api = {
  dashboard: () => req('/dashboard'),
  campaigns: () => req('/campaigns'),
  events: (day) => req('/events' + q(day)),
  addEvent: (body) => req('/events', { method: 'POST', body: JSON.stringify(body) }),
  facts: (day) => req('/facts' + q(day)),
  preview: (day) => req('/redeem/preview' + q(day)),
  seal: (body) => req('/redeem/seal', { method: 'POST', body: JSON.stringify(body) }),
  batches: (day, kind) => {
    const p = new URLSearchParams()
    if (day) p.set('business_day', day)
    if (kind) p.set('batch_kind', kind)
    const s = p.toString()
    return req('/batches' + (s ? `?${s}` : ''))
  },
  batch: (id) => req(`/batches/${id}`),
  returns: (day) => req('/returns' + q(day)),
  returnsPreview: (day) => req('/returns/preview' + q(day)),
  addReturn: (body) => req('/returns', { method: 'POST', body: JSON.stringify(body) }),
  sealReturns: (body) => req('/returns/seal', { method: 'POST', body: JSON.stringify(body) }),
  reconciliation: (day) => req('/reconciliation' + q(day)),
  returnPolicy: () => req('/settings/return-policy'),
  setReturnPolicy: (policy) =>
    req('/settings/return-policy', { method: 'PUT', body: JSON.stringify({ policy }) }),
  getDay: () => req('/settings/day'),
  setDay: (business_day) => req('/settings/day', { method: 'PUT', body: JSON.stringify({ business_day }) }),
}
