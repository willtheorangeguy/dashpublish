// Types mirroring the FastAPI REST contract under /api.
// Keep in sync with the backend's Pydantic schemas (package E).

export interface VideoOut {
  id: number
  path: string
  camera: string | null
  source_type: string
  event_id: string | null
  duration_s: number | null
  recorded_at: string | null
  indexed_at: string | null
}

export interface ClipOut {
  id: number
  video_id: number
  category_id: number
  category_name: string
  score: number
  start_s: number
  end_s: number
  duration_s: number
  clip_path: string
  starred: boolean
  hidden: boolean
  user_tags: Record<string, unknown>
  created_at: string
}

export interface ClipPatch {
  starred?: boolean
  hidden?: boolean
  user_tags?: Record<string, unknown>
}

export type ClipSort = 'score' | 'newest'

export interface ClipsQuery {
  category?: number
  starred?: boolean
  hidden?: boolean
  video_id?: number
  min_score?: number
  sort?: ClipSort
}

export interface CategoryOut {
  id: number
  name: string
  query_text: string
  threshold: number
  save_top: number
  rerank: boolean
  enabled: boolean
  is_builtin: boolean
}

export type CategoryCreate = Omit<CategoryOut, 'id'>
export type CategoryPatch = Partial<CategoryCreate>

export type JobType = 'index' | 'scan' | 'compile' | 'upload' | string
export type JobStatus = 'queued' | 'running' | 'done' | 'failed'

export interface JobOut {
  id: number
  type: JobType
  status: JobStatus
  progress: number
  message: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  error: string | null
}

export interface ScanOut {
  id: number
  started_at: string
  finished_at: string | null
  status: JobStatus
  clips_found: number
}

export type CompilationProfile = 'short' | 'long'
export type CompilationStatus =
  | 'draft'
  | 'planning'
  | 'rendering'
  | 'rendered'
  | 'uploaded'
  | 'published'
  | 'failed'

// The exact EDL schema is owned by the compile package (C) and produced by
// an LLM; treat it as a loosely-typed bag of segments so the UI stays
// resilient to fields we didn't anticipate.
export interface EdlSegment {
  clip_id: number
  order?: number
  trim_start?: number
  trim_end?: number
  transition?: 'cut' | 'crossfade' | string
  rationale?: string
  [key: string]: unknown
}

export interface Edl {
  segments: EdlSegment[]
  music_on?: boolean
  [key: string]: unknown
}

export interface CompilationOut {
  id: number
  title: string | null
  profile: CompilationProfile
  status: CompilationStatus
  edl: Edl | null
  output_path: string | null
  music_path: string | null
  duration_s: number | null
  error: string | null
  created_at: string
}

export interface CompilationCreate {
  profile: CompilationProfile
  clip_ids?: number[]
  from_selection?: 'starred' | 'top'
  music_path?: string
}

export interface CompilationPatch {
  edl?: Edl
  title?: string
  music_path?: string
}

export interface MetadataOut {
  title: string
  description: string
  tags: string[]
}

export interface PublishUploadBody {
  title: string
  description: string
  tags: string[]
}

export interface PublishRecordOut {
  id: number
  compilation_id: number
  youtube_video_id: string
  privacy_status: string
  title: string
  description: string
  tags: string[]
  uploaded_at: string
  published_at: string | null
}

export interface SettingsOut {
  footage_dir: string
  embeddings_backend: string
  llm_provider: string
  llm_model: string
  ollama_url: string
  youtube_authenticated: boolean
  [key: string]: unknown
}

export type SettingsPatch = Partial<Omit<SettingsOut, 'youtube_authenticated'>>
