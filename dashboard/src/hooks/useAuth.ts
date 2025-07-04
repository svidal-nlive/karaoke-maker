// src/hooks/useAuth.ts
import { useContext } from 'react';
import { AuthContext } from '../contexts/AuthContext';
import { login as apiLogin, changePassword as apiChangePassword, LoginCredentials, ChangePasswordRequest } from '../api/auth';

export const useAuth = () => {
  const context = useContext(AuthContext);
  
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  
  const { isAuthenticated, user, login: setAuth, logout } = context;
  
  const login = async (credentials: LoginCredentials) => {
    try {
      const response = await apiLogin(credentials);
      setAuth(response.access_token, response.user);
      return { success: true, user: response.user };
    } catch (error) {
      console.error('Login failed:', error);
      return { success: false, error };
    }
  };

  const changePassword = async (request: ChangePasswordRequest) => {
    try {
      const response = await apiChangePassword(request);
      setAuth(response.access_token, response.user);
      return { success: true, user: response.user };
    } catch (error) {
      console.error('Password change failed:', error);
      return { success: false, error };
    }
  };
  
  return {
    isAuthenticated,
    user,
    login,
    changePassword,
    logout,
  };
};
