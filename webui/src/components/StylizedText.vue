<script setup>
import { onMounted, ref, watch } from 'vue'

import * as textStyleParser from '@/assets/textStyleParse'
import { normalizeDisplayText } from '@/utils/textContent'

const props = defineProps({
  text: {
    type: String,
    default: ''
  },
  keyword: {
    type: String,
    default: ''
  }
})

const textWrapper = ref(null)
const loweredKeyword = ref('')

function getLines(text) {
  const normalized = normalizeDisplayText(text)
  if (!normalized) {
    return []
  }
  return normalized.split(/\n/)
}

function getAllOccurrences(text, keyword) {
  const indexes = []
  if (!text || !keyword) {
    return indexes
  }

  let cursor = 0
  while (cursor !== -1) {
    cursor = text.indexOf(keyword, cursor)
    if (cursor !== -1) {
      indexes.push(cursor)
      cursor += keyword.length
    }
  }
  return indexes
}

function createContainerElement(node) {
  const container = document.createElement('span')

  switch (node.tagName) {
    case 'color': {
      const colorValue = stripQuotes(node.tagValue || '')
      if (colorValue && colorValue.toLowerCase() !== '#ffffff' && colorValue.toLowerCase() !== '#ffffffff') {
        container.style.color = colorValue
      }
      break
    }
    case 'i':
      container.style.fontStyle = 'italic'
      break
    case 'b':
      container.style.fontWeight = '700'
      break
    case 'u':
      container.style.textDecoration = 'underline'
      break
    case 'size': {
      const sizeValue = parseInt(stripQuotes(node.tagValue || ''), 10)
      if (Number.isFinite(sizeValue)) {
        container.style.fontSize = `${sizeValue}px`
      }
      break
    }
    case 'align': {
      const alignValue = stripQuotes(node.tagValue || '').toLowerCase()
      if (alignValue) {
        container.style.display = 'block'
        container.style.textAlign = alignValue
      }
      break
    }
    case 'unbreak':
      container.style.whiteSpace = 'nowrap'
      break
    case 'icon':
      container.style.display = 'inline-block'
      container.style.width = '0'
      container.style.height = '0'
      break
    default:
      break
  }

  return container
}

function iterateNode(node, lines, containerStack, labelStack) {
  let container = containerStack[containerStack.length - 1]
  if (node.tagName !== 'root') {
    labelStack.push(node)
  }

  for (const child of node.children) {
    if (typeof child === 'string') {
      const lineParts = getLines(child)
      for (let index = 0; index < lineParts.length; index += 1) {
        const line = lineParts[index]

        if (index > 0) {
          const paragraph = document.createElement('p')
          lines.push(paragraph)
          containerStack[0] = paragraph

          let rebuiltContainer = null
          let stackIndex = 1
          for (const label of labelStack) {
            const nextContainer = createContainerElement(label)
            if (rebuiltContainer) {
              rebuiltContainer.append(nextContainer)
            } else {
              paragraph.append(nextContainer)
            }
            rebuiltContainer = nextContainer
            containerStack[stackIndex] = nextContainer
            stackIndex += 1
          }
          container = rebuiltContainer || paragraph
        }

        if (line.length === 0) {
          container.append(document.createElement('br'))
          continue
        }

        appendHighlightedText(container, line)
      }
    } else {
      const childContainer = createContainerElement(child)
      containerStack.push(childContainer)
      container.append(childContainer)
      iterateNode(child, lines, containerStack, labelStack)
    }
  }

  if (node.tagName !== 'root') {
    labelStack.pop()
    containerStack.pop()
  }
}

function appendHighlightedText(container, line) {
  if (!props.keyword) {
    container.append(line)
    return
  }

  const occurrences = getAllOccurrences(line.toLowerCase(), loweredKeyword.value)
  if (occurrences.length === 0) {
    container.append(line)
    return
  }

  let cursor = 0
  for (const startIndex of occurrences) {
    if (cursor < startIndex) {
      container.append(line.slice(cursor, startIndex))
    }

    const span = document.createElement('span')
    span.classList.add('keywordSpan')
    span.append(line.slice(startIndex, startIndex + props.keyword.length))
    container.append(span)
    cursor = startIndex + props.keyword.length
  }

  if (cursor < line.length) {
    container.append(line.slice(cursor))
  }
}

function regenerateWrapper(text) {
  loweredKeyword.value = props.keyword ? props.keyword.toLowerCase() : ''
  while (textWrapper.value?.lastChild) {
    textWrapper.value.removeChild(textWrapper.value.lastChild)
  }

  const normalized = normalizeDisplayText(text)
  if (!normalized) {
    const paragraph = document.createElement('p')
    paragraph.textContent = ''
    textWrapper.value.append(paragraph)
    return
  }

  const root = new textStyleParser.MyDomElement('root', '')
  root.children = textStyleParser.parse(normalized)

  const paragraph = document.createElement('p')
  const lines = [paragraph]
  const containerStack = [paragraph]
  const labelStack = []
  iterateNode(root, lines, containerStack, labelStack)
  for (const line of lines) {
    textWrapper.value.append(line)
  }
}

function stripQuotes(value) {
  if (value.startsWith('"') && value.endsWith('"')) {
    return value.slice(1, -1)
  }
  return value
}

watch(
  () => [props.text, props.keyword],
  () => {
    regenerateWrapper(props.text)
  }
)

onMounted(() => {
  regenerateWrapper(props.text)
})
</script>

<template>
  <div ref="textWrapper" class="textWrapper"></div>
</template>

<style scoped>
.textWrapper {
  word-break: break-word;
}

.textWrapper :deep(p) {
  margin: 0;
  line-height: 1.8;
}

.textWrapper :deep(.keywordSpan) {
  padding: 0 0.18em;
  border-radius: 0.35em;
  background: rgba(212, 180, 109, 0.28);
  color: #ffe6a7;
}
</style>
