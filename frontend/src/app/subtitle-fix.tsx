'use client';
import React, { useState } from 'react';
import { Upload, AlertCircle, Download, FileText } from 'lucide-react';

interface Analysis {
  statistics: {
    total_subtitles: number;
    avg_duration: number;
    avg_gap: number;
    avg_reading_speed: number;
    std_gap: number;
    std_reading_speed: number;
  };
  issues: string[];
}

const SubtitleAnalyzer: React.FC = () => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file && file.name.endsWith('.srt')) {
      setSelectedFile(file);
      setError(null);
      analyzeFile(file);
    } else {
      setError('Please select a valid .srt file');
      setSelectedFile(null);
    }
  };

  const analyzeFile = async (file: File) => {
    setIsLoading(true);
    setError(null);
    
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch('http://localhost:5000/api/analyze', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.error || 'Analysis failed');
      }

      const data = await response.json();
      setAnalysis(data as Analysis);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
      setAnalysis(null);
    } finally {
      setIsLoading(false);
    }
  };

  const handleFixSubtitles = async () => {
    if (!selectedFile) return;

    setIsLoading(true);
    setError(null);

    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
      const response = await fetch('http://localhost:5000/api/fix', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.error || 'Fix failed');
      }

      const contentDisposition = response.headers.get('Content-Disposition');
      const filename = contentDisposition
        ? contentDisposition.split('filename=')[1].replace(/['"]/g, '')
        : 'subtitles_fixed.srt';

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setIsLoading(false);
    }
  };

  const renderAnalysis = () => {
    if (!analysis) return null;

    const { statistics, issues } = analysis;

    return (
      <div className="mt-6 p-4 bg-gray-50 rounded-lg">
        <h3 className="text-lg font-semibold mb-4">Analysis Results</h3>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div className="p-3 bg-white rounded shadow">
            <p className="font-medium">Total Subtitles: {statistics.total_subtitles}</p>
            <p>Average Duration: {statistics.avg_duration.toFixed(2)}s</p>
            <p>Average Gap: {statistics.avg_gap.toFixed(2)}s</p>
          </div>
          <div className="p-3 bg-white rounded shadow">
            <p>Average Reading Speed: {statistics.avg_reading_speed.toFixed(2)} chars/s</p>
            <p>Standard Deviation (Gap): {statistics.std_gap.toFixed(2)}s</p>
            <p>Standard Deviation (Reading): {statistics.std_reading_speed.toFixed(2)} chars/s</p>
          </div>
        </div>

        {issues.length > 0 && (
          <div className="mt-4">
            <h4 className="font-medium mb-2">Issues Found:</h4>
            <ul className="list-disc list-inside">
              {issues.map((issue, index) => (
                <li key={index} className="text-red-600">{issue}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="text-center mb-8">
        <h1 className="text-3xl font-bold mb-2">Subtitle Analyzer & Fixer</h1>
        <p className="text-gray-600">Upload your SRT file to analyze and fix timing issues</p>
      </div>

      <div className="flex flex-col items-center justify-center p-6 border-2 border-dashed border-gray-300 rounded-lg bg-gray-50">
        <div className="mb-4">
          <label className="flex flex-col items-center px-4 py-2 bg-blue-500 text-white rounded-lg shadow-lg hover:bg-blue-600 cursor-pointer">
            <div className="flex items-center">
              <Upload className="w-5 h-5 mr-2" />
              <span>Select SRT File</span>
            </div>
            <input
              type="file"
              accept=".srt"
              onChange={handleFileSelect}
              className="hidden"
            />
          </label>
        </div>

        {selectedFile && (
          <div className="mt-4 flex items-center">
            <FileText className="w-5 h-5 mr-2" />
            <span>{selectedFile.name}</span>
          </div>
        )}
      </div>

      {error && (
        <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg flex items-start">
          <AlertCircle className="w-5 h-5 text-red-500 mr-2 flex-shrink-0 mt-0.5" />
          <p className="text-red-600">{error}</p>
        </div>
      )}

      {renderAnalysis()}

      {analysis && (
        <div className="mt-6 flex justify-center">
          <button
            onClick={handleFixSubtitles}
            disabled={isLoading}
            className="flex items-center px-6 py-3 bg-green-500 text-white rounded-lg shadow-lg hover:bg-green-600 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Download className="w-5 h-5 mr-2" />
            {isLoading ? 'Processing...' : 'Download Fixed Subtitles'}
          </button>
        </div>
      )}
    </div>
  );
};

export default SubtitleAnalyzer;