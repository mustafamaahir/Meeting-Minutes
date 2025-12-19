import React, { useState, useEffect } from 'react';
import { Search, Upload, LogOut, Menu, X, FileText, Calendar } from 'lucide-react';

// Use environment variable for API URL with fallback
const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

function App() {
  const [user, setUser] = useState(null);
  const [latestSummary, setLatestSummary] = useState(null);
  const [showLogin, setShowLogin] = useState(false);
  const [showUpload, setShowUpload] = useState(false);
  
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  
  const [query, setQuery] = useState('');
  const [maxWords, setMaxWords] = useState(300);
  const [queryResult, setQueryResult] = useState(null);
  const [loading, setLoading] = useState(false);
  
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadStatus, setUploadStatus] = useState('');
  
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [meetings, setMeetings] = useState([]);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (token) {
      fetchUserProfile(token);
    }
    fetchLatestSummary();
  }, []);

  const fetchLatestSummary = async () => {
    try {
      const res = await fetch(`${API_URL}/summary/latest`);
      const data = await res.json();
      setLatestSummary(data);
    } catch (err) {
      console.error('Failed to fetch summary:', err);
      setLatestSummary({ summary: 'Unable to load summary. Please check if the backend is running.' });
    }
  };

  const fetchUserProfile = async (token) => {
    try {
      const res = await fetch(`${API_URL}/auth/me`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setUser(data);
        fetchMeetings(token);
      } else {
        localStorage.removeItem('token');
      }
    } catch (err) {
      console.error('Failed to fetch profile:', err);
      localStorage.removeItem('token');
    }
  };

  const fetchMeetings = async (token) => {
    try {
      const res = await fetch(`${API_URL}/meetings`, {
        headers: { 'Authorization': `Bearer ${token || localStorage.getItem('token')}` }
      });
      if (res.ok) {
        const data = await res.json();
        setMeetings(data.meetings || []);
      }
    } catch (err) {
      console.error('Failed to fetch meetings:', err);
    }
  };

  const handleLogin = async () => {
    if (!username.trim() || !password.trim()) {
      alert('Please enter username and password');
      return;
    }

    setLoading(true);
    
    const formData = new FormData();
    formData.append('username', username);
    formData.append('password', password);
    
    try {
      const res = await fetch(`${API_URL}/auth/login`, {
        method: 'POST',
        body: formData
      });
      
      if (res.ok) {
        const data = await res.json();
        localStorage.setItem('token', data.access_token);
        await fetchUserProfile(data.access_token);
        setShowLogin(false);
        setUsername('');
        setPassword('');
      } else {
        const error = await res.json();
        alert('Login failed: ' + (error.detail || 'Check your credentials'));
      }
    } catch (err) {
      alert('Login error: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    setUser(null);
    setQueryResult(null);
    setMeetings([]);
  };

  const handleQuery = async () => {
    if (!query.trim()) {
      alert('Please enter a question');
      return;
    }

    setLoading(true);
    setQueryResult(null);
    
    const formData = new FormData();
    formData.append('query', query);
    formData.append('max_words', maxWords);
    
    try {
      const res = await fetch(`${API_URL}/query`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` },
        body: formData
      });
      
      if (res.ok) {
        const data = await res.json();
        setQueryResult(data);
      } else {
        const error = await res.json();
        alert('Query failed: ' + (error.detail || 'Unknown error'));
      }
    } catch (err) {
      alert('Query error: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleUpload = async () => {
    if (!uploadFile) {
      alert('Please select a PDF file');
      return;
    }
    
    setLoading(true);
    setUploadStatus('Uploading and processing PDF...');
    
    const formData = new FormData();
    formData.append('file', uploadFile);
    
    try {
      const res = await fetch(`${API_URL}/upload`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` },
        body: formData
      });
      
      if (res.ok) {
        const data = await res.json();
        setUploadStatus(`✓ Success! Uploaded meeting from ${data.meeting_date}`);
        setUploadFile(null);
        fetchLatestSummary();
        fetchMeetings();
        setTimeout(() => {
          setShowUpload(false);
          setUploadStatus('');
        }, 2000);
      } else {
        const error = await res.json();
        setUploadStatus(`✗ Upload failed: ${error.detail || 'Unknown error'}`);
      }
    } catch (err) {
      setUploadStatus(`✗ Upload error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (file && file.type === 'application/pdf') {
      setUploadFile(file);
      setUploadStatus('');
    } else {
      alert('Please select a valid PDF file');
      e.target.value = '';
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50">
      {/* Header */}
      <header className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex justify-between items-center">
          <div className="flex items-center gap-3">
            <FileText className="text-blue-600" size={32} />
            <h1 className="text-2xl font-bold text-blue-600">Meeting Minutes RAG</h1>
          </div>
          
          <div className="hidden md:flex items-center gap-4">
            {user ? (
              <>
                <span className="text-sm text-gray-600">
                  {user.username} <span className="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded">({user.role})</span>
                </span>
                {(user.role === 'admin' || user.role === 'secretary') && (
                  <button
                    onClick={() => setShowUpload(true)}
                    className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
                  >
                    <Upload size={18} />
                    Upload Minutes
                  </button>
                )}
                <button
                  onClick={handleLogout}
                  className="flex items-center gap-2 px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-lg transition"
                >
                  <LogOut size={18} />
                  Logout
                </button>
              </>
            ) : (
              <button
                onClick={() => setShowLogin(true)}
                className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
              >
                Login
              </button>
            )}
          </div>
          
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="md:hidden p-2 text-gray-600 hover:bg-gray-100 rounded-lg"
          >
            {mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
          </button>
        </div>
        
        {mobileMenuOpen && (
          <div className="md:hidden bg-white border-t px-4 py-3 space-y-2">
            {user ? (
              <>
                <div className="text-sm text-gray-600 py-2 border-b">
                  {user.username} ({user.role})
                </div>
                {(user.role === 'admin' || user.role === 'secretary') && (
                  <button
                    onClick={() => { setShowUpload(true); setMobileMenuOpen(false); }}
                    className="w-full flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg"
                  >
                    <Upload size={18} />
                    Upload Minutes
                  </button>
                )}
                <button
                  onClick={() => { handleLogout(); setMobileMenuOpen(false); }}
                  className="w-full flex items-center gap-2 px-4 py-2 text-gray-700 bg-gray-100 rounded-lg"
                >
                  <LogOut size={18} />
                  Logout
                </button>
              </>
            ) : (
              <button
                onClick={() => { setShowLogin(true); setMobileMenuOpen(false); }}
                className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg"
              >
                Login
              </button>
            )}
          </div>
        )}
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Latest Summary Section - Public */}
        <section className="bg-white rounded-xl shadow-md p-6 mb-8">
          <div className="flex items-center gap-2 mb-4">
            <Calendar className="text-blue-600" size={24} />
            <h2 className="text-xl font-semibold text-gray-800">Latest Meeting Summary</h2>
          </div>
          {latestSummary ? (
            <div>
              {latestSummary.meeting_date && (
                <p className="text-sm text-blue-600 font-medium mb-3">{latestSummary.meeting_date}</p>
              )}
              <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">{latestSummary.summary}</p>
            </div>
          ) : (
            <div className="flex items-center justify-center py-8">
              <div className="animate-pulse text-gray-400">Loading summary...</div>
            </div>
          )}
        </section>

        {/* Available Meetings List - For logged in users */}
        {user && meetings.length > 0 && (
          <section className="bg-white rounded-xl shadow-md p-6 mb-8">
            <h3 className="text-lg font-semibold text-gray-800 mb-4">Available Meetings</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {meetings.map((meeting) => (
                <div key={meeting.id} className="border border-gray-200 rounded-lg p-4 hover:border-blue-300 transition">
                  <p className="text-sm font-medium text-gray-800">{meeting.date}</p>
                  <p className="text-xs text-gray-500 mt-1">{meeting.filename}</p>
                  <p className="text-xs text-gray-400 mt-2">Uploaded: {new Date(meeting.uploaded_at).toLocaleDateString()}</p>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Query Section - Only for logged-in users */}
        {user ? (
          <section className="bg-white rounded-xl shadow-md p-6">
            <h2 className="text-xl font-semibold text-gray-800 mb-4 flex items-center gap-2">
              <Search size={24} className="text-blue-600" />
              Ask a Question
            </h2>
            
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Your Question
                </label>
                <textarea
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="e.g., What was discussed about the budget on 26th October, 2025?"
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
                  rows={4}
                />
                <p className="text-xs text-gray-500 mt-1">
                  Tip: Include a date to query specific meetings, or leave it out to search the most recent meeting
                </p>
              </div>
              
              <div className="bg-gray-50 p-4 rounded-lg">
                <label className="block text-sm font-medium text-gray-700 mb-3">
                  Response Length: <span className="text-blue-600 font-semibold">{maxWords} words</span>
                </label>
                <input
                  type="range"
                  min="50"
                  max="1000"
                  step="50"
                  value={maxWords}
                  onChange={(e) => setMaxWords(e.target.value)}
                  className="w-full"
                />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>50 (Brief)</span>
                  <span>500 (Moderate)</span>
                  <span>1000 (Detailed)</span>
                </div>
              </div>
              
              <button
                onClick={handleQuery}
                disabled={loading || !query.trim()}
                className="w-full sm:w-auto px-8 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition disabled:bg-gray-400 disabled:cursor-not-allowed font-medium"
              >
                {loading ? 'Searching...' : 'Search Meeting Minutes'}
              </button>
            </div>
            
            {/* Query Result */}
            {queryResult && (
              <div className="mt-6 p-5 bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-lg">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-xs text-blue-600 font-semibold uppercase tracking-wide">
                    Answer from Meeting: {queryResult.meeting_date}
                  </p>
                  <span className="text-xs text-gray-500">
                    {queryResult.sources_count} source{queryResult.sources_count !== 1 ? 's' : ''}
                  </span>
                </div>
                <div className="prose prose-sm max-w-none">
                  <p className="text-gray-800 leading-relaxed whitespace-pre-wrap">{queryResult.answer}</p>
                </div>
                
                {queryResult.sources && queryResult.sources.length > 0 && (
                  <details className="mt-4">
                    <summary className="text-xs text-gray-600 cursor-pointer hover:text-gray-800">
                      View source excerpts
                    </summary>
                    <div className="mt-2 space-y-2">
                      {queryResult.sources.map((source, idx) => (
                        <div key={idx} className="text-xs text-gray-600 bg-white p-3 rounded border border-gray-200">
                          <span className="font-medium">Source {idx + 1} (relevance: {(source.score * 100).toFixed(1)}%):</span>
                          <p className="mt-1">{source.text}</p>
                        </div>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            )}
          </section>
        ) : (
          <div className="text-center py-16 bg-white rounded-xl shadow-md">
            <Search size={64} className="mx-auto text-gray-300 mb-4" />
            <h3 className="text-xl font-semibold text-gray-800 mb-2">Login Required</h3>
            <p className="text-gray-600 mb-6 max-w-md mx-auto">
              Please log in to search through meeting minutes and get AI-powered answers to your questions
            </p>
            <button
              onClick={() => setShowLogin(true)}
              className="px-8 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition font-medium"
            >
              Login to Continue
            </button>
          </div>
        )}
      </main>

      {/* Login Modal */}
      {showLogin && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl shadow-xl p-8 w-full max-w-md">
            <h2 className="text-2xl font-bold text-gray-800 mb-6">Login to Meeting RAG</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Username</label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Enter your username"
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  onKeyPress={(e) => e.key === 'Enter' && handleLogin()}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  onKeyPress={(e) => e.key === 'Enter' && handleLogin()}
                />
              </div>
              <div className="flex gap-3 pt-2">
                <button
                  onClick={handleLogin}
                  disabled={loading}
                  className="flex-1 px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition disabled:bg-gray-400 disabled:cursor-not-allowed font-medium"
                >
                  {loading ? 'Logging in...' : 'Login'}
                </button>
                <button
                  onClick={() => setShowLogin(false)}
                  className="px-6 py-3 text-gray-700 hover:bg-gray-100 rounded-lg transition"
                >
                  Cancel
                </button>
              </div>
            </div>
            <p className="text-xs text-gray-500 mt-4 text-center">
              Default admin: username: <code className="bg-gray-100 px-1">admin</code> / password: <code className="bg-gray-100 px-1">admin123</code>
            </p>
          </div>
        </div>
      )}

      {/* Upload Modal */}
      {showUpload && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl shadow-xl p-8 w-full max-w-md">
            <h2 className="text-2xl font-bold text-gray-800 mb-2">Upload Meeting Minutes</h2>
            <p className="text-sm text-gray-600 mb-6">Upload a PDF with meeting date in format: "Sunday 26th October, 2025"</p>
            <div className="space-y-4">
              <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center hover:border-blue-400 transition">
                <input
                  type="file"
                  accept=".pdf"
                  onChange={handleFileSelect}
                  className="hidden"
                  id="file-upload"
                />
                <label htmlFor="file-upload" className="cursor-pointer">
                  <Upload size={48} className="mx-auto text-gray-400 mb-3" />
                  {uploadFile ? (
                    <div>
                      <p className="text-sm font-medium text-gray-800">{uploadFile.name}</p>
                      <p className="text-xs text-gray-500 mt-1">{(uploadFile.size / 1024 / 1024).toFixed(2)} MB</p>
                    </div>
                  ) : (
                    <div>
                      <p className="text-sm text-gray-600">Click to select PDF file</p>
                      <p className="text-xs text-gray-400 mt-1">or drag and drop</p>
                    </div>
                  )}
                </label>
              </div>
              
              {uploadStatus && (
                <div className={`p-3 rounded-lg text-sm ${
                  uploadStatus.startsWith('✓') 
                    ? 'bg-green-50 text-green-700 border border-green-200' 
                    : uploadStatus.startsWith('✗')
                    ? 'bg-red-50 text-red-700 border border-red-200'
                    : 'bg-blue-50 text-blue-700 border border-blue-200'
                }`}>
                  {uploadStatus}
                </div>
              )}
              
              <div className="flex gap-3 pt-2">
                <button
                  onClick={handleUpload}
                  disabled={loading || !uploadFile}
                  className="flex-1 px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition disabled:bg-gray-400 disabled:cursor-not-allowed font-medium"
                >
                  {loading ? 'Uploading...' : 'Upload & Process'}
                </button>
                <button
                  onClick={() => { setShowUpload(false); setUploadStatus(''); setUploadFile(null); }}
                  disabled={loading}
                  className="px-6 py-3 text-gray-700 hover:bg-gray-100 rounded-lg transition disabled:opacity-50"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Footer */}
      <footer className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 mt-12">
        <div className="text-center text-sm text-gray-500">
          <p>Meeting Minutes RAG System • Powered by Groq AI & Qdrant Vector Search</p>
        </div>
      </footer>
    </div>
  );
}

export default App;