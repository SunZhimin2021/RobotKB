import axios from 'axios';
import type { AuthToken, Document, SearchResponse } from '../types';

const client = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
});

// 自动附加 Bearer token
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// 401 → 跳转 /login
client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('access_token');
      localStorage.removeItem('user_role');
      window.location.href = '/login';
    }
    return Promise.reject(err);
  }
);

export const api = {
  login: (username: string, password: string) =>
    client.post<AuthToken>('/auth/token', { username, password }),

  listDocuments: (params?: { status?: string; chip?: string; limit?: number }) =>
    client.get<{ items: Document[]; total: number }>('/documents', { params }),

  getDocument: (id: string) =>
    client.get<Document>(`/documents/${id}`),

  uploadDocument: (file: File, meta: object) => {
    const form = new FormData();
    form.append('file', file);
    form.append('meta', JSON.stringify(meta));
    return client.post<{ doc_id: string; status: string }>('/documents', form);
  },

  publishDocument: (id: string) =>
    client.post(`/documents/${id}/publish`),

  searchTest: (query: string, chips?: string) =>
    client.get<SearchResponse>('/search/test', { params: { query, chips } }),
};
