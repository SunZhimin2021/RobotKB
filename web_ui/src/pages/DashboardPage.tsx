import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import { useAuth } from '../store/auth';

interface Stats {
  total: number;
  published: number;
  reviewing: number;
  pending: number;
}

export default function DashboardPage() {
  const [stats, setStats] = useState<Stats>({ total: 0, published: 0, reviewing: 0, pending: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const { hasRole } = useAuth();

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const [allRes, publishedRes, reviewingRes, pendingRes] = await Promise.all([
          api.listDocuments({ limit: 1 }),
          api.listDocuments({ status: 'published', limit: 1 }),
          api.listDocuments({ status: 'reviewing', limit: 1 }),
          api.listDocuments({ status: 'pending', limit: 1 }),
        ]);
        setStats({
          total: allRes.data.total,
          published: publishedRes.data.total,
          reviewing: reviewingRes.data.total,
          pending: pendingRes.data.total,
        });
      } catch {
        setError('加载统计数据失败');
      } finally {
        setLoading(false);
      }
    };
    fetchStats();
  }, []);

  const statCards = [
    { label: '文档总数', value: stats.total, color: 'bg-blue-50 text-blue-700 border-blue-200' },
    { label: '已发布', value: stats.published, color: 'bg-green-50 text-green-700 border-green-200' },
    { label: '待审核', value: stats.reviewing, color: 'bg-yellow-50 text-yellow-700 border-yellow-200' },
    { label: '待处理', value: stats.pending, color: 'bg-gray-50 text-gray-700 border-gray-200' },
  ];

  const quickLinks = [
    { to: '/documents', label: '查看文档列表', show: true },
    { to: '/documents/upload', label: '上传新文档', show: hasRole('importer') },
    { to: '/search-test', label: '检索测试', show: true },
    { to: '/review', label: '审核文档', show: hasRole('reviewer') },
    { to: '/stats', label: '详细统计', show: hasRole('admin') },
  ].filter((l) => l.show);

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">仪表盘</h1>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-6 text-sm">
          {error}
        </div>
      )}

      {/* 统计卡片 */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4 mb-8">
        {statCards.map((card) => (
          <div
            key={card.label}
            className={`border rounded-xl p-5 ${card.color}`}
          >
            <p className="text-sm font-medium opacity-80">{card.label}</p>
            <p className="text-3xl font-bold mt-2">
              {loading ? '—' : card.value}
            </p>
          </div>
        ))}
      </div>

      {/* 快速链接 */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">快速访问</h2>
        <div className="flex flex-wrap gap-3">
          {quickLinks.map((link) => (
            <Link
              key={link.to}
              to={link.to}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors"
            >
              {link.label}
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
