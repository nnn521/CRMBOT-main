export interface ChatMessage {
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

export interface ChatResponse {
  session_id: string
  message_id?: string
  user_message_id?: string
  status: 'completed' | 'waiting_human'
  reply: string
  intent: string
  documents: DocumentInfo[]
  images: string[]
  suggested_actions: string[]
  metadata: Record<string, unknown>
  response_time_ms: number
}

export interface WebSocketMessagePayload {
  id: string
  session_id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  documents?: DocumentInfo[]
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
