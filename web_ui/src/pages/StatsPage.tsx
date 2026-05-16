import { useEffect, useState } from 'react';
import { api } from '../api/client';

interface StatusCount {
  label: string;
  status: string;
  count: number;
  color: string;
  bgColor: string;
}

export default function StatsPage() {
  const [statusCounts, setStatusCounts] = useState<StatusCount[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const [allRes, publishedRes, reviewingRes, pendingRes] = await Promise.all([
          api.listDocuments({ limit: 1 }),
          api.listDocuments({ status: 'published', limit: 1 }),
          api.listDocuments({ status: 'reviewing', limit: 1 }),
          api.listDocuments({ status: 'pending', limit: 1 }),
        ]);

        setTotal(allRes.data.total);
        setStatusCounts([
          {
            label: '已发布',
            status: 'published',
            count: publishedRes.data.total,
            color: 'text-green-700',
            bgColor: 'bg-green-50 border-green-200',
          },
          {
            label: '审核中',
            status: 'reviewing',
            count: reviewingRes.data.total,
            color: 'text-yellow-700',
            bgColor: 'bg-yellow-50 border-yellow-200',
          },
          {
            label: '待处理',
            status: 'pending',
            count: pendingRes.data.total,
            color: 'text-gray-700',
            bgColor: 'bg-gray-50 border-gray-200',
          },
        ]);
      } catch {
        setError('加载统计数据失败');
      } finally {
        setLoading(false);
      }
    };
    fetchStats();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400">
        加载中...
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">统计信息</h1>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-6 text-sm">
          {error}
        </div>
      )}

      {/* 总计卡片 */}
      <div className="bg-blue-600 rounded-2xl p-6 mb-6 text-white">
        <p className="text-blue-100 text-sm font-medium">文档总数</p>
        <p className="text-5xl font-bold mt-2">{total}</p>
        <p className="text-blue-200 text-sm mt-2">所有状态的文档之和</p>
      </div>

      {/* 状态分布 */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        {statusCounts.map((item) => (
          <div key={item.status} className={`border rounded-xl p-5 ${item.bgColor}`}>
            <p className={`text-sm font-medium ${item.color} opacity-80`}>{item.label}</p>
            <p className={`text-4xl font-bold mt-2 ${item.color}`}>{item.count}</p>
            <p className={`text-xs mt-2 ${item.color} opacity-60`}>
              {total > 0 ? ((item.count / total) * 100).toFixed(1) : '0.0'}%
            </p>
          </div>
        ))}
      </div>

      {/* 进度条 */}
      {total > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl p-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-4">状态分布</h2>
          <div className="space-y-3">
            {statusCounts.map((item) => (
              <div key={item.status}>
                <div className="flex justify-between text-sm mb-1">
                  <span className="font-medium text-gray-700">{item.label}</span>
                  <span className="text-gray-500">{item.count} 篇（{total > 0 ? ((item.count / total) * 100).toFixed(1) : '0.0'}%）</span>
                </div>
                <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${
                      item.status === 'published'
                        ? 'bg-green-500'
                        : item.status === 'reviewing'
                        ? 'bg-yellow-500'
                        : 'bg-gray-400'
                    }`}
                    style={{ width: total > 0 ? `${(item.count / total) * 100}%` : '0%' }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mt-6 bg-white border border-gray-200 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-gray-800 mb-3">系统信息</h2>
        <div className="text-sm text-gray-500 space-y-2">
          <p>后端 API：<span className="font-mono text-gray-700">/api/v1</span></p>
          <p>认证方式：<span className="text-gray-700">Bearer Token（JWT）</span></p>
          <p>当前角色：<span className="font-medium text-gray-700">admin（管理员）</span></p>
        </div>
      </div>
    </div>
  );
}
