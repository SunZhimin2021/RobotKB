import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { useAuth } from '../store/auth';
import type { Document } from '../types';

const STATUS_LABELS: Record<string, string> = {
  pending: '待处理',
  reviewing: '审核中',
  published: '已发布',
};

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-gray-100 text-gray-700',
  reviewing: 'bg-yellow-100 text-yellow-700',
  published: 'bg-green-100 text-green-700',
};

export default function DocumentListPage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [chipFilter, setChipFilter] = useState('');
  const [publishing, setPublishing] = useState<string | null>(null);
  const { hasRole } = useAuth();
  const navigate = useNavigate();

  const fetchDocuments = async () => {
    setLoading(true);
    setError('');
    try {
      const params: { status?: string; chip?: string } = {};
      if (statusFilter) params.status = statusFilter;
      if (chipFilter) params.chip = chipFilter;
      const res = await api.listDocuments(params);
      setDocuments(res.data.items);
      setTotal(res.data.total);
    } catch {
      setError('加载文档列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, chipFilter]);

  const handlePublish = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    setPublishing(id);
    try {
      await api.publishDocument(id);
      await fetchDocuments();
    } catch {
      setError('发布失败');
    } finally {
      setPublishing(null);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">文档列表</h1>
        <span className="text-sm text-gray-500">共 {total} 篇文档</span>
      </div>

      {/* 筛选栏 */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 mb-4 flex flex-wrap gap-4">
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-gray-700">状态：</label>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="border border-gray-300 rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">全部</option>
            <option value="pending">待处理</option>
            <option value="reviewing">审核中</option>
            <option value="published">已发布</option>
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-gray-700">芯片：</label>
          <input
            type="text"
            value={chipFilter}
            onChange={(e) => setChipFilter(e.target.value)}
            placeholder="输入芯片型号筛选"
            className="border border-gray-300 rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm">
          {error}
        </div>
      )}

      {/* 表格 */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="text-left px-4 py-3 font-medium text-gray-700">标题</th>
              <th className="text-left px-4 py-3 font-medium text-gray-700">分类</th>
              <th className="text-left px-4 py-3 font-medium text-gray-700">来源层级</th>
              <th className="text-left px-4 py-3 font-medium text-gray-700">状态</th>
              <th className="text-left px-4 py-3 font-medium text-gray-700">适用芯片</th>
              <th className="text-left px-4 py-3 font-medium text-gray-700">创建时间</th>
              {hasRole('reviewer') && (
                <th className="text-left px-4 py-3 font-medium text-gray-700">操作</th>
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {loading ? (
              <tr>
                <td colSpan={hasRole('reviewer') ? 7 : 6} className="px-4 py-8 text-center text-gray-400">
                  加载中...
                </td>
              </tr>
            ) : documents.length === 0 ? (
              <tr>
                <td colSpan={hasRole('reviewer') ? 7 : 6} className="px-4 py-8 text-center text-gray-400">
                  暂无文档
                </td>
              </tr>
            ) : (
              documents.map((doc) => (
                <tr
                  key={doc.id}
                  onClick={() => navigate(`/documents/${doc.id}`)}
                  className="hover:bg-blue-50 cursor-pointer transition-colors"
                >
                  <td className="px-4 py-3 font-medium text-gray-900 max-w-xs truncate">
                    {doc.title}
                  </td>
                  <td className="px-4 py-3 text-gray-600">{doc.category}</td>
                  <td className="px-4 py-3 text-gray-600">{doc.source_tier}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[doc.status] ?? 'bg-gray-100 text-gray-700'}`}>
                      {STATUS_LABELS[doc.status] ?? doc.status}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {doc.applicable_chips.slice(0, 3).map((chip) => (
                        <span key={chip} className="px-1.5 py-0.5 bg-purple-100 text-purple-700 rounded text-xs">
                          {chip}
                        </span>
                      ))}
                      {doc.applicable_chips.length > 3 && (
                        <span className="text-xs text-gray-400">+{doc.applicable_chips.length - 3}</span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {new Date(doc.created_at).toLocaleDateString('zh-CN')}
                  </td>
                  {hasRole('reviewer') && (
                    <td className="px-4 py-3">
                      {doc.status !== 'published' && (
                        <button
                          onClick={(e) => handlePublish(e, doc.id)}
                          disabled={publishing === doc.id}
                          className="px-3 py-1 bg-green-600 hover:bg-green-700 disabled:bg-green-400 text-white text-xs rounded-md transition-colors"
                        >
                          {publishing === doc.id ? '发布中...' : '发布'}
                        </button>
                      )}
                    </td>
                  )}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
