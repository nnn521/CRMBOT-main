import { useState, useEffect, useCallback } from 'react'
import { TrendingUp, Loader2, Sparkles } from 'lucide-react'
import { fetchDashboard, fetchDeals, analyzeReport, type DashboardData, type DealRecord } from '@/api/reports'

/* ── 区块4: 车型销量（暂无DB来源，保留假数据） ── */
const carSales = [
  { name: '凯美瑞', count: 58 },
  { name: '卡罗拉', count: 42 },
  { name: 'RAV4', count: 35 },
  { name: '汉兰达', count: 28 },
  { name: '亚洲龙', count: 18 },
  { name: '其他', count: 12 },
]
const maxSales = Math.max(...carSales.map((c) => c.count))
const barColors = ['#1a56db', '#2563eb', '#3b82f6', '#60a5fa', '#93c5fd', '#bfdbfe']

/* ── 区块5: 客户来源（暂无DB来源，保留假数据） ── */
const channels = [
  { label: '线上广告', pct: 42, color: '#2563eb' },
  { label: '门店自然进店', pct: 28, color: '#0d9488' },
  { label: '老客户转介绍', pct: 18, color: '#f59e0b' },
  { label: '其他', pct: 12, color: '#8b5cf6' },
]
// SVG donut geometry
const donutR = 70
const donutStroke = 28
const donutCirc = 2 * Math.PI * donutR
let cumulativeOffset = 0
const donutSegments = channels.map((ch) => {
  const dash = (ch.pct / 100) * donutCirc
  const offset = cumulativeOffset
  cumulativeOffset += dash
  return { ...ch, dash, offset }
})

/* ── 默认空数据 ── */
const defaultDashboard: DashboardData = {
  summary: { total_sessions: 0, conversion_rate: 0, active_customers: 0, new_leads_this_month: 0 },
  monthly_trend: [],
  funnel: { total_leads: 0, contacted: 0, interested: 0, negotiating: 0, closed: 0 },
  status_breakdown: { new: 0, active: 0, negotiating: 0, closed: 0, lost: 0 },
}

export default function ReportsPage() {
  const [dashboard, setDashboard] = useState<DashboardData>(defaultDashboard)
  const [deals, setDeals] = useState<DealRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // AI 分析状态
  const [analysisText, setAnalysisText] = useState<string | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [analyzeError, setAnalyzeError] = useState<string | null>(null)

  // 加载数据
  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        setLoading(true)
        setError(null)
        const [dashData, dealsData] = await Promise.all([
          fetchDashboard(),
          fetchDeals(10),
        ])
        if (!cancelled) {
          setDashboard(dashData)
          setDeals(dealsData)
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : '加载数据失败')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  // AI 解读
  const handleAnalyze = useCallback(async () => {
    try {
      setAnalyzing(true)
      setAnalyzeError(null)
      setAnalysisText(null)
      const text = await analyzeReport(JSON.stringify(dashboard))
      setAnalysisText(text)
    } catch (e) {
      setAnalyzeError(e instanceof Error ? e.message : 'AI 分析失败')
    } finally {
      setAnalyzing(false)
    }
  }, [dashboard])

  // ── 从 API 数据派生图表数据 ──

  // 概览卡片
  const { summary, funnel: funnelData, monthly_trend } = dashboard
  const summaryCards = [
    { label: '总会话数', value: String(summary.total_sessions), sub: null, icon: '💬' },
    { label: '成交转化率', value: `${summary.conversion_rate}%`, sub: null, icon: '📈' },
    { label: '活跃客户数', value: String(summary.active_customers), sub: null, icon: '👥' },
    { label: '本月新增线索', value: String(summary.new_leads_this_month), sub: null, icon: '📋' },
  ]

  // 漏斗
  const funnelArr = [
    { label: '线索总数', value: funnelData.total_leads, color: '#1e40af' },
    { label: '已联系', value: funnelData.contacted, color: '#2563eb' },
    { label: '意向客户', value: funnelData.interested, color: '#3b82f6' },
    { label: '报价中', value: funnelData.negotiating, color: '#60a5fa' },
    { label: '已成交', value: funnelData.closed, color: '#93c5fd' },
  ]
  const funnelMax = funnelArr[0].value || 1

  // 月度趋势
  const months = monthly_trend.map((t) => {
    const parts = t.month.split('-')
    return `${parseInt(parts[1])}月`
  })
  const salesTrend = monthly_trend.map((t) => t.count)
  const trendMax = salesTrend.length > 0 ? Math.max(...salesTrend) * 1.2 : 10
  const svgW = 560
  const svgH = 220
  const padL = 40
  const padR = 20
  const padT = 20
  const padB = 36
  const plotW = svgW - padL - padR
  const plotH = svgH - padT - padB
  const trendPoints = salesTrend.map((v, i) => {
    const x = padL + (i / Math.max(salesTrend.length - 1, 1)) * plotW
    const y = padT + plotH - (v / trendMax) * plotH
    return { x, y, v }
  })
  const polylineStr = trendPoints.map((p) => `${p.x},${p.y}`).join(' ')

  // 近期成交
  const recentDeals = deals.map((d) => ({
    name: d.customer_name,
    model: d.title,
    amount: '',
    date: d.updated_at ? d.updated_at.slice(0, 10) : '',
    status: d.status,
  }))

  // ── 加载中骨架屏 ──
  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center bg-neutral-50">
        <div className="flex flex-col items-center gap-3">
          <Loader2 size={32} className="animate-spin text-neutral-400" />
          <span className="text-sm text-neutral-500">加载报表数据...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto bg-neutral-50 p-6">
      <div className="mx-auto max-w-[1080px] space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-semibold text-neutral-800">销售数据驾驶舱</h1>
          <span className="text-xs text-neutral-400">数据实时更新</span>
        </div>

        {/* 错误提示 */}
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
            ⚠️ {error}（显示默认数据）
          </div>
        )}

        {/* ━━ 区块1: 概览卡片 ━━ */}
        <div className="grid grid-cols-4 gap-3">
          {summaryCards.map((card) => (
            <div key={card.label} className="rounded-lg border border-neutral-200 bg-white p-4">
              <div className="mb-2 flex items-center gap-2">
                <span className="text-base">{card.icon}</span>
                <span className="text-xs text-neutral-500">{card.label}</span>
              </div>
              <div className="text-xl font-bold text-neutral-900">{card.value}</div>
              {card.sub && (
                <div className="mt-1 flex items-center gap-1 text-xs text-emerald-600">
                  <TrendingUp size={12} />
                  {card.sub}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* ━━ 区块2: 销售转化漏斗 ━━ */}
        <div className="rounded-lg border border-neutral-200 bg-white p-5">
          <h2 className="mb-5 text-sm font-medium text-neutral-700">销售转化漏斗</h2>
          <div className="mx-auto max-w-[640px] space-y-2">
            {funnelArr.map((step, idx) => {
              const widthPct = (step.value / funnelMax) * 100
              const convRate = idx === 0 ? '' : `  (${Math.round((step.value / funnelArr[idx - 1].value) * 100)}%)`
              return (
                <div key={step.label} className="flex items-center gap-3">
                  <span className="w-20 shrink-0 text-right text-xs text-neutral-500">{step.label}</span>
                  <div className="flex-1">
                    <div
                      className="flex h-9 items-center justify-end rounded pr-3 text-xs font-medium text-white transition-all"
                      style={{ width: `${widthPct}%`, backgroundColor: step.color }}
                    >
                      <span className="text-white drop-shadow-sm">{step.value}</span>
                    </div>
                  </div>
                  <span className="w-24 text-xs text-neutral-400">
                    {idx === 0 ? '100%' : `${Math.round((step.value / funnelMax) * 100)}%`}
                    {convRate}
                  </span>
                </div>
              )
            })}
          </div>
        </div>

        {/* ━━ 区块3 & 区块4: 两列布局 ━━ */}
        <div className="grid grid-cols-2 gap-6">
          {/* 区块3: 月度销售趋势 SVG 折线图 */}
          <div className="rounded-lg border border-neutral-200 bg-white p-5">
            <h2 className="mb-4 text-sm font-medium text-neutral-700">月度会话趋势</h2>
            {trendPoints.length > 1 ? (
              <svg viewBox={`0 0 ${svgW} ${svgH}`} className="w-full" style={{ height: 220 }}>
                {/* Grid lines */}
                {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
                  const y = padT + plotH * (1 - ratio)
                  const val = Math.round(trendMax * ratio)
                  return (
                    <g key={ratio}>
                      <line x1={padL} y1={y} x2={svgW - padR} y2={y} stroke="#e5e5e5" strokeWidth={1} />
                      <text x={padL - 8} y={y + 4} textAnchor="end" fontSize={10} fill="#a3a3a3">
                        {val}
                      </text>
                    </g>
                  )
                })}
                {/* X axis labels */}
                {trendPoints.map((p, i) => (
                  <text key={i} x={p.x} y={svgH - 8} textAnchor="middle" fontSize={10} fill="#a3a3a3">
                    {months[i]}
                  </text>
                ))}
                {/* Polyline */}
                <polyline
                  points={polylineStr}
                  fill="none"
                  stroke="#2563eb"
                  strokeWidth={2.5}
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
                {/* Data points */}
                {trendPoints.map((p, i) => (
                  <g key={i}>
                    <circle cx={p.x} cy={p.y} r={4} fill="white" stroke="#2563eb" strokeWidth={2.5} />
                    <text x={p.x} y={p.y - 10} textAnchor="middle" fontSize={10} fontWeight={600} fill="#1e40af">
                      {p.v}
                    </text>
                  </g>
                ))}
              </svg>
            ) : (
              <div className="flex h-[220px] items-center justify-center text-sm text-neutral-400">
                暂无趋势数据
              </div>
            )}
          </div>

          {/* 区块4: 车型销量排行 */}
          <div className="rounded-lg border border-neutral-200 bg-white p-5">
            <h2 className="mb-4 text-sm font-medium text-neutral-700">车型销量排行 <span className="text-[10px] font-normal text-neutral-400">(演示数据)</span></h2>
            <div className="flex items-end gap-3" style={{ height: 200 }}>
              {carSales.map((car, i) => {
                const heightPct = (car.count / maxSales) * 100
                return (
                  <div key={car.name} className="flex flex-col items-center flex-1 h-full justify-end">
                    <span className="mb-1 text-[11px] font-semibold text-neutral-700">{car.count}</span>
                    <div
                      className="w-full rounded-t transition-all"
                      style={{ height: `${heightPct}%`, backgroundColor: barColors[i] }}
                    />
                    <span className="mt-2 text-[11px] text-neutral-500 whitespace-nowrap">{car.name}</span>
                  </div>
                )
              })}
            </div>
          </div>
        </div>

        {/* ━━ 区块5 & 区块6: 两列布局 ━━ */}
        <div className="grid grid-cols-2 gap-6">
          {/* 区块5: 客户来源渠道 — SVG 环形饼图 */}
          <div className="rounded-lg border border-neutral-200 bg-white p-5">
            <h2 className="mb-4 text-sm font-medium text-neutral-700">客户来源渠道 <span className="text-[10px] font-normal text-neutral-400">(演示数据)</span></h2>
            <div className="flex items-center gap-6">
              <svg width={170} height={170} viewBox="0 0 170 170">
                {donutSegments.map((seg) => (
                  <circle
                    key={seg.label}
                    cx={85}
                    cy={85}
                    r={donutR}
                    fill="none"
                    stroke={seg.color}
                    strokeWidth={donutStroke}
                    strokeDasharray={`${seg.dash} ${donutCirc - seg.dash}`}
                    strokeDashoffset={-seg.offset}
                    transform="rotate(-90 85 85)"
                  />
                ))}
                {/* Center label */}
                <text x={85} y={80} textAnchor="middle" fontSize={18} fontWeight={700} fill="#1e40af">
                  {summary.total_sessions}
                </text>
                <text x={85} y={97} textAnchor="middle" fontSize={10} fill="#a3a3a3">
                  总客户数
                </text>
              </svg>
              <div className="space-y-3">
                {channels.map((ch) => (
                  <div key={ch.label} className="flex items-center gap-2">
                    <span className="inline-block h-3 w-3 rounded-sm" style={{ backgroundColor: ch.color }} />
                    <span className="text-xs text-neutral-600">{ch.label}</span>
                    <span className="ml-auto text-xs font-semibold text-neutral-800">{ch.pct}%</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* 区块6: 近期成交记录表 */}
          <div className="rounded-lg border border-neutral-200 bg-white">
            <div className="border-b border-neutral-100 px-5 py-3">
              <h2 className="text-sm font-medium text-neutral-700">近期成交记录</h2>
            </div>
            {recentDeals.length > 0 ? (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-neutral-100 text-left text-xs text-neutral-500">
                    <th className="px-4 py-2 font-medium">客户名</th>
                    <th className="px-4 py-2 font-medium">会话</th>
                    <th className="px-4 py-2 font-medium">日期</th>
                    <th className="px-4 py-2 font-medium">状态</th>
                  </tr>
                </thead>
                <tbody>
                  {recentDeals.map((deal, i) => (
                    <tr key={i} className="border-b border-neutral-50 last:border-0">
                      <td className="px-4 py-2.5 text-neutral-800">{deal.name}</td>
                      <td className="px-4 py-2.5 text-neutral-600">{deal.model}</td>
                      <td className="px-4 py-2.5 text-neutral-500">{deal.date}</td>
                      <td className="px-4 py-2.5">
                        <span className="inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-medium bg-neutral-100 text-neutral-700 border-neutral-200">
                          {deal.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="flex h-32 items-center justify-center text-sm text-neutral-400">
                暂无成交记录
              </div>
            )}
          </div>
        </div>

        {/* ━━ AI 解读区域 ━━ */}
        <div className="rounded-lg border border-neutral-200 bg-white p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-medium text-neutral-700">🤖 AI 数据解读</h2>
            <button
              onClick={handleAnalyze}
              disabled={analyzing || summary.total_sessions === 0}
              className="inline-flex items-center gap-1.5 rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {analyzing ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  分析中...
                </>
              ) : (
                <>
                  <Sparkles size={14} />
                  AI 解读
                </>
              )}
            </button>
          </div>

          {analyzeError && (
            <div className="mb-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-600">
              {analyzeError}
            </div>
          )}

          {analysisText && (
            <div className="rounded-lg bg-neutral-50 p-4 text-sm leading-relaxed text-neutral-700 whitespace-pre-wrap">
              {analysisText}
            </div>
          )}

          {!analysisText && !analyzing && !analyzeError && (
            <div className="text-center text-sm text-neutral-400 py-4">
              点击"AI 解读"按钮，自动生成业务分析和策略建议
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
