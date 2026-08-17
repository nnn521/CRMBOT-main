import { useState, useCallback } from 'react'
import { FileSpreadsheet, FileText, File, Download } from 'lucide-react'

interface Props {
  filename: string
  filePath?: string
}

function getFileIcon(filename: string) {
  const ext = filename.split('.').pop()?.toLowerCase()
  switch (ext) {
    case 'xlsx': case 'xls': case 'csv': return FileSpreadsheet
    case 'docx': case 'doc': return FileText
    default: return File
  }
}

function getShortName(filename: string) {
  const name = filename.replace(/\.(xlsx|docx|doc|csv|pdf)$/i, '')
  const ext = filename.split('.').pop()?.toLowerCase()
  const extLabel = ext === 'xlsx' ? 'Excel' : ext === 'docx' ? 'Word' : ext?.toUpperCase() || '文件'
  return { name, extLabel }
}

export default function DownloadButton({ filename, filePath }: Props) {
  const [downloading, setDownloading] = useState(false)
  const FileIcon = getFileIcon(filename)
  const { name, extLabel } = getShortName(filename)

  const handleDownload = useCallback(async () => {
    if (downloading) return
    setDownloading(true)
    try {
      const url = `/api/v1/documents/${encodeURIComponent(filename)}`
      const link = document.createElement('a')
      link.href = url; link.download = filename
      document.body.appendChild(link); link.click(); document.body.removeChild(link)
    } finally {
      setDownloading(false)
    }
  }, [filename, filePath, downloading])

  if (!filename) return null

  return (
    <button
      onClick={handleDownload}
      className="group flex items-center gap-2 rounded-2xl transition-all hover:scale-105 active:scale-95"
      style={{
        background: 'linear-gradient(135deg, #f8fafc, #f1f5f9)',
        border: '1px solid #e2e8f0',
        padding: '10px 16px',
        aspectRatio: '4/3',
        minWidth: '120px',
        maxWidth: '160px',
        boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
      }}
    >
      <div className="flex flex-col items-center gap-1.5 w-full">
        <div className="flex items-center justify-center w-9 h-9 rounded-xl"
          style={{ background: 'linear-gradient(135deg, #dbeafe, #bfdbfe)' }}>
          <FileIcon className="w-4.5 h-4.5 text-blue-600" />
        </div>
        <span className="text-xs font-medium text-slate-700 text-center leading-tight line-clamp-2">
          {name}
        </span>
        <span className="text-[10px] text-slate-400 flex items-center gap-1">
          <Download className="w-3 h-3" />
          {extLabel}
        </span>
      </div>
    </button>
  )
}
