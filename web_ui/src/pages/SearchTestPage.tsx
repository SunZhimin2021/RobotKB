import { useState, FormEvent } from 'react';
import { api } from '../api/client';
import TagInput from '../components/TagInput';
import type { SearchResponse, SearchHit } from '../types';

function HitCard({ hit }: { hit: SearchHit }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5 space-y-3">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <p className="text-sm text-gray-800 leading-relaxed line-clamp-4">{hit.content}</p>
        </div>
        <div className="flex-shrink-0 text-right">
          <span className="text-lg font-bold text-blue-600">{hit.score.toFixed(3)}</span>
          <p className="text-xs text-gray-400">相关度</p>
        </div>
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500 border-t border-gray-100 pt-3">
        <span>文档 ID：<span className="font-mono">{hit.document_id}</span></span>
        <span>来源层级：{hit.source_tier}</span>
      </div>

      <div className="flex flex-wrap gap-2">
        {hit.applicable_chips.map((chip) => (
          <span key={chip} className="px-2 py-0.5 bg-purple-100 text-purple-700 rounded text-xs">
            {chip}
          </span>
        ))}
        {hit.matched_constraints.map((c) => (
          <span key={c} className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-xs">
            {c}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function SearchTestPage() {
  const [query, setQuery] = useState('');
  const [chips, setChips] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<SearchResponse | null>(null);

  const handleSearch = async (e: FormEvent) => {
    e.preventDefault();
    if (!query.trim()) { setError('请输入搜索内容'); return; }
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const chipsParam = chips.length > 0 ? chips.join(',') : undefined;
      const res = await api.searchTest(query, chipsParam);
      setResult(res.data);
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } };
      setError(error.response?.data?.detail ?? '搜索失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">检索测试</h1>

      <form onSubmit={handleSearch} className="bg-white rounded-xl border border-gray-200 p-6 mb-6 space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">搜索内容</label>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="输入搜索关键词或问题..."
            className="w-full border border-gray-300 rounded-md px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            芯片筛选（可选）
          </label>
          <TagInput
            value={chips}
            onChange={setChips}
            placeholder="输入芯片型号，按 Enter 添加"
          />
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white text-sm font-medium rounded-lg transition-colors"
        >
          {loading ? '搜索中...' : '开始搜索'}
        </button>
      </form>

      {result && (
        <div className="space-y-4">
          {/* 降级警告 */}
          {result.degraded && (
            <div className="bg-yellow-50 border border-yellow-300 text-yellow-800 px-4 py-3 rounded-lg text-sm">
              <strong>注意：</strong>搜索结果已降级处理。
              {result.degradation_note && <span> {result.degradation_note}</span>}
            </div>
          )}

          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-800">
              搜索结果
            </h2>
            <span className="text-sm text-gray-500">
              共 {result.hits.length} 条结果（查询："{result.query}"）
            </span>
          </div>

          {result.hits.length === 0 ? (
            <div className="bg-white border border-gray-200 rounded-xl p-8 text-center text-gray-400">
              未找到相关结果
            </div>
          ) : (
            <div className="space-y-3">
              {result.hits.map((hit) => (
                <HitCard key={hit.chunk_id} hit={hit} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
