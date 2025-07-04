// src/components/Layout.tsx
import React, { useState } from 'react';
import { Link, Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import PasswordChangeModal from './PasswordChangeModal';

const Layout: React.FC = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [showPasswordChange, setShowPasswordChange] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };
  
  const isActive = (path: string) => {
    return location.pathname === path || location.pathname.startsWith(`${path}/`);
  };

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Navbar */}
      <nav className="bg-indigo-600 text-white shadow-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex">
              <div className="flex-shrink-0 flex items-center">
                <span className="text-xl font-bold">Karaoke Maker</span>
              </div>
              <div className="ml-6 flex items-center space-x-4">
                <Link 
                  to="/dashboard" 
                  className={`px-3 py-2 rounded-md text-sm font-medium ${
                    isActive('/dashboard') ? 'bg-indigo-700' : 'hover:bg-indigo-700'
                  }`}
                >
                  Dashboard
                </Link>
                <Link 
                  to="/upload" 
                  className={`px-3 py-2 rounded-md text-sm font-medium ${
                    isActive('/upload') ? 'bg-indigo-700' : 'hover:bg-indigo-700'
                  }`}
                >
                  Upload
                </Link>
                <Link 
                  to="/jobs" 
                  className={`px-3 py-2 rounded-md text-sm font-medium ${
                    isActive('/jobs') ? 'bg-indigo-700' : 'hover:bg-indigo-700'
                  }`}
                >
                  Jobs
                </Link>
                {user?.role === 'admin' && (
                  <Link 
                    to="/settings" 
                    className={`px-3 py-2 rounded-md text-sm font-medium ${
                      isActive('/settings') ? 'bg-indigo-700' : 'hover:bg-indigo-700'
                    }`}
                  >
                    Settings
                  </Link>
                )}
              </div>
            </div>
            <div className="flex items-center space-x-4">
              <span className="text-sm">Welcome, {user?.username}</span>
              <button 
                onClick={() => setShowPasswordChange(true)}
                className="px-3 py-2 rounded-md text-sm font-medium bg-indigo-700 hover:bg-indigo-800"
              >
                Change Password
              </button>
              <button 
                onClick={handleLogout}
                className="px-3 py-2 rounded-md text-sm font-medium bg-indigo-700 hover:bg-indigo-800"
              >
                Logout
              </button>
            </div>
          </div>
        </div>
      </nav>

      {/* Main content */}
      <main className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <Outlet />
      </main>
      
      <PasswordChangeModal 
        isOpen={showPasswordChange}
        onClose={() => setShowPasswordChange(false)}
        isRequired={false}
      />
    </div>
  );
};

export default Layout;
