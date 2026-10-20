import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { BookOpen, RefreshCw, Search, Upload } from 'lucide-react'
import {
  createKnowledgeSource,
  enqueueKnowledgeBuild,
  getKnowledgeBuild,
  getKnowledgeStatus,
  listKnowledgeSources,
  publishKnowledgeRelease,
  revokeKnowledgeSource,
  searchKnowledge,
  uploadKnowledgeVersion,
  vehicleModels,
  powertrains,
  type VehicleModel,
  type Powertrain,
  type KnowledgeVehicleScope,
  type KnowledgeBuild,
  type KnowledgeSearch,
  type KnowledgeSource,
  type KnowledgeStatus,
  type KnowledgeUpload,
} from '@/api/knowledge'

const inputClass = 'w-full rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm outline-none focus:border-amber-400 disabled:bg-neutral-50 disabled:text-neutral-400'
const buttonClass = 'inline-flex items-center justify-center gap-1.5 rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-neutral-700 hover:bg-neutral-50 disabled:cursor-not-allowed disabled:opacity-40'
const primaryClass = 'inline-flex items-center justify-center gap-1.5 rounded-lg bg-neutral-900 px-3 py-2 text-sm text-white hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-40'
const cardClass = 'rounded-xl border border-neutral-200 bg-white p-4 sm:p-5'
const jobLabels: Record<KnowledgeBuild['status'], string> = { queued: '排队中', running: '构建中', succeeded: '构建成功', failed: '构建失败' }
const identifierPattern = /^[A-Za-z0-9_.:-]{1,200}$/
const digestPattern = /^[0-9a-f]{64}$/
const vehicleLabels: Record<VehicleModel, string> = { CAMRY: '凯美瑞', HIGHLANDER: '汉兰达', RAV4: 'RAV4 荣放' }

function isAdminUser(): boolean {
  try {
    return (JSON.parse(localStorage.getItem('crmbot_user') || 'null') as { role?: string } | null)?.role === 'admin'
  } catch {
    return false
  }
}

interface UploadedVersion extends KnowledgeUpload {
  title: string
  scopeLabel: string
}

export function KnowledgePage() {
  const [isAdmin, setIsAdmin] = useState(isAdminUser)
  const [status, setStatus] = useState<KnowledgeStatus | null>(null)
  const [sources, setSources] = useState<KnowledgeSource[]>([])
  const [refreshing, setRefreshing] = useState(false)
  const [pending, setPending] = useState<string | null>(null)
  const pendingRef = useRef(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [docId, setDocId] = useState('')
  const [sourceUri, setSourceUri] = useState('')
  const [sourceId, setSourceId] = useState('')
  const [title, setTitle] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [vehicleModel, setVehicleModel] = useState<VehicleModel | ''>('')
  const [modelYear, setModelYear] = useState('')
  const [powertrain, setPowertrain] = useState<Powertrain | ''>('')
  const fileRef = useRef<HTMLInputElement>(null)
  const [versions, setVersions] = useState<UploadedVersion[]>([])
  const [selectedVersions, setSelectedVersions] = useState<string[]>([])
  const [manualVersions, setManualVersions] = useState('')
  const [buildKey, setBuildKey] = useState<string>(() => crypto.randomUUID())
  const [jobId, setJobId] = useState('')
  const [job, setJob] = useState<KnowledgeBuild | null>(null)
  const [revokeId, setRevokeId] = useState('')
  const [revokeReason, setRevokeReason] = useState('')
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<KnowledgeSearch | null>(null)
  const busy = pending !== null
  const enabled = status?.enabled === true

  const refresh = useCallback(async () => {
    setRefreshing(true)
    try {
      const info = await getKnowledgeStatus()
      setStatus(info)
      if (isAdmin && info.enabled) setSources((await listKnowledgeSources()).sources)
      else setSources([])
    } catch (err) {
      setStatus(null)
      setSources([])
      setError(err instanceof Error ? err.message : '读取知识状态失败')
    } finally {
      setRefreshing(false)
    }
  }, [isAdmin])

  useEffect(() => { void refresh() }, [refresh])
  useEffect(() => {
    const updateRole = () => setIsAdmin(isAdminUser())
    window.addEventListener('storage', updateRole)
    window.addEventListener('auth-expired', updateRole)
    return () => {
      window.removeEventListener('storage', updateRole)
      window.removeEventListener('auth-expired', updateRole)
    }
  }, [])

  async function runAction(name: string, action: () => Promise<void>) {
    if (pendingRef.current) return
    pendingRef.current = true
    setPending(name)
    setError('')
    setNotice('')
    try {
      await action()
    } catch (err) {
      setError(err instanceof Error ? err.message : '操作失败，请重试')
    } finally {
      pendingRef.current = false
      setPending(null)
    }
  }

  async function handleCreate(event: FormEvent) {
    event.preventDefault()
    if (!isAdmin || !enabled) return
    await runAction('create', async () => {
      if (!identifierPattern.test(docId.trim())) throw new Error('文档标识须为 1–200 位字母、数字或 _ . : -')
      const result = await createKnowledgeSource(docId.trim(), sourceUri.trim())
      setSourceId(result.source_id)
      setDocId('')
      setSourceUri('')
      setNotice(`来源已创建：${result.doc_id}。请上传文档版本。`)
      await refresh()
    })
  }

  async function handleUpload(event: FormEvent) {
    event.preventDefault()
    if (!isAdmin || !enabled || !file || !sourceId || !vehicleModel) return
    await runAction('upload', async () => {
      const uploadTitle = title.trim() || file.name
      if (uploadTitle.length > 200) throw new Error('版本标题不得超过 200 字符，请填写较短标题')
      const year = modelYear.trim()
      if (year && (!/^\d{4}$/.test(year) || Number(year) < 2000 || Number(year) > 2099)) {
        throw new Error('年款须为 2000–2099 的四位数字；未知时请选择“未知年款”')
      }
      const scope: KnowledgeVehicleScope = {
        vehicle_model: vehicleModel,
        model_year: year ? Number(year) : undefined,
        powertrain: powertrain || undefined,
      }
      const version = await uploadKnowledgeVersion(sourceId, file, uploadTitle, scope)
      const scopeLabel = `${vehicleLabels[scope.vehicle_model]} · ${scope.model_year ?? '未知年款'} · ${scope.powertrain ?? '未标注动力'}`
      setVersions((current) => [...current.filter((item) => item.version_id !== version.version_id), { ...version, title: uploadTitle, scopeLabel }])
      setSelectedVersions((current) => [...new Set([...current.filter((id) => !versions.some((item) => item.source_id === version.source_id && item.version_id === id)), version.version_id])])
      setFile(null)
      setTitle('')
      setVehicleModel('')
      setModelYear('')
      setPowertrain('')
      if (fileRef.current) fileRef.current.value = ''
      setNotice(`上传成功，标注为 ${scopeLabel}，解析为 ${version.span_count} 个原文片段。选择版本后提交构建，上传不会自动发布。`)
    })
  }

  async function handleBuild(event: FormEvent) {
    event.preventDefault()
    if (!isAdmin || !enabled) return
    await runAction('build', async () => {
      const manual = manualVersions.split(/[\s,，]+/).filter(Boolean)
      const versionIds = [...new Set([...selectedVersions, ...manual])]
      if (!versionIds.length || versionIds.length > 100 || !versionIds.every((id) => digestPattern.test(id))) {
        throw new Error('请选择或填写 1–100 个有效的版本 ID（64 位小写 SHA-256）')
      }
      const known = versions.filter((item) => versionIds.includes(item.version_id))
      if (new Set(known.map((item) => item.source_id)).size !== known.length) throw new Error('每个来源只能选择一个版本')
      if (!identifierPattern.test(buildKey.trim())) throw new Error('幂等键须为 1–200 位字母、数字或 _ . : -')
      const result = await enqueueKnowledgeBuild(versionIds, buildKey.trim())
      setJob(result)
      setJobId(result.job_id)
      setNotice('构建任务已提交。请手动刷新任务状态；构建成功且发布版本 ready 后才能发布。')
    })
  }

  async function handleJobRefresh(event?: FormEvent) {
    event?.preventDefault()
    if (!isAdmin || !enabled || !jobId.trim()) return
    await runAction('job', async () => { setJob(await getKnowledgeBuild(jobId.trim())) })
  }

  async function handlePublish() {
    if (!isAdmin || !enabled || job?.status !== 'succeeded' || job.release_status !== 'ready' || !job.release_id) return
    const releaseId = job.release_id
    if (!window.confirm(`确认发布知识版本 ${releaseId}？将切换当前生效知识，仅包含该构建所选版本。`)) return
    await runAction('publish', async () => {
      await publishKnowledgeRelease(releaseId)
      setJob((current) => current?.release_id === releaseId ? { ...current, release_status: 'published' } : current)
      setResults(null)
      setNotice('知识版本已发布。')
      await refresh()
    })
  }

  async function handleRevoke(event: FormEvent) {
    event.preventDefault()
    if (!isAdmin || !enabled || !revokeId || !revokeReason.trim()) return
    const source = sources.find((item) => item.source_id === revokeId)
    if (!window.confirm(`确认撤回来源「${source?.doc_id || revokeId}」？该来源的检索和引用将不可用，当前页面不支持恢复。`)) return
    await runAction('revoke', async () => {
      await revokeKnowledgeSource(revokeId, revokeReason.trim())
      const revokedIds = versions.filter((item) => item.source_id === revokeId).map((item) => item.version_id)
      setSelectedVersions((current) => current.filter((id) => !revokedIds.includes(id)))
      if (sourceId === revokeId) setSourceId('')
      setRevokeId('')
      setRevokeReason('')
      setResults(null)
      setNotice('来源已撤回，原文引用将由后端实时校验可用性。')
      await refresh()
    })
  }

  async function handleSearch(event: FormEvent) {
    event.preventDefault()
    if (!status?.ready || !query.trim()) return
    await runAction('search', async () => {
      setResults(null)
      setResults(await searchKnowledge(query.trim()))
    })
  }

  return (
    <main className="flex-1 overflow-y-auto bg-neutral-50 p-4 sm:p-6">
      <div className="mx-auto max-w-5xl space-y-5">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div><h1 className="flex items-center gap-2 text-lg font-semibold text-neutral-900"><BookOpen size={20} />知识库管理</h1><p className="mt-1 text-xs text-neutral-500">共享知识来源、版本构建与原文检索</p></div>
          <button type="button" onClick={() => { setError(''); void refresh() }} disabled={refreshing || busy} className={buttonClass}><RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />刷新状态</button>
        </header>
        {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</p>}
        {notice && <p role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</p>}

        <section aria-label="知识库状态" className={cardClass}>
          <h2 className="text-sm font-semibold">服务状态</h2>
          {status ? <div className="mt-3 space-y-2 text-sm text-neutral-600">
            <p><span className={`mr-2 inline-block h-2 w-2 rounded-full ${status.ready ? 'bg-emerald-500' : 'bg-amber-500'}`} />{!status.enabled ? '知识服务未启用' : status.ready ? '已就绪，可检索' : '尚未就绪，请检查已发布版本和向量配置'}</p>
            <p className="break-all">当前发布版本：{status.release_id || '暂无'}</p>
            <p>向量配置：{status.embedding_compatible ? '兼容' : '未确认兼容'}<span className="ml-4 text-xs text-neutral-400">访问范围：已登录用户共享</span></p>
          </div> : <p className="mt-3 text-sm text-neutral-400">{refreshing ? '正在读取状态…' : '未能读取状态，请刷新重试。'}</p>}
        </section>

        {isAdmin && <>
          <section className={cardClass}>
            <h2 className="text-sm font-semibold">1. 创建与上传来源</h2>
            <form onSubmit={handleCreate} className="mt-4 grid gap-3 sm:grid-cols-2">
              <label className="space-y-1 text-xs text-neutral-600">文档标识<input value={docId} onChange={(event) => setDocId(event.target.value)} required maxLength={200} placeholder="例如 camry-specs" className={inputClass} disabled={!enabled || busy} /></label>
              <label className="space-y-1 text-xs text-neutral-600">来源说明 / URI<input value={sourceUri} onChange={(event) => setSourceUri(event.target.value)} required maxLength={1000} placeholder="例如 内部车型手册 2026 版" className={inputClass} disabled={!enabled || busy} /></label>
              <div className="sm:col-span-2"><button type="submit" className={buttonClass} disabled={!enabled || busy || !docId.trim() || !sourceUri.trim()}>{pending === 'create' ? '创建中…' : '创建来源'}</button><span className="ml-3 text-xs text-neutral-400">来源说明仅记录出处，不抓取网址或本地文件。</span></div>
            </form>
            <form onSubmit={handleUpload} className="mt-5 grid gap-3 border-t border-neutral-100 pt-4 sm:grid-cols-2">
              <label className="space-y-1 text-xs text-neutral-600">上传到来源<select value={sourceId} onChange={(event) => setSourceId(event.target.value)} required className={inputClass} disabled={!enabled || busy}><option value="">选择未撤回来源</option>{sources.filter((source) => !source.revoked).map((source) => <option key={source.source_id} value={source.source_id}>{source.doc_id}</option>)}</select></label>
              <label className="space-y-1 text-xs text-neutral-600">版本标题<input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={200} placeholder="留空使用文件名" className={inputClass} disabled={!enabled || busy} /></label>
              <label className="space-y-1 text-xs text-neutral-600">适用车型（必选）<select value={vehicleModel} onChange={(event) => setVehicleModel(event.target.value as VehicleModel | '')} required className={inputClass} disabled={!enabled || busy}><option value="">选择来源明确适用的车型</option>{vehicleModels.map((model) => <option key={model} value={model}>{vehicleLabels[model]}（{model}）</option>)}</select></label>
              <label className="space-y-1 text-xs text-neutral-600">年款（未知可留空）<input value={modelYear} onChange={(event) => setModelYear(event.target.value)} inputMode="numeric" maxLength={4} placeholder="留空表示未知年款" className={inputClass} disabled={!enabled || busy} /></label>
              <label className="space-y-1 text-xs text-neutral-600">动力标注（可选）<select value={powertrain} onChange={(event) => setPowertrain(event.target.value as Powertrain | '')} className={inputClass} disabled={!enabled || busy}><option value="">未标注动力</option>{powertrains.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
              <label className="space-y-1 text-xs text-neutral-600 sm:col-span-2">UTF-8 文本文件<input ref={fileRef} type="file" accept=".txt,.md" onChange={(event) => setFile(event.target.files?.[0] || null)} required className={`${inputClass} file:mr-3 file:rounded file:border-0 file:bg-neutral-100 file:px-2 file:py-1 file:text-xs`} disabled={!enabled || busy} /></label>
              <p className="text-xs leading-5 text-neutral-400 sm:col-span-2">车型与动力是原文标注，不代表官方配置组合一定存在；未选车型的来源无法用于具体车型答案。年款留空按“未知年款”记录。</p>
              <div className="sm:col-span-2"><button type="submit" className={primaryClass} disabled={!enabled || busy || !sourceId || !file || !vehicleModel}><Upload size={14} />{pending === 'upload' ? '上传中…' : '上传新版本'}</button></div>
            </form>
          </section>

          <section className={cardClass}>
            <h2 className="text-sm font-semibold">2. 选择版本并构建</h2>
            <p className="mt-1 text-xs text-neutral-500">所选版本组成完整的新发布内容，不会自动追加当前知识。请选择全部需要保留的来源版本，每个来源仅选一个版本；构建不会自动发布。</p>
            {versions.length > 0 && <div className="mt-3 space-y-2">{versions.map((version) => <label key={version.version_id} className="flex items-start gap-2 rounded-lg border border-neutral-100 p-3 text-xs"><input type="checkbox" className="mt-0.5 accent-amber-600" checked={selectedVersions.includes(version.version_id)} disabled={!enabled || busy || sources.some((source) => source.source_id === version.source_id && source.revoked)} onChange={(event) => setSelectedVersions((current) => event.target.checked ? [...current.filter((id) => !versions.some((item) => item.source_id === version.source_id && item.version_id === id)), version.version_id] : current.filter((id) => id !== version.version_id))} /><span className="min-w-0"><span className="font-medium">{version.title} · {version.scopeLabel} · {version.span_count} 个片段</span><span className="mt-1 block break-all font-mono text-neutral-400">{version.version_id}</span></span></label>)}</div>}
            <form onSubmit={handleBuild} className="mt-3 space-y-3">
              <label className="block space-y-1 text-xs text-neutral-600">已有版本 ID（可选，用空格或逗号分隔）<textarea value={manualVersions} onChange={(event) => setManualVersions(event.target.value)} rows={2} className={`${inputClass} font-mono text-xs`} disabled={!enabled || busy} /></label>
              <div className="flex flex-wrap items-end gap-2"><label className="min-w-0 flex-1 space-y-1 text-xs text-neutral-600">构建幂等键<input value={buildKey} onChange={(event) => setBuildKey(event.target.value)} required maxLength={200} className={`${inputClass} font-mono text-xs`} disabled={!enabled || busy} /></label><button type="button" onClick={() => setBuildKey(crypto.randomUUID())} className={buttonClass} disabled={!enabled || busy}>新建键</button><button type="submit" className={primaryClass} disabled={!enabled || busy || (!selectedVersions.length && !manualVersions.trim())}>{pending === 'build' ? '提交中…' : '提交构建'}</button></div>
              <p className="text-xs text-neutral-400">同一请求重试请保留幂等键；版本选择改变时请生成新键。</p>
            </form>
          </section>

          <section className={cardClass}>
            <h2 className="text-sm font-semibold">3. 查询构建与显式发布</h2>
            <form onSubmit={handleJobRefresh} className="mt-3 flex flex-wrap gap-2"><label className="min-w-0 flex-1"><span className="sr-only">构建任务 ID</span><input value={jobId} onChange={(event) => { setJobId(event.target.value); setJob(null) }} placeholder="构建任务 UUID，可恢复查询已知任务" className={`${inputClass} font-mono text-xs`} disabled={!enabled || busy} /></label><button type="submit" className={buttonClass} disabled={!enabled || busy || !jobId.trim()}><RefreshCw size={14} />{pending === 'job' ? '查询中…' : '刷新任务'}</button></form>
            {job && <div className="mt-4 space-y-2 rounded-lg bg-neutral-50 p-3 text-sm text-neutral-600"><p>{jobLabels[job.status]} · 已尝试 {job.attempts} 次</p><p className="break-all text-xs">任务：{job.job_id}</p>{job.release_id && <p className="break-all text-xs">发布版本：{job.release_id} · {job.release_status || '尚未就绪'}</p>}{job.error && <p className="text-xs text-red-700">任务错误：{job.error}</p>}<button type="button" onClick={() => void handlePublish()} className={primaryClass} disabled={!enabled || busy || job.status !== 'succeeded' || job.release_status !== 'ready' || !job.release_id}>{pending === 'publish' ? '发布中…' : job.release_status === 'published' ? '已发布' : '发布此知识版本'}</button><p className="text-xs text-neutral-400">仅构建成功且版本状态为 ready 时可发布。任务状态需手动刷新。</p></div>}
          </section>

          <section className={cardClass}>
            <h2 className="text-sm font-semibold">来源与撤回</h2>
            {!sources.length ? <p className="mt-3 text-sm text-neutral-400">{enabled ? '暂无来源，请先创建。' : '启用知识服务后可管理来源。'}</p> : <ul className="mt-3 divide-y divide-neutral-100">{sources.map((source) => <li key={source.source_id} className="py-3 text-xs"><div className="flex gap-2"><span className="font-medium text-neutral-800">{source.doc_id}</span><span className={source.revoked ? 'text-red-600' : 'text-emerald-700'}>{source.revoked ? '已撤回' : '可用'}</span></div><p className="mt-1 break-all text-neutral-500">{source.source_uri}</p><p className="mt-1 break-all font-mono text-neutral-400">{source.source_id}</p></li>)}</ul>}
            <form onSubmit={handleRevoke} className="mt-4 space-y-3 border-t border-neutral-100 pt-4"><label className="block space-y-1 text-xs text-neutral-600">撤回来源<select value={revokeId} onChange={(event) => setRevokeId(event.target.value)} className={inputClass} required disabled={!enabled || busy}><option value="">选择未撤回来源</option>{sources.filter((source) => !source.revoked).map((source) => <option key={source.source_id} value={source.source_id}>{source.doc_id}</option>)}</select></label><label className="block space-y-1 text-xs text-neutral-600">撤回原因<textarea value={revokeReason} onChange={(event) => setRevokeReason(event.target.value)} maxLength={500} rows={2} required className={inputClass} disabled={!enabled || busy} /></label><button type="submit" className={`${buttonClass} border-red-200 text-red-700 hover:bg-red-50`} disabled={!enabled || busy || !revokeId || !revokeReason.trim()}>{pending === 'revoke' ? '撤回中…' : '确认撤回来源…'}</button></form>
          </section>
        </>}

        <section className={cardClass}>
          <h2 className="text-sm font-semibold">原文检索</h2>
          <p className="mt-1 text-xs text-neutral-500">只返回当前发布版本的原文引用，不生成总结。</p>
          <form onSubmit={handleSearch} className="mt-3 flex gap-2"><label className="min-w-0 flex-1"><span className="sr-only">检索问题</span><input value={query} onChange={(event) => setQuery(event.target.value)} maxLength={2000} required placeholder={status?.ready ? '输入要查找的车型、配置或政策' : '知识服务就绪后可检索'} className={inputClass} disabled={!status?.ready || busy} /></label><button type="submit" className={primaryClass} disabled={!status?.ready || busy || !query.trim()}><Search size={14} />{pending === 'search' ? '检索中…' : '检索'}</button></form>
          {results && <div className="mt-4 space-y-3"><p className="break-all text-xs text-neutral-400">发布版本：{results.release_id} · {results.hits.length} 条原文{results.degraded.length > 0 && ` · 检索降级：${results.degraded.join('、')}`}</p>{!results.hits.length && <p className="text-sm text-neutral-500">未找到匹配原文，请调整关键词。</p>}{results.hits.map(({ citation, score }) => <details key={citation.citation_id} className="rounded-lg border border-neutral-200 p-3" open><summary className="cursor-pointer text-sm font-medium text-neutral-800">{citation.title || citation.source_id}<span className="ml-2 text-xs font-normal text-neutral-400">相关度 {score.toFixed(3)}</span></summary><blockquote className="mt-2 whitespace-pre-wrap break-words border-l-2 border-amber-300 pl-3 text-sm leading-6 text-neutral-600">{citation.quote}</blockquote><p className="mt-2 break-all text-xs text-neutral-400">文档版本：{citation.document_version}</p><pre className="mt-1 whitespace-pre-wrap break-all text-xs text-neutral-400">{JSON.stringify(citation.locator, null, 2)}</pre></details>)}</div>}
        </section>
        <p className="pb-2 text-xs leading-5 text-neutral-400">{isAdmin ? '当前接口支持来源与发布管理；暂不提供版本历史列表、任务列表、在线编辑、审核或 Wiki 同步。刷新页面后，本次上传的版本选择需通过已知版本 ID 恢复。' : '当前账号可查看知识状态并检索已发布原文。来源上传、构建、发布和撤回仅向管理员提供。'}</p>
      </div>
    </main>
  )
}

export default KnowledgePage
