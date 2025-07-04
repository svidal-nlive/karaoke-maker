import React, { useEffect, useState } from 'react';
import { getSettings, updateSettings } from '../api/settings';

interface SettingsState {
  splitterType: string;
  stems: number;
  stemTypes: string[];
  chunking: boolean;
  chunkLengthMs: number;
  cleanIntermediateFiles: boolean;
  maxRetries: number;
  retryDelay: number;
}

const Settings: React.FC = () => {
  const [settings, setSettings] = useState<SettingsState>({
    splitterType: 'SPLEETER',
    stems: 4,
    stemTypes: ['vocals', 'drums', 'bass', 'other'],
    chunking: false,
    chunkLengthMs: 240000,
    cleanIntermediateFiles: true,
    maxRetries: 3,
    retryDelay: 10
  });
  
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  
  useEffect(() => {
    const loadSettings = async () => {
      try {
        setLoading(true);
        const response = await getSettings();
        setSettings(response);
      } catch (err) {
        setError('Failed to load settings');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    
    loadSettings();
  }, []);
  
  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>
  ) => {
    const { name, value, type } = e.target;
    
    if (type === 'checkbox') {
      const checked = (e.target as HTMLInputElement).checked;
      setSettings(prev => ({
        ...prev,
        [name]: checked
      }));
    } else if (type === 'number') {
      setSettings(prev => ({
        ...prev,
        [name]: parseInt(value, 10)
      }));
    } else {
      setSettings(prev => ({
        ...prev,
        [name]: value
      }));
    }
  };
  
  const handleStemTypesChange = (type: string) => {
    setSettings(prev => {
      const stemTypes = [...prev.stemTypes];
      
      if (stemTypes.includes(type)) {
        // Remove the type if it exists
        return {
          ...prev,
          stemTypes: stemTypes.filter(t => t !== type)
        };
      } else {
        // Add the type if it doesn't exist
        return {
          ...prev,
          stemTypes: [...stemTypes, type]
        };
      }
    });
  };
  
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    try {
      setSaving(true);
      setError(null);
      setSuccessMessage(null);
      
      await updateSettings(settings);
      setSuccessMessage('Settings saved successfully!');
      
      // Clear success message after 5 seconds
      setTimeout(() => setSuccessMessage(null), 5000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save settings');
    } finally {
      setSaving(false);
    }
  };
  
  if (loading) {
    return (
      <div className="p-6">
        <h1 className="text-2xl font-bold mb-6">Settings</h1>
        <div className="text-center py-8">
          <p className="text-gray-500">Loading settings...</p>
        </div>
      </div>
    );
  }
  
  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-6">Settings</h1>
      
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
      
      <div className="bg-white rounded-lg shadow p-6">
        <form onSubmit={handleSubmit}>
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            {/* Splitter Type */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Splitter Type
              </label>
              <select
                name="splitterType"
                value={settings.splitterType}
                onChange={handleChange}
                className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
              >
                <option value="SPLEETER">Spleeter</option>
                <option value="DEMUCS" disabled>Demucs (Coming Soon)</option>
              </select>
              <p className="mt-1 text-sm text-gray-500">
                Select the audio separation algorithm to use
              </p>
            </div>
            
            {/* Number of Stems */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Number of Stems
              </label>
              <select
                name="stems"
                value={settings.stems}
                onChange={handleChange}
                className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
              >
                <option value={2}>2 (Vocals, Accompaniment)</option>
                <option value={4}>4 (Vocals, Drums, Bass, Other)</option>
                <option value={5}>5 (Vocals, Drums, Bass, Piano, Other)</option>
              </select>
              <p className="mt-1 text-sm text-gray-500">
                How many separate audio stems to extract
              </p>
            </div>
            
            {/* Stem Types */}
            <div className="md:col-span-2">
              <fieldset>
                <legend className="block text-sm font-medium text-gray-700 mb-2">
                  Stem Types to Keep
                </legend>
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                  <div className="flex items-start">
                    <div className="flex items-center h-5">
                      <input
                        type="checkbox"
                        id="vocals"
                        checked={settings.stemTypes.includes('vocals')}
                        onChange={() => handleStemTypesChange('vocals')}
                        className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                      />
                    </div>
                    <div className="ml-3 text-sm">
                      <label htmlFor="vocals" className="font-medium text-gray-700">Vocals</label>
                    </div>
                  </div>
                  <div className="flex items-start">
                    <div className="flex items-center h-5">
                      <input
                        type="checkbox"
                        id="drums"
                        checked={settings.stemTypes.includes('drums')}
                        onChange={() => handleStemTypesChange('drums')}
                        className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                      />
                    </div>
                    <div className="ml-3 text-sm">
                      <label htmlFor="drums" className="font-medium text-gray-700">Drums</label>
                    </div>
                  </div>
                  <div className="flex items-start">
                    <div className="flex items-center h-5">
                      <input
                        type="checkbox"
                        id="bass"
                        checked={settings.stemTypes.includes('bass')}
                        onChange={() => handleStemTypesChange('bass')}
                        className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                      />
                    </div>
                    <div className="ml-3 text-sm">
                      <label htmlFor="bass" className="font-medium text-gray-700">Bass</label>
                    </div>
                  </div>
                  <div className="flex items-start">
                    <div className="flex items-center h-5">
                      <input
                        type="checkbox"
                        id="other"
                        checked={settings.stemTypes.includes('other')}
                        onChange={() => handleStemTypesChange('other')}
                        className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                      />
                    </div>
                    <div className="ml-3 text-sm">
                      <label htmlFor="other" className="font-medium text-gray-700">Other</label>
                    </div>
                  </div>
                  <div className="flex items-start">
                    <div className="flex items-center h-5">
                      <input
                        type="checkbox"
                        id="piano"
                        checked={settings.stemTypes.includes('piano')}
                        onChange={() => handleStemTypesChange('piano')}
                        disabled={settings.stems < 5}
                        className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 disabled:opacity-50"
                      />
                    </div>
                    <div className="ml-3 text-sm">
                      <label htmlFor="piano" className={`font-medium ${settings.stems < 5 ? 'text-gray-400' : 'text-gray-700'}`}>
                        Piano (5-stem only)
                      </label>
                    </div>
                  </div>
                  <div className="flex items-start">
                    <div className="flex items-center h-5">
                      <input
                        type="checkbox"
                        id="accompaniment"
                        checked={settings.stemTypes.includes('accompaniment')}
                        onChange={() => handleStemTypesChange('accompaniment')}
                        disabled={settings.stems !== 2}
                        className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 disabled:opacity-50"
                      />
                    </div>
                    <div className="ml-3 text-sm">
                      <label htmlFor="accompaniment" className={`font-medium ${settings.stems !== 2 ? 'text-gray-400' : 'text-gray-700'}`}>
                        Accompaniment (2-stem only)
                      </label>
                    </div>
                  </div>
                </div>
              </fieldset>
            </div>
            
            {/* Chunking Settings */}
            <div>
              <div className="flex items-start mb-4">
                <div className="flex items-center h-5">
                  <input
                    type="checkbox"
                    id="chunking"
                    name="chunking"
                    checked={settings.chunking}
                    onChange={handleChange}
                    className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                  />
                </div>
                <div className="ml-3 text-sm">
                  <label htmlFor="chunking" className="font-medium text-gray-700">Enable Chunking</label>
                  <p className="text-gray-500">Process large files in chunks to avoid memory issues</p>
                </div>
              </div>
              
              <div className={settings.chunking ? '' : 'opacity-50'}>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Chunk Length (ms)
                </label>
                <input
                  type="number"
                  name="chunkLengthMs"
                  value={settings.chunkLengthMs}
                  onChange={handleChange}
                  min={10000}
                  max={600000}
                  step={10000}
                  disabled={!settings.chunking}
                  className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                />
                <p className="mt-1 text-sm text-gray-500">
                  Length of each audio chunk in milliseconds (default: 240000 = 4 minutes)
                </p>
              </div>
            </div>
            
            {/* Cleanup Settings */}
            <div>
              <div className="flex items-start">
                <div className="flex items-center h-5">
                  <input
                    type="checkbox"
                    id="cleanIntermediateFiles"
                    name="cleanIntermediateFiles"
                    checked={settings.cleanIntermediateFiles}
                    onChange={handleChange}
                    className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                  />
                </div>
                <div className="ml-3 text-sm">
                  <label htmlFor="cleanIntermediateFiles" className="font-medium text-gray-700">Clean Intermediate Files</label>
                  <p className="text-gray-500">Delete temporary files after processing to save disk space</p>
                </div>
              </div>
            </div>
            
            {/* Retry Settings */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Max Retries
              </label>
              <input
                type="number"
                name="maxRetries"
                value={settings.maxRetries}
                onChange={handleChange}
                min={0}
                max={10}
                className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
              />
              <p className="mt-1 text-sm text-gray-500">
                Maximum number of retry attempts for failed operations
              </p>
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Retry Delay (seconds)
              </label>
              <input
                type="number"
                name="retryDelay"
                value={settings.retryDelay}
                onChange={handleChange}
                min={1}
                max={60}
                className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
              />
              <p className="mt-1 text-sm text-gray-500">
                Delay between retry attempts in seconds
              </p>
            </div>
          </div>
          
          <div className="mt-8 flex justify-end">
            <button
              type="submit"
              disabled={saving}
              className={`inline-flex items-center px-4 py-2 border border-transparent text-base font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 ${saving ? 'opacity-70 cursor-not-allowed' : ''}`}
            >
              {saving ? 'Saving...' : 'Save Settings'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default Settings;
