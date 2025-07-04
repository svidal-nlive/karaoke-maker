import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchJobs, Job } from '../api/jobs';

const Jobs: React.FC = () => {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [page, setPage] = useState(0);
  const [totalJobs, setTotalJobs] = useState(0);
  const [filter, setFilter] = useState<string>('');
  
  const limit = 10;
  const navigate = useNavigate();
  
  const loadJobs = async () => {
    try {
      setLoading(true);
      const response = await fetchJobs({
        limit,
        offset: page * limit,
        status: filter || undefined
      });
      // Add null checks and ensure we always have an array
      setJobs(Array.isArray(response?.jobs) ? response.jobs : []);
      setTotalJobs(response?.total || 0);
    } catch (err) {
      setError('Failed to load jobs');
      console.error('Error loading jobs:', err);
      // Ensure we have a valid array even on error
      setJobs([]);
      setTotalJobs(0);
    } finally {
      setLoading(false);
    }
  };
  
  useEffect(() => {
    loadJobs();
  }, [page, filter]);
  
  const handleViewDetails = (jobId: string) => {
    navigate(`/jobs/${jobId}`);
  };
  
  const totalPages = Math.ceil(totalJobs / limit);
  
  const handlePrevPage = () => {
    if (page > 0) {
      setPage(page - 1);
    }
  };
  
  const handleNextPage = () => {
    if (page < totalPages - 1) {
      setPage(page + 1);
    }
  };
  
  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Jobs</h1>
        <div className="flex items-center space-x-4">
          <label className="flex items-center">
            <span className="mr-2 text-gray-700">Filter:</span>
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="border rounded p-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="">All</option>
              <option value="waiting">Waiting</option>
              <option value="processing">Processing</option>
              <option value="metadata_extracted">Metadata Extracted</option>
              <option value="stems_split">Stems Split</option>
              <option value="completed">Completed</option>
              <option value="error">Error</option>
            </select>
          </label>
          <button
            onClick={loadJobs}
            className="bg-indigo-600 text-white px-4 py-2 rounded hover:bg-indigo-700 transition"
          >
            Refresh
          </button>
        </div>
      </div>
      
      {loading ? (
        <div className="text-center py-8">
          <p className="text-gray-500">Loading jobs...</p>
        </div>
      ) : error ? (
        <div className="bg-red-100 text-red-700 p-4 rounded mb-4">
          {error}
        </div>
      ) : jobs.length === 0 ? (
        <div className="bg-white rounded-lg shadow p-8 text-center">
          <p className="text-gray-500">No jobs found.</p>
        </div>
      ) : (
        <>
          <div className="bg-white rounded-lg shadow overflow-hidden">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    File
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Created
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Updated
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {jobs.map((job) => (
                  <tr key={job.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-sm font-medium text-gray-900">{job.filename}</div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full 
                        ${job.status === 'completed' ? 'bg-green-100 text-green-800' : 
                          job.status === 'error' ? 'bg-red-100 text-red-800' : 
                          'bg-yellow-100 text-yellow-800'}`}>
                        {job.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-sm text-gray-500">
                        {new Date(job.createdAt).toLocaleString()}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-sm text-gray-500">
                        {job.updatedAt ? new Date(job.updatedAt).toLocaleString() : '-'}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                      <button
                        onClick={() => handleViewDetails(job.id)}
                        className="text-indigo-600 hover:text-indigo-900"
                      >
                        Details
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          
          {/* Pagination */}
          <div className="mt-4 flex items-center justify-between">
            <div className="text-sm text-gray-700">
              Showing <span className="font-medium">{jobs.length}</span> of{' '}
              <span className="font-medium">{totalJobs}</span> results
            </div>
            <div className="flex space-x-2">
              <button
                onClick={handlePrevPage}
                disabled={page === 0}
                className={`px-3 py-1 rounded border ${
                  page === 0 
                    ? 'text-gray-400 border-gray-300 cursor-not-allowed' 
                    : 'text-gray-700 border-gray-300 hover:bg-gray-50'
                }`}
              >
                Previous
              </button>
              <div className="px-3 py-1 text-gray-700">
                Page {page + 1} of {Math.max(1, totalPages)}
              </div>
              <button
                onClick={handleNextPage}
                disabled={page >= totalPages - 1}
                className={`px-3 py-1 rounded border ${
                  page >= totalPages - 1 
                    ? 'text-gray-400 border-gray-300 cursor-not-allowed' 
                    : 'text-gray-700 border-gray-300 hover:bg-gray-50'
                }`}
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default Jobs;
