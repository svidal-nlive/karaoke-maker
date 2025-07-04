import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { fetchJobs } from '../api/jobs';

interface JobSummary {
  id: string;
  filename: string;
  status: string;
  createdAt: string;
}

const Dashboard: React.FC = () => {
  const [recentJobs, setRecentJobs] = useState<JobSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  
  const { user } = useAuth();
  const navigate = useNavigate();
  
  useEffect(() => {
    const loadJobs = async () => {
      try {
        setLoading(true);
        // Fetch just the recent jobs (limit to 5)
        const response = await fetchJobs({ limit: 5 });
        setRecentJobs(response.jobs);
      } catch (err) {
        setError('Failed to load recent jobs');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    
    loadJobs();
  }, []);
  
  const handleViewAllJobs = () => {
    navigate('/jobs');
  };
  
  const handleUpload = () => {
    navigate('/upload');
  };
  
  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-6">Dashboard</h1>
      
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold">Welcome, {user?.username}</h2>
          <button
            onClick={handleUpload}
            className="bg-indigo-600 text-white px-4 py-2 rounded hover:bg-indigo-700 transition"
          >
            Upload New Track
          </button>
        </div>
        <p className="text-gray-600">
          Create karaoke tracks by uploading audio files. Track the status of your jobs and manage your settings.
        </p>
      </div>
      
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold">Recent Jobs</h2>
          <button
            onClick={handleViewAllJobs}
            className="text-indigo-600 hover:text-indigo-800 transition"
          >
            View All
          </button>
        </div>
        
        {loading ? (
          <div className="text-center py-4">
            <p className="text-gray-500">Loading recent jobs...</p>
          </div>
        ) : error ? (
          <div className="bg-red-100 text-red-700 p-3 rounded">
            {error}
          </div>
        ) : recentJobs.length === 0 ? (
          <div className="text-center py-4">
            <p className="text-gray-500">No jobs found. Upload your first audio file to get started!</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Filename
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Created
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {recentJobs.map((job) => (
                  <tr key={job.id}>
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
                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                      <button 
                        onClick={() => navigate(`/jobs/${job.id}`)}
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
        )}
      </div>
    </div>
  );
};

export default Dashboard;
