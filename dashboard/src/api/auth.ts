// src/api/auth.ts
import apiClient from './client';

export interface LoginCredentials {
  username: string;
  password: string;
}

export interface User {
  username: string;
  role: 'admin' | 'user';
  needs_password_change?: boolean;
}

export interface AuthResponse {
  access_token: string;
  user: User;
}

export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
  new_username?: string;
}

export const login = async (credentials: LoginCredentials): Promise<AuthResponse> => {
  const response = await apiClient.post<AuthResponse>('/login', credentials);
  return response.data;
};

export const changePassword = async (request: ChangePasswordRequest): Promise<AuthResponse> => {
  const response = await apiClient.post<AuthResponse>('/change-password', request);
  return response.data;
};
