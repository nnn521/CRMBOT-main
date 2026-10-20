import { apiFetch } from '@/lib/api'
import type { CitationInfo } from '@/types'

export interface KnowledgeStatus {
  enabled: boolean
  ready: boolean
  release_id: string | null
  embedding_compatible: boolean
  scope: 'shared_authenticated'
}

export interface KnowledgeSource {
  source_id: string
  doc_id: string
  source_uri: string
  created_at: string
  revoked: boolean
}

export const vehicleModels = ['CAMRY', 'HIGHLANDER', 'RAV4'] as const
export type VehicleModel = typeof vehicleModels[number]
export const powertrains = ['2.0', '2.5', '燃油', '双擎', '插混', '2.0 燃油', '2.0 双擎', '2.0 插混', '2.5 燃油', '2.5 双擎', '2.5 插混'] as const
export type Powertrain = typeof powertrains[number]

export interface KnowledgeVehicleScope {
  vehicle_model: VehicleModel
  model_year?: number
  powertrain?: Powertrain
}

export interface KnowledgeUpload {
  source_id: string
  version_id: string
  span_count: number
}

export interface KnowledgeBuild {
  job_id: string
  status: 'queued' | 'running' | 'succeeded' | 'failed'
  attempts: number
  error: string | null
  release_id: string | null
  release_status: string | null
}

export interface KnowledgeSearch {
  release_id: string
  hits: { score: number; citation: CitationInfo }[]
  mode: 'source_quotes_only'
  degraded: string[]
}

export function getKnowledgeStatus(): Promise<KnowledgeStatus> {
  return apiFetch('/knowledge/status')
}

export function listKnowledgeSources(): Promise<{ sources: KnowledgeSource[] }> {
  return apiFetch('/knowledge/sources')
}

export function createKnowledgeSource(docId: string, sourceUri: string): Promise<{ source_id: string; doc_id: string }> {
  return apiFetch('/knowledge/sources', {
    method: 'POST', body: JSON.stringify({ doc_id: docId, source_uri: sourceUri }),
  })
}

/** Send original bytes as the raw UTF-8 body required by the upload API. */
export async function uploadKnowledgeVersion(sourceId: string, file: File, title: string, scope: KnowledgeVehicleScope): Promise<KnowledgeUpload> {
  if (!scope || !vehicleModels.includes(scope.vehicle_model)) throw new Error('请选择来源明确适用的车型')
  if (scope.model_year !== undefined && (!Number.isInteger(scope.model_year) || scope.model_year < 2000 || scope.model_year > 2099)) {
    throw new Error('年款须为 2000–2099 年；未知时请留空')
  }
  if (scope.powertrain !== undefined && !powertrains.includes(scope.powertrain)) throw new Error('请选择有效的动力标注')
  const extension = file.name.split('.').pop()?.toLowerCase()
  if (extension !== 'txt' && extension !== 'md') throw new Error('请选择 UTF-8 编码的 .txt 或 .md 文件')
  if (file.size === 0) throw new Error('文件内容不能为空')
  const bytes = await file.arrayBuffer()
  let text: string
  try {
    text = new TextDecoder('utf-8', { fatal: true }).decode(bytes)
  } catch {
    throw new Error('文件不是有效的 UTF-8 文本，请转换编码后重试')
  }
  if (!text.trim() || /[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(text)) {
    throw new Error('文件须包含有效文本，且不能含二进制控制字符')
  }
  const params = new URLSearchParams({ title, vehicle_model: scope.vehicle_model })
  if (scope.model_year !== undefined) params.set('model_year', String(scope.model_year))
  if (scope.powertrain !== undefined) params.set('powertrain', scope.powertrain)
  return apiFetch(`/knowledge/sources/${encodeURIComponent(sourceId)}/versions?${params}`, {
    method: 'POST', body: bytes,
    headers: { 'Content-Type': `${extension === 'md' ? 'text/markdown' : 'text/plain'}; charset=utf-8` },
  })
}

export function enqueueKnowledgeBuild(versionIds: string[], idempotencyKey: string): Promise<KnowledgeBuild> {
  return apiFetch('/knowledge/builds', {
    method: 'POST', body: JSON.stringify({ version_ids: versionIds, idempotency_key: idempotencyKey }),
  })
}

export function getKnowledgeBuild(jobId: string): Promise<KnowledgeBuild> {
  return apiFetch(`/knowledge/builds/${encodeURIComponent(jobId)}`)
}

export function publishKnowledgeRelease(releaseId: string): Promise<{ release_id: string; status: 'published' }> {
  return apiFetch(`/knowledge/releases/${encodeURIComponent(releaseId)}/publish`, { method: 'POST' })
}

export function revokeKnowledgeSource(sourceId: string, reason: string): Promise<{ source_id: string; revoked: boolean }> {
  return apiFetch(`/knowledge/sources/${encodeURIComponent(sourceId)}/revoke`, {
    method: 'POST', body: JSON.stringify({ reason }),
  })
}

export function searchKnowledge(query: string): Promise<KnowledgeSearch> {
  return apiFetch(`/knowledge/search?${new URLSearchParams({ q: query, top_k: '5' })}`)
}
