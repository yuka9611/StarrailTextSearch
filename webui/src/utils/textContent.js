export function normalizeDisplayText(value) {
  if (typeof value !== 'string') {
    return ''
  }
  return value
    .replace(/<\/?unbreak>/gi, '')
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .replace(/\\n/g, '\n')
}

const ANY_TAG_PATTERN = /<[^>]+>/g
const COLOR_TAG_PATTERN = /^<\s*\/?\s*color(?:\s*=\s*[^>]+|\s*)>$/i

export function toPlainText(value) {
  return normalizeDisplayText(value).replace(ANY_TAG_PATTERN, '').trim()
}

export function toCopyableText(value) {
  return normalizeDisplayText(value)
    .replace(ANY_TAG_PATTERN, (tag) => (COLOR_TAG_PATTERN.test(tag) ? tag : ''))
    .trim()
}
