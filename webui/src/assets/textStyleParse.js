export class MyDomElement {
  constructor(tagName = '', tagValue = '') {
    this.tagName = tagName
    this.tagValue = tagValue
    this.children = []
  }
}

const IMPLICIT_SELF_CLOSING_TAGS = new Set(['icon', 'br'])

function parseTagToken(rawToken) {
  let token = rawToken.trim()
  if (!token) {
    return { tagName: '', tagValue: '', isClosing: false, isSelfClosing: false }
  }

  let isClosing = false
  let isSelfClosing = false

  if (token.startsWith('/')) {
    isClosing = true
    token = token.slice(1).trim()
  }

  if (!isClosing && token.endsWith('/')) {
    isSelfClosing = true
    token = token.slice(0, -1).trim()
  }

  const nameEnd = token.search(/[\s=]/)
  const tagName = (nameEnd === -1 ? token : token.slice(0, nameEnd)).trim().toLowerCase()
  const rawValue = nameEnd === -1 ? '' : token.slice(nameEnd).trim()
  const tagValue = rawValue.startsWith('=') ? rawValue.slice(1).trim() : rawValue

  if (IMPLICIT_SELF_CLOSING_TAGS.has(tagName)) {
    isSelfClosing = true
  }

  return { tagName, tagValue, isClosing, isSelfClosing }
}

export function parse(text) {
  if (!text) {
    return []
  }

  const root = new MyDomElement('root', '')
  const stack = [root]
  const tagPattern = /<[^>]+>/g
  let cursor = 0
  let match = tagPattern.exec(text)

  while (match) {
    if (match.index > cursor) {
      stack[stack.length - 1].children.push(text.slice(cursor, match.index))
    }

    const token = match[0].slice(1, -1)
    const parsedToken = parseTagToken(token)

    if (!parsedToken.tagName) {
      stack[stack.length - 1].children.push(match[0])
      cursor = tagPattern.lastIndex
      match = tagPattern.exec(text)
      continue
    }

    if (parsedToken.isClosing) {
      while (stack.length > 1) {
        const current = stack.pop()
        if (current.tagName === parsedToken.tagName) {
          break
        }
      }
    } else {
      const element = new MyDomElement(parsedToken.tagName, parsedToken.tagValue)
      stack[stack.length - 1].children.push(element)
      if (!parsedToken.isSelfClosing) {
        stack.push(element)
      }
    }

    cursor = tagPattern.lastIndex
    match = tagPattern.exec(text)
  }

  if (cursor < text.length) {
    stack[stack.length - 1].children.push(text.slice(cursor))
  }

  return root.children
}
