export interface Document {
  id: string;
  title: string;
  category: string;
  source_tier: string;
  applicable_chips: string[];
  applicable_boards: string[];
  ros_versions: string[];
  tags: string[];
  doc_version: string | null;
  status: string;
  chunk_count: number | null;
  created_at: string;
  updated_at: string;
}

export interface SearchHit {
  chunk_id: string;
  document_id: string;
  content: string;
  score: number;
  applicable_chips: string[];
  source_tier: string;
  matched_constraints: string[];
}

export interface SearchResponse {
  query: string;
  hits: SearchHit[];
  degraded: boolean;
  degradation_note: string | null;
}

export interface AuthToken {
  access_token: string;
  token_type: string;
  role: string;
}

export type UserRole = 'admin' | 'reviewer' | 'importer' | 'viewer';
