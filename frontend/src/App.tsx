import { useEffect, useState, type DragEvent, type FormEvent } from 'react';
import { submitVideo } from './jobs.mjs';
import './site.css';

type Route = '/' | '/analyze' | '/result' | '/how-it-works';
type Prediction = {
  filename: string;
  predicted_label: 'fake' | 'real';
  confidence: number;
  probabilities: { fake: number; real: number };
  frame_count: number;
  sampled_frames: number;
};

const API_URL = import.meta.env.VITE_API_URL ?? 'https://deepfake-video-detection-486r.onrender.com';
const MAX_BYTES = 100 * 1024 * 1024;
const pct = (value: number) => (value * 100).toFixed(1) + '%';
const navItems: { path: Route; label: string }[] = [
  { path: '/', label: 'Overview' },
  { path: '/analyze', label: 'Analyzer' },
  { path: '/how-it-works', label: 'Method' },
];

function routeFromLocation(): Route {
  const p = window.location.pathname;
  return p === '/analyze' || p === '/result' || p === '/how-it-works' ? p : '/';
}

function useRoute() {
  const [route, setRoute] = useState<Route>(routeFromLocation);
  useEffect(() => {
    const onPop = () => setRoute(routeFromLocation());
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);
  function go(path: Route) {
    if (path !== window.location.pathname) window.history.pushState({}, '', path);
    setRoute(path);
    window.scrollTo({ top: 0, behavior: 'instant' });
  }
  return { route, go };
}

function Header({ route, go }: { route: Route; go: (path: Route) => void }) {
  return (
    <header className="topbar">
      <div className="topbar-inner">
        <button className="wordmark" onClick={() => go('/')} aria-label="VeriFrame home">
          <span className="wordmark-symbol" aria-hidden="true"><i /><i /><i /><i /></span>
          <span>veriframe<span className="wordmark-period">.</span></span>
        </button>
        <nav className="navigation" aria-label="Main navigation">
          {navItems.map((item) => (
            <button key={item.path} className={route === item.path ? 'nav-active' : ''} onClick={() => go(item.path)} aria-current={route === item.path ? 'page' : undefined}>
              {item.label}
            </button>
          ))}
        </nav>
        <button className="header-action" onClick={() => go('/analyze')}>Open analyzer <span aria-hidden="true">↗</span></button>
      </div>
    </header>
  );
}

function Eyebrow({ children }: { children: React.ReactNode }) {
  return <p className="eyebrow"><span className="eyebrow-line" />{children}</p>;
}

function ScanArtwork() {
  return (
    <div className="scan-window" aria-label="Illustration of the ten-frame video analysis process">
      <div className="scan-header"><span>FRAME STUDY / 05—10</span><span className="scan-status"><i /> MODEL VIEW</span></div>
      <div className="scan-area">
        <div className="scan-rings"><span /><span /><span /></div>
        <div className="scan-cross scan-cross-a" /><div className="scan-cross scan-cross-b" />
        <div className="scan-axis scan-axis-x" /><div className="scan-axis scan-axis-y" />
        <span className="scan-corner scan-corner-tl" /><span className="scan-corner scan-corner-br" />
        <div className="scan-center">SPATIAL <b>×</b> FREQUENCY</div>
        <span className="scan-corner-text">EVIDENCE / MODEL INPUT</span>
      </div>
      <div className="scan-filmstrip">
        {Array.from({ length: 10 }, (_, i) => (
          <div key={i} className={i === 4 ? 'film-frame film-active' : 'film-frame'}>
            <span>{String(i + 1).padStart(2, '0')}</span>
          </div>
        ))}
      </div>
      <div className="scan-footer"><span>ILLUSTRATIVE MODEL PIPELINE</span><span>10 SAMPLED FRAMES</span></div>
    </div>
  );
}

function Home({ go }: { go: (path: Route) => void }) {
  return (
    <main>
      <section className="home-hero wrap">
        <div className="home-intro">
          <Eyebrow>VIDEO FORENSICS / RESEARCH PROTOTYPE</Eyebrow>
          <h1>Question<br />the <em>frame.</em></h1>
          <p className="hero-lead">A closer look at what a video might be hiding.</p>
          <p className="hero-description">Upload a clip. A spatial and frequency-based model examines sampled frames and returns a probability estimate—not a final judgment.</p>
          <div className="hero-actions">
            <button className="button-primary" onClick={() => go('/analyze')}>Analyze a video <span aria-hidden="true">↗</span></button>
            <button className="text-link" onClick={() => go('/how-it-works')}>Explore the method <span aria-hidden="true">↗</span></button>
          </div>
          <div className="hero-footnote"><span>01 / INPUT</span><span>02 / INFERENCE</span><span>03 / REVIEW</span></div>
        </div>
        <ScanArtwork />
      </section>
      <section className="capability-section">
        <div className="wrap">
          <div className="section-heading"><span className="eyebrow">WHAT IS UNDER THE HOOD</span><h2>Evidence, not answers.</h2></div>
          <div className="capability-grid">
            <div className="capability"><span className="cap-number">01</span><h3>10 frames</h3><p>Samples a clip across its timeline rather than reading every frame.</p></div>
            <div className="capability"><span className="cap-number">02</span><h3>Two signals</h3><p>Combines EfficientNet-B4 visual features with FFT-based features.</p></div>
            <div className="capability"><span className="cap-number">03</span><h3>One estimate</h3><p>Shows both class probabilities with the context needed to interpret them.</p></div>
          </div>
        </div>
      </section>
      <div className="wrap bottom-cta"><p>Have a clip worth examining?</p><button className="text-link" onClick={() => go('/analyze')}>Start an analysis <span aria-hidden="true">↗</span></button></div>
    </main>
  );
}

function ScoreBar({ label, value, selected }: { label: string; value: number; selected?: boolean }) {
  return (
    <div className="score-row">
      <div className="score-head"><span>{label}</span><strong>{pct(value)}</strong></div>
      <div className="score-track"><div className={selected ? 'score-fill selected' : 'score-fill'} style={{ width: pct(value) }} /></div>
    </div>
  );
}

function Analyzer({ go }: { go: (path: Route) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [jobStatus, setJobStatus] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    if (!file) { setPreview(null); return; }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function selectFile(next: File | null) {
    setError('');
    if (next && next.size > MAX_BYTES) {
      setFile(null);
      setError('This file is over 100 MB. Choose a smaller video.');
      return;
    }
    setFile(next);
  }

  function drop(event: DragEvent<HTMLElement>) {
    event.preventDefault();
    setDragging(false);
    selectFile(event.dataTransfer.files?.[0] ?? null);
  }

  async function analyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || loading) return;
    setLoading(true);
    setError('');
    setJobStatus('Uploading video…');
    try {
      const data = new FormData();
      data.append('file', file);
      const result = await submitVideo(API_URL, data, setJobStatus);
      const completed: Prediction = { ...result, filename: file.name };
      sessionStorage.setItem('veriframe:lastResult', JSON.stringify(completed));
      go('/result');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed. Please try again.');
    } finally {
      setLoading(false);
      setJobStatus('');
    }
  }

  return (
    <main className="wrap workspace">
      <div className="page-topline"><Eyebrow>ANALYSIS / 01</Eyebrow><span>MAXIMUM FILE SIZE · 100 MB</span></div>
      <h1 className="page-title">Examine a clip.</h1>
      <p className="page-description">Choose a video to run through the detector. You can inspect it before uploading.</p>
      <div className="workspace-grid">
        <form onSubmit={analyze} className="workspace-panel">
          <div className="panel-kicker"><span>01 / VIDEO INPUT</span><span>LOCAL SELECTION</span></div>
          <label className={dragging ? 'dropzone dropzone-active' : 'dropzone'} onDragOver={(e) => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={drop}>
            <input type="file" accept="video/mp4,video/quicktime,video/webm,video/x-msvideo,video/x-matroska,.mkv" onChange={(e) => selectFile(e.target.files?.[0] ?? null)} disabled={loading} />
            <span className="upload-mark" aria-hidden="true">↥</span>
            <strong>{file ? file.name : 'Drop a video here'}</strong>
            <span>{file ? (file.size / 1024 / 1024).toFixed(1) + ' MB · click to replace' : 'or browse your files'}</span>
            <small>MP4 · MOV · WEBM · AVI · MKV</small>
          </label>
          <div className="workspace-note"><span>●</span> Only the selected file is sent when you choose “Run analysis”.</div>
          <button type="submit" className="button-primary action-full" disabled={!file || loading}>{loading ? 'Processing…' : 'Run analysis'} <span aria-hidden="true">{loading ? '◌' : '↗'}</span></button>
          {loading && <div className="task-status" role="status"><span className="busy-indicator" />{jobStatus || 'Working…'}<small>The service may need time to wake up or process earlier jobs.</small></div>}
          {error && <p className="form-error" role="alert">{error}</p>}
        </form>
        <div className="workspace-panel preview-panel">
          <div className="panel-kicker"><span>02 / PREVIEW</span><span>{file ? 'FILE READY' : 'AWAITING INPUT'}</span></div>
          <div className="video-stage">
            {preview ? <video controls src={preview} preload="metadata" aria-label="Selected video preview" /> : <div className="empty-preview"><div className="preview-cross" aria-hidden="true">+</div><strong>No clip selected</strong><span>Your video preview will appear here.</span></div>}
          </div>
          <div className="preview-bottom"><span>OUTPUT</span><p>Real / fake probabilities · sampled frame count · model confidence</p></div>
        </div>
      </div>
      <p className="disclaimer-inline">This research model can make mistakes. A score is not proof that a video is authentic or manipulated.</p>
    </main>
  );
}

function Result({ go }: { go: (path: Route) => void }) {
  const [copied, setCopied] = useState(false);
  const [result] = useState<Prediction | null>(() => {
    try {
      const stored = sessionStorage.getItem('veriframe:lastResult');
      return stored ? JSON.parse(stored) as Prediction : null;
    } catch { return null; }
  });
  if (!result) return <main className="wrap workspace"><Eyebrow>ANALYSIS / 02</Eyebrow><h1 className="page-title">No result yet.</h1><p className="page-description">Start with a video to see its model assessment.</p><button className="button-primary" onClick={() => go('/analyze')}>Open analyzer ↗</button></main>;

  const fake = result.predicted_label === 'fake';
  async function copy() {
    const summary = ['VeriFrame / model assessment', 'File: ' + result!.filename, 'Verdict: ' + (fake ? 'Likely manipulated' : 'Likely authentic'), 'Confidence: ' + pct(result!.confidence), 'Fake probability: ' + pct(result!.probabilities.fake), 'Real probability: ' + pct(result!.probabilities.real), 'Sampled frames: ' + result!.sampled_frames].join('\n');
    try { await navigator.clipboard.writeText(summary); setCopied(true); } catch { setCopied(false); }
  }
  return (
    <main className="wrap workspace">
      <div className="page-topline"><Eyebrow>ANALYSIS / RESULT</Eyebrow><span>MODEL OUTPUT · NOT VERIFIED FACT</span></div>
      <h1 className="page-title">The model's view.</h1>
      <p className="page-description">Results describe the model's prediction, not the video's provenance.</p>
      <div className="result-grid">
        <section className="result-verdict">
          <p className="panel-kicker">CLASSIFICATION / 01</p>
          <span className="verdict-marker">{fake ? '!' : '○'}</span>
          <h2>{fake ? 'Likely manipulated.' : 'Likely authentic.'}</h2>
          <p>Model confidence</p><strong className="confidence">{pct(result.confidence)}</strong>
          <span className="result-filename">{result.filename}</span>
        </section>
        <section className="result-data">
          <p className="panel-kicker">PROBABILITY DISTRIBUTION / 02</p>
          <ScoreBar label="Manipulated / fake" value={result.probabilities.fake} selected={fake} />
          <ScoreBar label="Authentic / real" value={result.probabilities.real} selected={!fake} />
          <div className="result-meta">
            <div><span>FRAMES READ</span><strong>{result.frame_count}</strong></div>
            <div><span>FRAMES SAMPLED</span><strong>{result.sampled_frames}</strong></div>
            <div><span>PROCESS</span><strong>ASYNC INFERENCE</strong></div>
          </div>
          <p className="result-caution"><strong>Interpret with care.</strong> Compression, lighting, and unseen manipulation methods can affect the result. Do not treat this score as definitive proof.</p>
        </section>
      </div>
      <div className="result-actions"><button className="button-primary" onClick={() => go('/analyze')}>Analyze another <span>↗</span></button><button className="button-outline" onClick={copy}>{copied ? 'Copied ✓' : 'Copy assessment ↗'}</button><button className="text-link" onClick={() => go('/how-it-works')}>Read the method ↗</button></div>
    </main>
  );
}

const method = [
  ['01', 'Inspect', 'The service checks the upload format, size and whether the video can be decoded.'],
  ['02', 'Sample', 'Ten frames are selected across the clip and resized to the model input.'],
  ['03', 'Evaluate', 'EfficientNet-B4 spatial features are combined with frequency-domain features.'],
  ['04', 'Estimate', 'Per-frame predictions are averaged to produce the displayed video-level scores.'],
];
function Method({ go }: { go: (path: Route) => void }) {
  return (
    <main className="wrap workspace method-page">
      <Eyebrow>INSIDE THE SYSTEM</Eyebrow>
      <h1 className="page-title">No magic.<br /><em>Just a model.</em></h1>
      <p className="page-description">A four-step look at how a video becomes a probability estimate.</p>
      <div className="method-list">
        {method.map(([n, title, description]) => <div className="method-row" key={n}><span>{n}</span><h2>{title}</h2><p>{description}</p><span aria-hidden="true">↗</span></div>)}
      </div>
      <div className="method-disclaimer"><span>IMPORTANT / LIMITATION</span><p>A classification is evidence from this model, not a forensic certification. Confirm consequential claims with independent checks and original-source provenance.</p></div>
      <div className="result-actions"><button className="button-primary" onClick={() => go('/analyze')}>Try the analyzer <span>↗</span></button></div>
    </main>
  );
}

export default function App() {
  const { route, go } = useRoute();
  return <div className="site-shell"><Header route={route} go={go} />{route === '/' && <Home go={go} />}{route === '/analyze' && <Analyzer go={go} />}{route === '/result' && <Result go={go} />}{route === '/how-it-works' && <Method go={go} />}<footer className="site-footer"><div className="wrap"><span>VERIFRAME / EXPERIMENTAL VIDEO ANALYSIS</span><span>BUILT FOR CRITICAL REVIEW, NOT CERTAINTY.</span></div></footer></div>;
}