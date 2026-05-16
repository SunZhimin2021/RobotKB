import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import type { Document } from '../types';

export default function ReviewPage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const navigate = useNavigate();

  const fetchDocuments = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.listDocuments({ status: 'reviewing' });
      setDocuments(res.data.items);
      setTotal(res.data.total);
    } catch {
      setError('加载待审核文档失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, []);

  const handlePublish = async (id: string) => {
    setActionLoading(id);
    try {
      await api.publishDocument(id);
      await fetchDocuments();
    } catch {
      setError('发布操作失败');
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">待审核文档</h1>
        <span className="text-sm text-gray-500">共 {total} 篇待审核</span>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center h-48 text-gray-400">
          加载中...
        </div>
      ) : documents.length === 0 ? (
        <div className="bg-white border border-gray-200 rounded-xl p-12 text-center">
          <p className="text-gray-400 text-lg">暂无待审核文档</p>
          <p className="text-gray-300 text-sm mt-2">所有文档已审核完毕</p>
        </div>
      ) : (
        <div className="space-y-4">
          {documents.map((doc) => (
            <div
              key={doc.id}
              className="bg-white border border-gray-200 rounded-xl p-5 flex items-start gap-4"
            >
              <div
                className="flex-1 min-w-0 cursor-pointer"
                onClick={() => navigate(`/documents/${doc.id}`)}
              >
                <h3 className="font-semibold text-gray-900 truncate hover:text-blue-600 transition-colors">
                  {doc.title}
                </h3>
                <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-xs text-gray-500">
                  <span>分类：{doc.category}</span>
                  <span>来源层级：{doc.source_tier}</span>
                  <span>创建时间：{new Date(doc.created_at).toLocaleString('zh-CN')}</span>
                </div>
                {doc.applicable_chips.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {doc.applicable_chips.map((chip) => (
                      <span key={chip} className="px-1.5 py-0.5 bg-purple-100 text-purple-700 rounded text-xs">
                        {chip}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              <div className="flex gap-2 flex-shrink-0">
                <button
                  onClick={() => handlePublish(doc.id)}
                  disabled={actionLoading === doc.id}
                  className="px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-green-400 text-white text-sm font-medium rounded-lg transition-colors"
                >
                  {actionLoading === doc.id ? '处理中...' : '发布'}
                </button>
                <button
                  disabled={actionLoading === doc.id}
                  className="px-4 py-2 bg-red-100 hover:bg-red-200 disabled:opacity-50 text-red-700 text-sm font-medium rounded-lg transition-colors"
                  title="拒绝功能需后端支持"
                >
                  拒绝
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
