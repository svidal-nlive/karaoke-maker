// src/api/client.ts
import axios from 'axios';

// Get API base URL from environment variable (set during build)
const apiBaseUrl = import.meta.env.VITE_API_BASE || 'https://kapi.vectorhost.net/api';

// Create axios instance with defaults
const apiClient = axios.create({
  baseURL: apiBaseUrl,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add interceptor to include the JWT token in every request
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      // Ensure token is well-formed
      const cleanToken = token.trim();
      if (cleanToken) {
        config.headers.Authorization = `Bearer ${cleanToken}`;
      }
    }
    return config;
  },
  (error) => {
    console.error('Request interceptor error:', error);
    return Promise.reject(error);
  }
);

// Add response interceptor to handle common errors
apiClient.interceptors.response.use(
  (response) => {
    // Validate response data
    if (!response.data) {
      console.warn('Empty response data received');
      response.data = {};
    }
    return response;
  },
  (error) => {
    console.error('Response error:', error);
    
    // Handle 401 Unauthorized - redirect to login
    if (error.response && error.response.status === 401) {
      // Clear auth state
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      
      // Only redirect if not already on login page
      if (!window.location.pathname.includes('/login')) {
        window.location.href = '/login';
      }
    }
    
    // Ensure error has a response structure
    if (!error.response) {
      error.response = {
        status: 500,
        data: { error: 'Network error or server unreachable' }
      };
    }
    
    return Promise.reject(error);
  }
);

export default apiClient;
