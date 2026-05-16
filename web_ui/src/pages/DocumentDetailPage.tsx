import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
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

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex gap-3 py-3 border-b border-gray-100 last:border-0">
      <span className="w-32 flex-shrink-0 text-sm font-medium text-gray-500">{label}</span>
      <span className="text-sm text-gray-900 flex-1">{value}</span>
    </div>
  );
}

function TagList({ tags }: { tags: string[]; color?: string }) {
  if (!tags || tags.length === 0) return <span className="text-gray-400 text-sm">—</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {tags.map((tag) => (
        <span key={tag} className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-xs">
          {tag}
        </span>
      ))}
    </div>
  );
}

export default function DocumentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [doc, setDoc] = useState<Document | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [publishing, setPublishing] = useState(false);
  const { hasRole } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!id) return;
    const fetchDoc = async () => {
      try {
        const res = await api.getDocument(id);
        setDoc(res.data);
      } catch {
        setError('加载文档详情失败');
      } finally {
        setLoading(false);
      }
    };
    fetchDoc();
  }, [id]);

  const handlePublish = async () => {
    if (!id) return;
    setPublishing(true);
    try {
      await api.publishDocument(id);
      const res = await api.getDocument(id);
      setDoc(res.data);
    } catch {
      setError('发布失败');
    } finally {
      setPublishing(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-gray-400">加载中...</p>
      </div>
    );
  }

  if (error || !doc) {
    return (
      <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
        {error || '文档不存在'}
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={() => navigate(-1)}
          className="text-sm text-blue-600 hover:text-blue-800"
        >
          ← 返回
        </button>
        <h1 className="text-2xl font-bold text-gray-900 flex-1 truncate">{doc.title}</h1>
        <span className={`px-3 py-1 rounded-full text-sm font-medium ${STATUS_COLORS[doc.status] ?? 'bg-gray-100 text-gray-700'}`}>
          {STATUS_LABELS[doc.status] ?? doc.status}
        </span>
        {hasRole('reviewer') && doc.status !== 'published' && (
          <button
            onClick={handlePublish}
            disabled={publishing}
            className="px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-green-400 text-white text-sm rounded-lg transition-colors"
          >
            {publishing ? '发布中...' : '发布文档'}
          </button>
        )}
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm">
          {error}
        </div>
      )}

      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <InfoRow label="文档 ID" value={<span className="font-mono text-xs">{doc.id}</span>} />
        <InfoRow label="分类" value={doc.category} />
        <InfoRow label="来源层级" value={doc.source_tier} />
        <InfoRow label="文档版本" value={doc.doc_version ?? '—'} />
        <InfoRow label="分块数量" value={doc.chunk_count ?? '—'} />
        <InfoRow label="适用芯片" value={<TagList tags={doc.applicable_chips} />} />
        <InfoRow label="适用开发板" value={<TagList tags={doc.applicable_boards} />} />
        <InfoRow label="ROS 版本" value={<TagList tags={doc.ros_versions} />} />
        <InfoRow label="标签" value={<TagList tags={doc.tags} />} />
        <InfoRow
          label="创建时间"
          value={new Date(doc.created_at).toLocaleString('zh-CN')}
        />
        <InfoRow
          label="更新时间"
          value={new Date(doc.updated_at).toLocaleString('zh-CN')}
        />
      </div>
    </div>
  );
}
