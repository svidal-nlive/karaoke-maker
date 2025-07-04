import React, { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDropzone } from 'react-dropzone';
import { uploadFile } from '../api/upload';

const Upload: React.FC = () => {
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  
  const navigate = useNavigate();
  
  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    if (acceptedFiles.length === 0) return;
    
    const file = acceptedFiles[0];
    
    // Only accept audio files
    if (!file.type.startsWith('audio/')) {
      setError('Please upload an audio file (MP3, WAV, FLAC, etc.)');
      return;
    }
    
    try {
      setError(null);
      setSuccessMessage(null);
      setUploading(true);
      setUploadProgress(0);
      
      // Upload the file
      const result = await uploadFile(file, (progress) => {
        setUploadProgress(Math.round(progress));
      });
      
      setSuccessMessage(`Successfully uploaded ${file.name}! Job ID: ${result.jobId}`);
      
      // Redirect to job details after 2 seconds
      setTimeout(() => {
        navigate(`/jobs/${result.jobId}`);
      }, 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to upload file. Please try again.');
    } finally {
      setUploading(false);
    }
  }, [navigate]);
  
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'audio/*': ['.mp3', '.wav', '.flac', '.aac', '.m4a', '.ogg']
    },
    maxFiles: 1,
    disabled: uploading
  });
  
  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-6">Upload Audio File</h1>
      
      <div className="bg-white rounded-lg shadow p-6">
        <div className="mb-6">
          <p className="text-gray-700 mb-4">
            Upload an audio file to create a karaoke version. We'll separate the vocals from the music.
          </p>
          <p className="text-gray-700 mb-4">
            Supported formats: MP3, WAV, FLAC, AAC, M4A, OGG
          </p>
        </div>
        
        {error && (
          <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative mb-6" role="alert">
            <span className="block sm:inline">{error}</span>
          </div>
        )}
        
        {successMessage && (
          <div className="bg-green-100 border border-green-400 text-green-700 px-4 py-3 rounded relative mb-6" role="alert">
            <span className="block sm:inline">{successMessage}</span>
          </div>
        )}
        
        <div
          {...getRootProps()}
          className={`
            border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition
            ${isDragActive ? 'border-indigo-500 bg-indigo-50' : 'border-gray-300 hover:border-indigo-500'}
            ${uploading ? 'opacity-50 cursor-not-allowed' : ''}
          `}
        >
          <input {...getInputProps()} />
          
          {uploading ? (
            <div>
              <div className="mb-3 text-gray-700">Uploading... {uploadProgress}%</div>
              <div className="w-full bg-gray-200 rounded-full h-2.5">
                <div
                  className="bg-indigo-600 h-2.5 rounded-full"
                  style={{ width: `${uploadProgress}%` }}
                ></div>
              </div>
            </div>
          ) : isDragActive ? (
            <p className="text-indigo-500">Drop the audio file here...</p>
          ) : (
            <div>
              <svg className="mx-auto h-12 w-12 text-gray-400" stroke="currentColor" fill="none" viewBox="0 0 48 48" aria-hidden="true">
                <path d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <p className="mt-2 text-gray-700">
                Drag and drop an audio file here, or <span className="text-indigo-500">click to select a file</span>
              </p>
              <p className="mt-1 text-sm text-gray-500">
                Maximum file size: 50MB
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Upload;
