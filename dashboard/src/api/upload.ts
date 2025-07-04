// src/api/upload.ts
import apiClient from './client';
import { AxiosProgressEvent } from 'axios';

export interface UploadResponse {
  status: string;
  message: string;
  filename: string;
  jobId: string; // Renamed from job_id for consistency with frontend
}

export type ProgressCallback = (progress: number) => void;

export const uploadFile = async (
  file: File, 
  onProgress?: ProgressCallback
): Promise<UploadResponse> => {
  const formData = new FormData();
  formData.append('file', file);
  
  const response = await apiClient.post<UploadResponse>('/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    onUploadProgress: onProgress 
      ? (progressEvent: AxiosProgressEvent) => {
          const percentCompleted = Math.round(
            (progressEvent.loaded * 100) / (progressEvent.total || 100)
          );
          onProgress(percentCompleted);
        }
      : undefined,
  });
  
  // Convert job_id to jobId if needed
  const data = response.data;
  if ('job_id' in data && !('jobId' in data)) {
    // @ts-ignore - Handle API inconsistency
    data.jobId = data.job_id;
  }
  
  return data;
};
