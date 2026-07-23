import { useEffect, useMemo, useState } from 'react';

type PredictionResponse = {
  filename: string;
  predicted_label: 'fake' | 'real';
  confidence: number;
  probabilities: {
    fake: number;
    real: number;
  };
  frame_count: number;
  sampled_frames: number;
};

const API_URL =
  import.meta.env.VITE_API_URL ??
  'https://deepfake-video-detection-486r.onrender.com';

if (
  import.meta.env.PROD &&
  (API_URL.includes('localhost') || API_URL.includes('127.0.0.1'))
) {
  console.error(
    'Production build is using a local API URL. Set VITE_API_URL in Vercel.',
  );
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

export default function App() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [prediction, setPrediction] = useState<PredictionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!selectedFile) {
      setPreviewUrl(null);
      return;
    }

    const nextUrl = URL.createObjectURL(selectedFile);
    setPreviewUrl(nextUrl);
    return () => URL.revokeObjectURL(nextUrl);
  }, [selectedFile]);

  const predictedTone = useMemo(() => {
    if (!prediction) {
      return 'neutral';
    }
    return prediction.predicted_label === 'fake' ? 'alert' : 'positive';
  }, [prediction]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedFile) {
      setError('Choose a video file first.');
      return;
    }

    setLoading(true);
    setError(null);
    setPrediction(null);

    try {
      const formData = new FormData();
      formData.append('file', selectedFile);

      const response = await fetch(`${API_URL}/predict`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? 'Prediction request failed.');
      }

      const data = (await response.json()) as PredictionResponse;
      setPrediction(data);
    } catch (submissionError) {
      setError(submissionError instanceof Error ? submissionError.message : 'Unexpected error.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="app-shell">
      <section className="hero-card">
        <div className="hero-copy">
          <span className="eyebrow">Deepfake Video Scanner</span>
          <h1>Upload a clip and get a frame-level model verdict in seconds.</h1>
          <p>
            The backend samples 10 frames from your video, runs them through the saved PyTorch
            checkpoint, and averages the predictions at video level.
          </p>

          <form className="upload-form" onSubmit={handleSubmit}>
            <label className="file-dropzone">
              <input
                type="file"
                accept="video/*"
                onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
              />
              <span className="dropzone-title">
                {selectedFile ? selectedFile.name : 'Drop a video or click to browse'}
              </span>
              <span className="dropzone-subtitle">
                MP4, MOV, WEBM, and AVI work best for this demo.
              </span>
            </label>

            <div className="form-actions">
              <button type="submit" disabled={!selectedFile || loading}>
                {loading ? 'Analyzing...' : 'Run prediction'}
              </button>
              <span className="api-chip">API: {API_URL}</span>
            </div>
          </form>

          {error ? <div className="status-banner status-error">{error}</div> : null}
          {prediction ? (
            <div className={`status-banner status-${predictedTone}`}>
              <strong>{prediction.predicted_label.toUpperCase()}</strong> with {formatPercent(prediction.confidence)} confidence.
            </div>
          ) : null}
        </div>

        <div className="preview-panel">
          <div className="preview-frame">
            {previewUrl ? (
              <video src={previewUrl} controls />
            ) : (
              <div className="preview-placeholder">
                <p>Video preview appears here.</p>
                <span>Pick a file to inspect it before sending the request.</span>
              </div>
            )}
          </div>

          <div className="mini-stats">
            <div>
              <span>Backend</span>
              <strong>FastAPI</strong>
            </div>
            <div>
              <span>Checkpoint</span>
              <strong>best_model.pt</strong>
            </div>
            <div>
              <span>Sampling</span>
              <strong>10 frames</strong>
            </div>
          </div>
        </div>
      </section>

      <section className="results-grid">
        <article className="result-card">
          <span className="card-label">Prediction</span>
          <h2>{prediction ? prediction.predicted_label : 'Awaiting upload'}</h2>
          <p>
            {prediction
              ? `The model inspected ${prediction.sampled_frames} sampled frames from ${prediction.filename}.`
              : 'Submit a video to see the model verdict and probability breakdown.'}
          </p>
        </article>

        <article className="result-card">
          <span className="card-label">Probability</span>
          <div className="probability-stack">
            <div className="probability-row">
              <span>Fake</span>
              <strong>{prediction ? formatPercent(prediction.probabilities.fake) : '--'}</strong>
            </div>
            <div className="progress-track">
              <div
                className="progress-fill progress-fake"
                style={{ width: prediction ? formatPercent(prediction.probabilities.fake) : '0%' }}
              />
            </div>
            <div className="probability-row">
              <span>Real</span>
              <strong>{prediction ? formatPercent(prediction.probabilities.real) : '--'}</strong>
            </div>
            <div className="progress-track">
              <div
                className="progress-fill progress-real"
                style={{ width: prediction ? formatPercent(prediction.probabilities.real) : '0%' }}
              />
            </div>
          </div>
        </article>

        <article className="result-card">
          <span className="card-label">Metadata</span>
          <ul className="meta-list">
            <li>
              <span>Frames read</span>
              <strong>{prediction ? prediction.frame_count : '--'}</strong>
            </li>
            <li>
              <span>Frames sampled</span>
              <strong>{prediction ? prediction.sampled_frames : '--'}</strong>
            </li>
            <li>
              <span>API route</span>
              <strong>/predict</strong>
            </li>
          </ul>
        </article>
      </section>
    </main>
  );
}
