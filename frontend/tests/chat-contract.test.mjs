// Existing TypeScript compiler + Node's test runner; no browser, network or test framework.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'
import { renderToStaticMarkup } from 'react-dom/server'
import { createElement } from 'react'

function moduleUrl(path, aliases = {}) {
  const source = readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8')
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText.replace(/from (['"])([^'"]+)\1/g, (_match, _quote, name) => `from ${JSON.stringify(aliases[name] ?? import.meta.resolve(name))}`)
  return `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
}

const apiUrl = moduleUrl('lib/api.ts')
const api = await import(apiUrl)
const { apiMessageToChatMessage } = await import(moduleUrl('api/sessions.ts', { '@/lib/api': apiUrl }))
const { useChatStore } = await import(moduleUrl('stores/chat.ts', { '@/lib/api': apiUrl }))
const { ChatBubble } = await import(moduleUrl('components/ChatBubble.tsx'))

const citation = {
  citation_id: 'cite-1', span_id: 'span-1', source_id: 'source-1', document_version: 'v1',
  title: '<script>title()</script>', locator: { start_line: 3, end_line: 4 },
  quote: '<img src=x onerror=alert(1)>', url: '/api/v1/knowledge/releases/r1/citations/span-1',
}
const answer = {
  citations: [citation], knowledge_release_id: 'r1', answer_status: 'partial',
  data_as_of: '2026-10-20', assumptions: ['<script>condition()</script>'], limitations: ['门店确认为准'],
}
const base = { id: '7', role: 'assistant', content: '配置回答', timestamp: 100 }

function resetStore() {
  useChatStore.setState({ messages: [], sessionMessages: {}, seenMessageIds: new Set() })
}

test('all HTTP/WS/history answer fields and legacy metadata survive mapping', () => {
  for (const source of [{ ...base, ...answer }, { ...base, metadata_json: answer }, { ...base, metadata: answer }]) {
    const mapped = apiMessageToChatMessage(source)
    for (const name of Object.keys(answer)) assert.deepEqual(mapped[name], answer[name])
  }
  const mapped = apiMessageToChatMessage({ ...base, timestamp: '2026-10-20T12:00:00Z', documents: [{ filename: 'a.pdf', type: 'pdf' }], images: ['/images/a.png'] })
  assert.equal(mapped.timestamp, Date.parse('2026-10-20T12:00:00Z'))
  assert.equal(mapped.documents[0].file_path, '/api/v1/documents/a.pdf')
  assert.deepEqual(mapped.images, ['/images/a.png'])
})

test('HTTP and WS arriving in either order merge one bubble and retain late fields', () => {
  const sparse = { ...base, citations: undefined, assumptions: [], limitations: undefined }
  const complete = { ...base, ...answer }
  for (const messages of [[sparse, complete], [complete, sparse]]) {
    resetStore()
    for (const message of messages) useChatStore.getState().addMessage(message)
    useChatStore.getState().mergeMessages([sparse, complete])
    useChatStore.getState().setMessages([sparse])
    assert.equal(useChatStore.getState().messages.length, 1)
    for (const name of Object.keys(answer)) assert.deepEqual(useChatStore.getState().messages[0][name], answer[name])
  }
})

test('admin session history and WS merge by ID independently of global seen keys', () => {
  resetStore()
  const store = useChatStore.getState()
  store.addMessage(base)
  store.appendSessionMessage('s1', base)
  store.setSessionMessages('s1', [{ ...base, ...answer }])
  store.appendSessionMessage('s1', base)
  assert.equal(useChatStore.getState().sessionMessages.s1.length, 1)
  assert.deepEqual(useChatStore.getState().sessionMessages.s1[0].citations, answer.citations)
})

test('server user ID reconciles optimistic echo before reconnect history', () => {
  resetStore()
  const store = useChatStore.getState()
  store.addMessage({ ...base, id: 'local-1', role: 'user', status: 'sending' })
  store.addMessage({ ...base, id: 'server-1', role: 'user', status: 'sent' })
  store.updateMessageStatus('local-1', 'sent', 'server-1')
  store.mergeMessages([{ ...base, id: 'server-1', role: 'user' }])
  assert.equal(useChatStore.getState().messages.length, 1)
  assert.equal(useChatStore.getState().messages[0].id, 'server-1')
})

test('apiFetch sets JSON headers except automatic FormData boundary and preserves Headers', async () => {
  const calls = []
  const originalFetch = globalThis.fetch
  globalThis.fetch = async (_url, init) => {
    calls.push(init)
    return { ok: true, status: 200, json: async () => ({}) }
  }
  try {
    await api.apiFetch('/mock')
    await api.apiFetch('/mock', { method: 'POST', body: '{}' })
    await api.apiFetch('/mock', { method: 'POST', body: new FormData() })
    await api.apiFetch('/mock', { headers: new Headers({ 'X-Test': 'kept', 'Content-Type': 'application/custom' }) })
    assert.equal(calls[0].headers.get('Content-Type'), 'application/json')
    assert.equal(calls[1].headers.get('Content-Type'), 'application/json')
    assert.equal(calls[2].headers.has('Content-Type'), false)
    assert.equal(calls[3].headers.get('X-Test'), 'kept')
    assert.equal(calls[3].headers.get('Content-Type'), 'application/custom')
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('citation details render quote, locator and conditions as escaped React text', () => {
  const html = renderToStaticMarkup(createElement(ChatBubble, { message: { ...base, ...answer } }))
  assert.ok(html.includes('&lt;script&gt;title()&lt;/script&gt;'))
  assert.ok(html.includes('&lt;img src=x onerror=alert(1)&gt;'))
  assert.ok(html.includes('&lt;script&gt;condition()&lt;/script&gt;'))
  assert.ok(html.includes('start_line') && html.includes('部分回答') && html.includes('适用条件'))
  assert.ok(html.includes(`href="${citation.url}"`))
  assert.equal(html.includes('<script>'), false)
  for (const url of ['file:///private/source', '/srv/private', 'https://evil.example/source', '/api/v1/knowledge/releases/r/citations/%252e%252e']) {
    const unsafe = renderToStaticMarkup(createElement(ChatBubble, { message: { ...base, citations: [{ ...citation, url }] } }))
    assert.equal(unsafe.includes('查看来源详情'), false)
  }
})
