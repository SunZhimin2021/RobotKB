import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthContext, useAuthState } from './store/auth';
import Layout from './components/Layout';
import PrivateRoute from './components/PrivateRoute';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import DocumentListPage from './pages/DocumentListPage';
import DocumentUploadPage from './pages/DocumentUploadPage';
import DocumentDetailPage from './pages/DocumentDetailPage';
import SearchTestPage from './pages/SearchTestPage';
import ReviewPage from './pages/ReviewPage';
import StatsPage from './pages/StatsPage';

function AuthProvider({ children }: { children: React.ReactNode }) {
  const authState = useAuthState();
  return (
    <AuthContext.Provider value={authState}>
      {children}
    </AuthContext.Provider>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/"
            element={
              <PrivateRoute minRole="viewer">
                <Layout />
              </PrivateRoute>
            }
          >
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard" element={<DashboardPage />} />
            <Route
              path="documents"
              element={
                <PrivateRoute minRole="viewer">
                  <DocumentListPage />
                </PrivateRoute>
              }
            />
            <Route
              path="documents/upload"
              element={
                <PrivateRoute minRole="importer">
                  <DocumentUploadPage />
                </PrivateRoute>
              }
            />
            <Route
              path="documents/:id"
              element={
                <PrivateRoute minRole="viewer">
                  <DocumentDetailPage />
                </PrivateRoute>
              }
            />
            <Route
              path="search-test"
              element={
                <PrivateRoute minRole="viewer">
                  <SearchTestPage />
                </PrivateRoute>
              }
            />
            <Route
              path="review"
              element={
                <PrivateRoute minRole="reviewer">
                  <ReviewPage />
                </PrivateRoute>
              }
            />
            <Route
              path="stats"
              element={
                <PrivateRoute minRole="admin">
                  <StatsPage />
                </PrivateRoute>
              }
            />
          </Route>
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
