export function normalizeDisplayText(value) {
  if (typeof value !== 'string') {
    return ''
  }
  return value.replace(/\r\n/g, '\n').replace(/\r/g, '\n').replace(/\\n/g, '\n')
}

export function toCopyableText(value) {
  return normalizeDisplayText(value).replace(/<[^>]+>/g, '').trim()
}
