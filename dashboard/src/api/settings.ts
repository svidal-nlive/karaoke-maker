// src/api/settings.ts
import apiClient from './client';

// Backend API response format
interface ApiSettings {
  splitter_type: string;
  stems: number | string;
  stem_types: string;
  chunking_enabled?: boolean | string;
  chunk_length_ms?: number | string;
  clean_intermediate_files?: boolean | string;
  max_retries?: number | string;
  retry_delay?: number | string;
}

// Frontend settings format
export interface Settings {
  splitterType: string;
  stems: number;
  stemTypes: string[];
  chunking: boolean;
  chunkLengthMs: number;
  cleanIntermediateFiles: boolean;
  maxRetries: number;
  retryDelay: number;
}

// Convert API format to frontend format
const convertFromApiFormat = (apiSettings: ApiSettings): Settings => {
  return {
    splitterType: apiSettings.splitter_type || 'SPLEETER',
    stems: typeof apiSettings.stems === 'string' ? parseInt(apiSettings.stems, 10) : (apiSettings.stems || 4),
    stemTypes: (apiSettings.stem_types || 'vocals,drums,bass,other').split(',').map(s => s.trim()),
    chunking: apiSettings.chunking_enabled === 'true' || apiSettings.chunking_enabled === true || false,
    chunkLengthMs: typeof apiSettings.chunk_length_ms === 'string' 
      ? parseInt(apiSettings.chunk_length_ms, 10) 
      : (apiSettings.chunk_length_ms || 240000),
    cleanIntermediateFiles: apiSettings.clean_intermediate_files === 'true' 
      || apiSettings.clean_intermediate_files === true 
      || true,
    maxRetries: typeof apiSettings.max_retries === 'string' 
      ? parseInt(apiSettings.max_retries, 10) 
      : (apiSettings.max_retries || 3),
    retryDelay: typeof apiSettings.retry_delay === 'string' 
      ? parseInt(apiSettings.retry_delay, 10) 
      : (apiSettings.retry_delay || 10),
  };
};

// Convert frontend format to API format
const convertToApiFormat = (settings: Settings): ApiSettings => {
  return {
    splitter_type: settings.splitterType,
    stems: settings.stems,
    stem_types: settings.stemTypes.join(','),
    chunking_enabled: settings.chunking,
    chunk_length_ms: settings.chunkLengthMs,
    clean_intermediate_files: settings.cleanIntermediateFiles,
    max_retries: settings.maxRetries,
    retry_delay: settings.retryDelay,
  };
};

export const getSettings = async (): Promise<Settings> => {
  const response = await apiClient.get<ApiSettings>('/settings');
  return convertFromApiFormat(response.data);
};

export const updateSettings = async (settings: Settings): Promise<Settings> => {
  const apiSettings = convertToApiFormat(settings);
  const response = await apiClient.post<ApiSettings>('/settings', apiSettings);
  return convertFromApiFormat(response.data);
};
