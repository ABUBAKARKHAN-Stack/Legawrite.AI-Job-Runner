'use client';

import { useState, useEffect } from 'react';

export default function JobRunner() {
  const [prompt, setPrompt] = useState('');
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<string>('idle');
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt) return;

    setJobId(null);
    setStatus('submitting');
    setResult(null);
    setError(null);

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt }),
      });

      if (!response.ok) throw new Error('Failed to submit job');

      const data = await response.json();
      setJobId(data.job_id);
      setStatus(data.status);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      setStatus('error');
    }
  };

  useEffect(() => {
    if (!jobId) return;

    const apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    const eventSource = new EventSource(`${apiBase}/api/jobs/${jobId}/stream`);

    eventSource.addEventListener('status', (event) => {
      const data = JSON.parse(event.data);
      setStatus(data.status);
    });

    eventSource.addEventListener('result', (event) => {
      const data = JSON.parse(event.data);
      setResult(data.data);
      setStatus('completed');
      eventSource.close();
    });

    // Handle FAILED state published by the worker
    eventSource.addEventListener('error', (event: MessageEvent) => {
      const data = JSON.parse(event.data);
      setError(data.error ?? 'Job failed');
      setStatus('failed');
      eventSource.close();
    });

    eventSource.onerror = () => {
      // Network-level SSE error — EventSource will auto-reconnect.
      console.error('SSE connection error — will reconnect automatically');
    };

    return () => {
      eventSource.close();
    };
  }, [jobId]);

  const isActive = status !== 'idle' && status !== 'completed' && status !== 'failed' && status !== 'error';

  return (
    <div style={{ padding: '2rem', maxWidth: '600px', margin: '0 auto', fontFamily: 'sans-serif' }}>
      <h1>Legawrite.AI Job Runner</h1>

      <form onSubmit={handleSubmit} style={{ marginBottom: '2rem' }}>
        <div style={{ marginBottom: '1rem' }}>
          <label htmlFor="prompt" style={{ display: 'block', marginBottom: '0.5rem' }}>Enter Prompt:</label>
          <textarea
            id="prompt"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            disabled={isActive}
            style={{ width: '100%', minHeight: '100px', padding: '0.5rem' }}
            placeholder="Type something here..."
          />
        </div>
        <button
          type="submit"
          disabled={isActive}
          style={{ padding: '0.5rem 1rem', cursor: 'pointer' }}
        >
          Run Job
        </button>
      </form>

      <div style={{ border: '1px solid #ccc', padding: '1rem', borderRadius: '4px' }}>
        <h3>Job Status: <span style={{ color: status === 'completed' ? 'green' : status === 'failed' ? 'red' : 'blue' }}>{status.toUpperCase()}</span></h3>

        {jobId && <p><small>Job ID: {jobId}</small></p>}

        {status === 'processing' && (
          <p><em>Processing... please wait (takes ~90 seconds)</em></p>
        )}

        {result && (
          <div style={{ marginTop: '1rem', backgroundColor: '#f9f9f9', padding: '1rem' }}>
            <strong>Result:</strong>
            <p>{result}</p>
          </div>
        )}

        {error && (
          <p style={{ color: 'red' }}>Error: {error}</p>
        )}
      </div>
    </div>
  );
}
