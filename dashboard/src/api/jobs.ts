// src/api/jobs.ts
import apiClient from './client';

export interface Job {
  id: string;
  filename: string;
  status: string;
  error?: string;
  createdAt: string;
  updatedAt?: string;
  stems?: string[];
}

export interface JobsResponse {
  jobs: Job[];
  total: number;
}

export interface JobsRequest {
  limit?: number;
  offset?: number;
  status?: string;
}

export interface RawJobsResponse {
  jobs?: Job[];
  total?: number;
}

export const getJobs = async (): Promise<Job[]> => {
  try {
    const response = await apiClient.get<Job[]>('/jobs');
    return Array.isArray(response.data) ? response.data : [];
  } catch (error) {
    console.error('Error getting jobs:', error);
    return [];
  }
};

export const fetchJobs = async (params?: JobsRequest): Promise<JobsResponse> => {
  try {
    const response = await apiClient.get<RawJobsResponse | Job[]>('/jobs', { params });
    
    // Handle array response format
    if (Array.isArray(response.data)) {
      return {
        jobs: response.data,
        total: response.data.length
      };
    }
    
    // Handle object response format
    const data = response.data as RawJobsResponse;
    return {
      jobs: Array.isArray(data?.jobs) ? data.jobs : [],
      total: typeof data?.total === 'number' ? data.total : 0
    };
  } catch (error) {
    console.error('Error fetching jobs:', error);
    return { jobs: [], total: 0 };
  }
};

export const getJob = async (jobId: string): Promise<Job> => {
  const response = await apiClient.get<Job>(`/jobs/${jobId}`);
  return response.data;
};
