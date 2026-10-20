export interface CitationInfo {
  citation_id: string
  span_id: string
  source_id: string
  document_version: string
  title: string
  locator: Record<string, unknown>
  quote: string
  /** Authenticated knowledge-detail API; never a server filesystem path. */
  url: string
}

export interface ChatAnswerInfo {
  citations?: CitationInfo[] | null
  knowledge_release_id?: string | null
  answer_status?: 'answered' | 'partial' | 'clarification' | 'unavailable' | null
  data_as_of?: string | null
  assumptions?: string[] | null
  limitations?: string[] | null
}

export interface ChatMessage extends ChatAnswerInfo {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: number
  documents?: DocumentInfo[]
  images?: string[]
  status?: 'sending' | 'sent' | 'failed'
  sessionId?: string
}

export interface ChatRequest {
  session_id: string
  message: string
  history?: { role: string; content: string }[]
  context?: Record<string, unknown>
}

export interface DocumentInfo {
  file_name: string
  file_path: string
  doc_type: string
  file_size: number
}

/** 后端文档序列化形态（REST 别名 / WS 别名混合，均为可选字段） */
export interface ApiDocumentInfo {
  file_name?: string
  filename?: string
  file_path?: string
  path?: string
  doc_type?: string
  type?: string
  file_size?: number
  size?: number
}

export interface ChatResponse extends ChatAnswerInfo {
  session_id: string
  message_id?: string
  user_message_id?: string
  status: string
  reply: string
  intent: string
  documents: ApiDocumentInfo[]
  images: string[]
  suggested_actions: string[]
  metadata: Record<string, unknown>
  response_time_ms: number | null
}

export interface WebSocketMessagePayload extends ChatAnswerInfo {
  id: string
  session_id: string
  role: string
  content: string
  timestamp: string
  documents?: ApiDocumentInfo[]
  images?: string[]
  intent?: string
}

export interface WebSocketEvent {
  type: string
  event_id?: string
  session_id?: string
  timestamp?: string
  message?: WebSocketMessagePayload
  [key: string]: unknown
}

export interface Session {
  id: string
  session_id?: string
  customer_name?: string
  status: 'new' | 'active' | 'negotiating' | 'closed' | 'lost'
  handover_mode: 'ai' | 'human'
  title: string
  last_message?: string
  updated_at: string
  created_at?: string
}

export interface HighIntentAlert {
  type: 'high_intent_alert'
  session_id: string
  customer_name: string
  trigger_message: string
  intent: string
  timestamp: string
}

export interface CarCardData {
  name: string
  brand: string
  price: string
  images: string[]
  highlights: string[]
  specs: { engine: string; power: string; fuel: string }
}

export interface HistorySession {
  session_id: string
  preview: string
  updated_at: string | null
  message_count: number
}

export interface LeadFormData {
  session_id: string
  name: string
  phone: string
  car_model?: string
  budget_range?: string
  purchase_time?: string
  notes?: string
}

export interface FeedbackFormData {
  session_id: string
  rating: number
  speed: number
  professionalism: number
  comment?: string
  would_recommend: boolean
}
