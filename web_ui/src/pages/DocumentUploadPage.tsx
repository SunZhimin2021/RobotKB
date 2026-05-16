import { useState, useRef, DragEvent, FormEvent } from 'react';
import { api } from '../api/client';
import TagInput from '../components/TagInput';

interface UploadMeta {
  title: string;
  category: string;
  source_tier: string;
  applicable_chips: string[];
  applicable_boards: string[];
  ros_versions: string[];
  doc_version: string;
  tags: string[];
}

const ALLOWED_TYPES = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'text/plain'];
const ALLOWED_EXT = ['.pdf', '.docx', '.txt'];

export default function DocumentUploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [meta, setMeta] = useState<UploadMeta>({
    title: '',
    category: '',
    source_tier: '',
    applicable_chips: [],
    applicable_boards: [],
    ros_versions: [],
    doc_version: '',
    tags: [],
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<{ doc_id: string; status: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const validateFile = (f: File) => {
    const ext = '.' + f.name.split('.').pop()?.toLowerCase();
    if (!ALLOWED_EXT.includes(ext) && !ALLOWED_TYPES.includes(f.type)) {
      return '仅支持 PDF、DOCX、TXT 格式';
    }
    return null;
  };

  const handleFile = (f: File) => {
    const err = validateFile(f);
    if (err) { setError(err); return; }
    setError('');
    setFile(f);
    if (!meta.title) {
      setMeta((prev) => ({ ...prev, title: f.name.replace(/\.[^/.]+$/, '') }));
    }
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) handleFile(dropped);
  };

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(true);
  };

  const handleDragLeave = () => setDragging(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!file) { setError('请先选择文件'); return; }
    if (!meta.title.trim()) { setError('标题不能为空'); return; }
    if (!meta.category.trim()) { setError('分类不能为空'); return; }
    if (!meta.source_tier.trim()) { setError('来源层级不能为空'); return; }
    if (meta.applicable_chips.length === 0) { setError('至少填写一个适用芯片'); return; }

    setLoading(true);
    setError('');
    setResult(null);
    try {
      const res = await api.uploadDocument(file, meta);
      setResult(res.data);
      setFile(null);
      setMeta({
        title: '', category: '', source_tier: '', applicable_chips: [],
        applicable_boards: [], ros_versions: [], doc_version: '', tags: [],
      });
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } };
      setError(error.response?.data?.detail ?? '上传失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">上传文档</h1>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* 拖拽上传区 */}
        <div
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onClick={() => fileInputRef.current?.click()}
          className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
            dragging
              ? 'border-blue-500 bg-blue-50'
              : file
              ? 'border-green-400 bg-green-50'
              : 'border-gray-300 hover:border-blue-400 hover:bg-gray-50'
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.txt"
            className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
          />
          {file ? (
            <div>
              <p className="text-green-700 font-medium">{file.name}</p>
              <p className="text-green-600 text-sm mt-1">{(file.size / 1024).toFixed(1)} KB</p>
              <p className="text-gray-400 text-xs mt-2">点击重新选择文件</p>
            </div>
          ) : (
            <div>
              <p className="text-gray-500 font-medium">拖拽文件到此处，或点击选择文件</p>
              <p className="text-gray-400 text-sm mt-1">支持 PDF / DOCX / TXT 格式</p>
            </div>
          )}
        </div>

        {/* 元数据表单 */}
        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
          <h2 className="text-lg font-semibold text-gray-800 mb-4">文档元数据</h2>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                标题 <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={meta.title}
                onChange={(e) => setMeta((p) => ({ ...p, title: e.target.value }))}
                required
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                分类 <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={meta.category}
                onChange={(e) => setMeta((p) => ({ ...p, category: e.target.value }))}
                required
                placeholder="如：硬件手册、SDK 文档"
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                来源层级 <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={meta.source_tier}
                onChange={(e) => setMeta((p) => ({ ...p, source_tier: e.target.value }))}
                required
                placeholder="如：official、community"
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                文档版本
              </label>
              <input
                type="text"
                value={meta.doc_version}
                onChange={(e) => setMeta((p) => ({ ...p, doc_version: e.target.value }))}
                placeholder="如：v1.0.0"
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              适用芯片 <span className="text-red-500">*</span>
            </label>
            <TagInput
              value={meta.applicable_chips}
              onChange={(tags) => setMeta((p) => ({ ...p, applicable_chips: tags }))}
              placeholder="输入芯片型号，按 Enter 添加"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              适用开发板
            </label>
            <TagInput
              value={meta.applicable_boards}
              onChange={(tags) => setMeta((p) => ({ ...p, applicable_boards: tags }))}
              placeholder="输入开发板型号，按 Enter 添加"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              ROS 版本
            </label>
            <TagInput
              value={meta.ros_versions}
              onChange={(tags) => setMeta((p) => ({ ...p, ros_versions: tags }))}
              placeholder="输入 ROS 版本，按 Enter 添加"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              标签
            </label>
            <TagInput
              value={meta.tags}
              onChange={(tags) => setMeta((p) => ({ ...p, tags }))}
              placeholder="输入标签，按 Enter 添加"
            />
          </div>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
            {error}
          </div>
        )}

        {result && (
          <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg text-sm">
            上传成功！文档 ID：<span className="font-mono font-medium">{result.doc_id}</span>，状态：{result.status}
          </div>
        )}

        <button
          type="submit"
          disabled={loading || !file}
          className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white font-medium py-2.5 rounded-lg transition-colors"
        >
          {loading ? '上传中...' : '提交上传'}
        </button>
      </form>
    </div>
  );
}
