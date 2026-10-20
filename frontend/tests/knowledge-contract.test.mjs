// Exercise actual typed clients and server-rendered role gating without extra dependencies.
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
const knowledgeUrl = moduleUrl('api/knowledge.ts', { '@/lib/api': apiUrl })
const knowledge = await import(knowledgeUrl)
const { KnowledgePage } = await import(moduleUrl('pages/KnowledgePage.tsx', { '@/api/knowledge': knowledgeUrl }))

async function withFetchMock(action) {
  const originalFetch = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init })
    return { ok: true, status: 200, json: async () => ({}) }
  }
  try { await action(calls) } finally { globalThis.fetch = originalFetch }
}

test('knowledge clients match actual status/source/build/publish/revoke/search routes', async () => {
  await withFetchMock(async (calls) => {
    await knowledge.getKnowledgeStatus()
    await knowledge.listKnowledgeSources()
    await knowledge.createKnowledgeSource('doc-1', '内部资料')
    await knowledge.enqueueKnowledgeBuild(['a'.repeat(64)], 'build-1')
    await knowledge.getKnowledgeBuild('known-job')
    await knowledge.publishKnowledgeRelease('release-1')
    await knowledge.revokeKnowledgeSource('source-1', '资料过期')
    await knowledge.searchKnowledge('配置 & 价格')
    assert.deepEqual(calls.map((call) => call.url.split('?')[0]), [
      '/api/v1/knowledge/status', '/api/v1/knowledge/sources', '/api/v1/knowledge/sources',
      '/api/v1/knowledge/builds', '/api/v1/knowledge/builds/known-job',
      '/api/v1/knowledge/releases/release-1/publish', '/api/v1/knowledge/sources/source-1/revoke',
      '/api/v1/knowledge/search',
    ])
    assert.deepEqual(JSON.parse(calls[2].init.body), { doc_id: 'doc-1', source_uri: '内部资料' })
    assert.deepEqual(JSON.parse(calls[3].init.body), { version_ids: ['a'.repeat(64)], idempotency_key: 'build-1' })
    assert.deepEqual(JSON.parse(calls[6].init.body), { reason: '资料过期' })
    assert.equal(new URL(calls[7].url, 'http://localhost').searchParams.get('q'), '配置 & 价格')
  })
})

test('upload sends scope query, original UTF-8 bytes and explicit raw text content type', async () => {
  await withFetchMock(async (calls) => {
    const text = '# 车型\n配置原文。\n'
    for (const extension of ['md', 'txt']) {
      const file = new File([text], `车型.${extension}`)
      await knowledge.uploadKnowledgeVersion('source-1', file, '车型标题', { vehicle_model: 'CAMRY', model_year: 2024, powertrain: '2.5 双擎' })
      const { url, init } = calls.at(-1)
      const params = new URL(url, 'http://localhost').searchParams
      assert.equal(params.get('title'), '车型标题')
      assert.equal(params.get('vehicle_model'), 'CAMRY')
      assert.equal(params.get('model_year'), '2024')
      assert.equal(params.get('powertrain'), '2.5 双擎')
      assert.equal(init.headers.get('Content-Type'), `text/${extension === 'md' ? 'markdown' : 'plain'}; charset=utf-8`)
      assert.ok(init.body instanceof ArrayBuffer)
      assert.equal(new TextDecoder().decode(init.body), text)
      assert.equal(url.split('?')[0], '/api/v1/knowledge/sources/source-1/versions')
    }
    await knowledge.uploadKnowledgeVersion('source-1', new File([text], 'a.md'), '未知年款', { vehicle_model: 'RAV4' })
    const unknown = new URL(calls.at(-1).url, 'http://localhost').searchParams
    assert.equal(unknown.get('vehicle_model'), 'RAV4')
    assert.equal(unknown.has('model_year'), false)
    assert.equal(unknown.has('powertrain'), false)
  })
})

test('upload rejects unsupported files, invalid UTF-8 and binary text before sending', async () => {
  await withFetchMock(async (calls) => {
    for (const file of [new File(['a'], 'a.pdf'), new File([], 'a.txt'), new File([new Uint8Array([0xff])], 'a.md'), new File(['\0binary'], 'a.txt'), new File(['  \n'], 'a.md')]) {
      await assert.rejects(() => knowledge.uploadKnowledgeVersion('s', file, 'title', { vehicle_model: 'CAMRY' }))
    }
    assert.equal(calls.length, 0)
  })
})

test('upload requires canonical vehicle scope and bounded year/powertrain before sending', async () => {
  await withFetchMock(async (calls) => {
    const file = new File(['text'], 'a.md')
    for (const scope of [undefined, {}, { vehicle_model: 'COROLLA' }, { vehicle_model: 'CAMRY', model_year: 1999 }, { vehicle_model: 'CAMRY', model_year: 2024.5 }, { vehicle_model: 'CAMRY', powertrain: 'V6' }]) {
      await assert.rejects(() => knowledge.uploadKnowledgeVersion('s', file, 'title', scope))
    }
    assert.equal(calls.length, 0)
    assert.deepEqual(knowledge.vehicleModels, ['CAMRY', 'HIGHLANDER', 'RAV4'])
    assert.deepEqual(knowledge.powertrains, ['2.0', '2.5', '燃油', '双擎', '插混', '2.0 燃油', '2.0 双擎', '2.0 插混', '2.5 燃油', '2.5 双擎', '2.5 插混'])
  })
})

test('regular and invalid local users render status/search without usable write controls', () => {
  const originalStorage = globalThis.localStorage
  try {
    for (const stored of [JSON.stringify({ role: 'customer' }), '{invalid', 'null']) {
      globalThis.localStorage = { getItem: () => stored }
      const html = renderToStaticMarkup(createElement(KnowledgePage))
      assert.ok(html.includes('服务状态') && html.includes('原文检索'))
      assert.equal(html.includes('上传新版本'), false)
      assert.equal(html.includes('创建来源</button>'), false)
      assert.equal(html.includes('提交构建</button>'), false)
      assert.equal(html.includes('确认撤回来源…'), false)
    }
    globalThis.localStorage = { getItem: () => JSON.stringify({ role: 'admin' }) }
    const html = renderToStaticMarkup(createElement(KnowledgePage))
    assert.ok(html.includes('上传新版本') && html.includes('创建来源</button>'))
    assert.ok(html.includes('适用车型（必选）') && html.includes('未知年款') && html.includes('未标注动力'))
    assert.ok(html.includes('不代表官方配置组合一定存在'))
    assert.ok(html.includes('提交构建</button>') && html.includes('确认撤回来源…'))
    assert.ok(html.includes('查询构建与显式发布'))
  } finally {
    if (originalStorage === undefined) delete globalThis.localStorage
    else globalThis.localStorage = originalStorage
  }
})
