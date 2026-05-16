import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../store/auth';

interface NavItem {
  to: string;
  label: string;
  minRole: 'viewer' | 'importer' | 'reviewer' | 'admin';
}

const navItems: NavItem[] = [
  { to: '/dashboard', label: '仪表盘', minRole: 'viewer' },
  { to: '/documents', label: '文档列表', minRole: 'viewer' },
  { to: '/documents/upload', label: '上传文档', minRole: 'importer' },
  { to: '/search-test', label: '检索测试', minRole: 'viewer' },
  { to: '/review', label: '待审核', minRole: 'reviewer' },
  { to: '/stats', label: '统计信息', minRole: 'admin' },
];

export default function Layout() {
  const { role, logout, hasRole } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const roleLabelMap: Record<string, string> = {
    admin: '管理员',
    reviewer: '审核员',
    importer: '导入员',
    viewer: '查看员',
  };

  return (
    <div className="flex h-screen bg-gray-100">
      {/* 左侧导航栏 */}
      <aside className="w-56 bg-gray-900 flex flex-col">
        <div className="px-6 py-5 border-b border-gray-700">
          <h1 className="text-white font-bold text-lg">RobotKB</h1>
          <p className="text-gray-400 text-xs mt-1">机器人知识库管理系统</p>
        </div>
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {navItems
            .filter((item) => hasRole(item.minRole))
            .map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `block px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-blue-600 text-white'
                      : 'text-gray-300 hover:bg-gray-700 hover:text-white'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
        </nav>
        <div className="px-4 py-4 border-t border-gray-700">
          <div className="text-gray-400 text-xs mb-2">
            角色：{role ? roleLabelMap[role] ?? role : '未知'}
          </div>
          <button
            onClick={handleLogout}
            className="w-full text-left px-3 py-2 rounded-md text-sm font-medium text-gray-300 hover:bg-gray-700 hover:text-white transition-colors"
          >
            退出登录
          </button>
        </div>
      </aside>

      {/* 主内容区域 */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* 顶部 Header */}
        <header className="bg-white shadow-sm px-6 py-4 flex items-center justify-between">
          <h2 className="text-gray-700 font-semibold text-lg">RobotKB 管理界面</h2>
          <div className="text-sm text-gray-500">
            当前角色：<span className="font-medium text-gray-700">{role ? roleLabelMap[role] ?? role : '未知'}</span>
          </div>
        </header>

        {/* 页面内容 */}
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
