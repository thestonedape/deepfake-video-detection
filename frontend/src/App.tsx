import { useEffect, useMemo, useState } from 'react';
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import {
  Alert,
  AppBar,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Container,
  Divider,
  LinearProgress,
  Stack,
  Toolbar,
  Typography,
} from '@mui/material';
import CloudUploadOutlinedIcon from '@mui/icons-material/CloudUploadOutlined';
import GppGoodOutlinedIcon from '@mui/icons-material/GppGoodOutlined';
import GppBadOutlinedIcon from '@mui/icons-material/GppBadOutlined';
import MovieOutlinedIcon from '@mui/icons-material/MovieOutlined';
import ShieldOutlinedIcon from '@mui/icons-material/ShieldOutlined';
import PsychologyOutlinedIcon from '@mui/icons-material/PsychologyOutlined';
import SpeedOutlinedIcon from '@mui/icons-material/SpeedOutlined';
import SecurityOutlinedIcon from '@mui/icons-material/SecurityOutlined';
import ArrowForwardRoundedIcon from '@mui/icons-material/ArrowForwardRounded';
import { submitVideo } from './jobs.mjs';

type PredictionResponse = {
  filename: string;
  predicted_label: 'fake' | 'real';
  confidence: number;
  probabilities: { fake: number; real: number };
  frame_count: number;
  sampled_frames: number;
};

const API_URL = import.meta.env.VITE_API_URL ?? 'https://deepfake-video-detection-486r.onrender.com';
const MAX_UPLOAD_BYTES = 100 * 1024 * 1024;

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function ProbabilityRow({ label, value, color }: { label: string; value: number | null; color: 'error' | 'success' }) {
  return (
    <Box>
      <Stack direction="row" sx={{ justifyContent: 'space-between', mb: 0.75 }}>
        <Typography variant="body2" color="text.secondary">{label}</Typography>
        <Typography variant="body2" sx={{ fontWeight: 700 }}>{value === null ? '--' : formatPercent(value)}</Typography>
      </Stack>
      <LinearProgress variant="determinate" color={color} value={value === null ? 0 : value * 100} />
    </Box>
  );
}

function Nav() {
  const location = useLocation();
  const activePath = location.pathname;
  const items = [
    ['/', 'Home'],
    ['/analyze', 'Analyze'],
    ['/how-it-works', 'How it works'],
  ] as const;

  return (
    <AppBar position="sticky" color="transparent" elevation={0} sx={{ backdropFilter: 'blur(18px)', borderBottom: '1px solid rgba(148,163,184,.12)' }}>
      <Toolbar sx={{ gap: 2 }}>
        <Stack component={Link} to="/" direction="row" spacing={1.25} sx={{ alignItems: 'center', flexGrow: 1, cursor: 'pointer', color: 'inherit', textDecoration: 'none' }}>
          <ShieldOutlinedIcon color="primary" />
          <Typography sx={{ fontWeight: 800, letterSpacing: '-0.03em' }}>VeriFrame</Typography>
        </Stack>
        {items.map(([to, label]) => (
          <Button key={to} component={Link} to={to} color={activePath === to ? 'primary' : 'inherit'}>
            {label}
          </Button>
        ))}
      </Toolbar>
    </AppBar>
  );
}

function Home() {
  const navigate = useNavigate();
  return (
    <Container maxWidth="lg" sx={{ py: { xs: 7, md: 12 } }}>
      <Box sx={{ display: 'grid', gap: 6, gridTemplateColumns: { xs: '1fr', md: '1.1fr .9fr' }, alignItems: 'center' }}>
        <Stack spacing={3}>
          <Chip icon={<ShieldOutlinedIcon />} label="AI media verification" color="primary" variant="outlined" sx={{ alignSelf: 'flex-start' }} />
          <Typography variant="h1" sx={{ maxWidth: 760 }}>
            Check whether a video shows signs of AI manipulation.
          </Typography>
          <Typography color="text.secondary" sx={{ fontSize: { xs: '1rem', md: '1.14rem' }, maxWidth: 650 }}>
            Upload a clip, let the model sample key frames, and get a clear real-vs-fake probability breakdown with supporting metadata.
          </Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
            <Button variant="contained" size="large" onClick={() => navigate('/analyze')} endIcon={<ArrowForwardRoundedIcon />}>Analyze a video</Button>
            <Button variant="outlined" size="large" onClick={() => navigate('/how-it-works')}>See how detection works</Button>
          </Stack>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={3} sx={{ pt: 2 }}>
            {[
              ['10', 'sampled frames'],
              ['100 MB', 'upload limit'],
              ['Async', 'job processing'],
            ].map(([value, label]) => (
              <Box key={label}>
                <Typography variant="h2">{value}</Typography>
                <Typography variant="body2" color="text.secondary">{label}</Typography>
              </Box>
            ))}
          </Stack>
        </Stack>
        <Card sx={{ p: { xs: 1, md: 2 }, background: 'linear-gradient(145deg, rgba(124,140,248,.15), rgba(18,26,46,.88))' }}>
          <CardContent sx={{ p: { xs: 2.5, md: 4 } }}>
            <Stack spacing={3}>
              <Typography variant="overline" color="text.secondary">What you get</Typography>
              {[
                [<PsychologyOutlinedIcon color="primary" />, 'Model verdict', 'Real or fake classification with calibrated confidence.'],
                [<SpeedOutlinedIcon color="secondary" />, 'Readable probabilities', 'Separate fake and real scores, not just a binary label.'],
                [<SecurityOutlinedIcon color="primary" />, 'Private job access', 'Uploads are handled through token-protected asynchronous jobs.'],
              ].map(([icon, title, copy]) => (
                <Stack key={String(title)} direction="row" spacing={2}>
                  <Box>{icon}</Box>
                  <Box>
                    <Typography sx={{ fontWeight: 700 }}>{title}</Typography>
                    <Typography variant="body2" color="text.secondary">{copy}</Typography>
                  </Box>
                </Stack>
              ))}
            </Stack>
          </CardContent>
        </Card>
      </Box>
    </Container>
  );
}

function About() {
  const navigate = useNavigate();
  return (
    <Container maxWidth="md" sx={{ py: { xs: 6, md: 10 } }}>
      <Stack spacing={4}>
        <Box>
          <Typography variant="overline" color="primary.main">Detection pipeline</Typography>
          <Typography variant="h1" sx={{ mt: 1, mb: 2 }}>How the scanner reaches a verdict.</Typography>
          <Typography color="text.secondary">
            The system does not inspect every frame. It validates the video, samples representative frames, preprocesses them, runs inference through the saved PyTorch model, and averages frame-level outputs into a video-level result.
          </Typography>
        </Box>
        <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', sm: 'repeat(2,1fr)' } }}>
          {[
            ['01', 'Validate upload', 'The API checks size, type, signature, decodability and resource limits before inference.'],
            ['02', 'Sample frames', 'Ten frames are selected across the video timeline for efficient analysis.'],
            ['03', 'Run model inference', 'The EfficientNet-based PyTorch checkpoint evaluates sampled visual evidence.'],
            ['04', 'Aggregate the result', 'Frame probabilities are averaged into the final real/fake confidence shown in the UI.'],
          ].map(([num, title, copy]) => (
            <Card key={num}>
              <CardContent sx={{ p: 3 }}>
                <Typography variant="overline" color="primary.main">{num}</Typography>
                <Typography variant="h2" sx={{ my: 1 }}>{title}</Typography>
                <Typography variant="body2" color="text.secondary">{copy}</Typography>
              </CardContent>
            </Card>
          ))}
        </Box>
        <Alert severity="info">
          A model confidence score is evidence from this detector, not definitive proof of authenticity. Treat borderline results as a reason for further verification.
        </Alert>
        <Button variant="contained" size="large" onClick={() => navigate('/analyze')} sx={{ alignSelf: 'flex-start' }}>Open analyzer</Button>
      </Stack>
    </Container>
  );
}

function Analyze() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [prediction, setPrediction] = useState<PredictionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [jobStatus, setJobStatus] = useState('');

  useEffect(() => {
    if (!selectedFile) {
      setPreviewUrl(null);
      return;
    }
    const nextUrl = URL.createObjectURL(selectedFile);
    setPreviewUrl(nextUrl);
    return () => URL.revokeObjectURL(nextUrl);
  }, [selectedFile]);

  const isFake = prediction?.predicted_label === 'fake';
  const verdictLabel = useMemo(() => {
    if (!prediction) return 'Awaiting analysis';
    return isFake ? 'Likely manipulated' : 'Likely authentic';
  }, [prediction, isFake]);

  function handleFileChange(file: File | null) {
    setPrediction(null);
    setError(null);
    if (file && file.size > MAX_UPLOAD_BYTES) {
      setSelectedFile(null);
      setError('File exceeds the 100 MB upload limit.');
      return;
    }
    setSelectedFile(file);
  }

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
      setJobStatus('Waking the service and uploading your video…');
      const result = await submitVideo(API_URL, formData, setJobStatus);
      setPrediction({ filename: selectedFile.name, ...result });
    } catch (submissionError) {
      setError(submissionError instanceof Error ? submissionError.message : 'Unexpected error.');
    } finally {
      setLoading(false);
      setJobStatus('');
    }
  }

  return (
    <Container maxWidth="lg" sx={{ py: { xs: 5, md: 8 } }}>
      <Stack spacing={4}>
        <Box>
          <Typography variant="overline" color="primary.main">Analyzer workspace</Typography>
          <Typography variant="h1" sx={{ mt: 1 }}>Upload once. Get a focused verdict.</Typography>
          <Typography color="text.secondary" sx={{ mt: 1, maxWidth: 680 }}>
            The analysis runs as a background job, so slower cold starts or queued requests do not block the interface.
          </Typography>
        </Box>

        {loading && jobStatus && <Alert severity="info" icon={<CircularProgress size={18} />}>{jobStatus}</Alert>}

        <Box sx={{ display: 'grid', gap: 3, gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' } }}>
          <Card>
            <CardContent component="form" onSubmit={handleSubmit} sx={{ p: 3 }}>
              <Stack spacing={2.5}>
                <Box component="label" sx={{
                  display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                  gap: 1.25, px: 3, py: 7, borderRadius: 3, border: '1.5px dashed',
                  borderColor: selectedFile ? 'primary.main' : 'divider', cursor: 'pointer', textAlign: 'center',
                  backgroundColor: selectedFile ? 'rgba(124,140,248,.06)' : 'transparent',
                  '&:hover': { borderColor: 'primary.main', backgroundColor: 'rgba(124,140,248,.06)' },
                }}>
                  <input type="file" accept="video/*" hidden onChange={(e) => handleFileChange(e.target.files?.[0] ?? null)} />
                  <CloudUploadOutlinedIcon color={selectedFile ? 'primary' : 'disabled'} sx={{ fontSize: 48 }} />
                  <Typography sx={{ fontWeight: 700 }}>{selectedFile ? selectedFile.name : 'Drop a video or click to browse'}</Typography>
                  <Typography variant="body2" color="text.secondary">MP4, MOV, WEBM, AVI · up to 100 MB</Typography>
                </Box>
                <Button type="submit" variant="contained" size="large" disabled={!selectedFile || loading} startIcon={loading ? <CircularProgress size={18} color="inherit" /> : <MovieOutlinedIcon />}>
                  {loading ? 'Analyzing…' : 'Run analysis'}
                </Button>
                {error && <Alert severity="error">{error}</Alert>}
              </Stack>
            </CardContent>
          </Card>

          <Card>
            <CardContent sx={{ p: 3 }}>
              <Box sx={{ minHeight: 320, borderRadius: 3, overflow: 'hidden', bgcolor: 'rgba(2,6,23,.7)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                {previewUrl ? (
                  <Box component="video" src={previewUrl} controls sx={{ width: '100%', display: 'block' }} />
                ) : (
                  <Stack spacing={0.75} sx={{ alignItems: 'center', p: 3, textAlign: 'center' }}>
                    <MovieOutlinedIcon sx={{ fontSize: 42, color: 'text.disabled' }} />
                    <Typography sx={{ fontWeight: 700 }}>Preview area</Typography>
                    <Typography variant="body2" color="text.secondary">Choose a clip to inspect it before upload.</Typography>
                  </Stack>
                )}
              </Box>
            </CardContent>
          </Card>
        </Box>

        <Card sx={{ borderColor: prediction ? (isFake ? 'error.main' : 'success.main') : undefined }}>
          <CardContent sx={{ p: { xs: 3, md: 4 } }}>
            <Box sx={{ display: 'grid', gap: 4, gridTemplateColumns: { xs: '1fr', md: '.85fr 1.15fr' } }}>
              <Box>
                <Typography variant="overline" color="text.secondary">Verdict</Typography>
                <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', mt: 1 }}>
                  {prediction && (isFake ? <GppBadOutlinedIcon color="error" /> : <GppGoodOutlinedIcon color="success" />)}
                  <Typography variant="h2">{verdictLabel}</Typography>
                </Stack>
                <Typography color="text.secondary" sx={{ mt: 1.5 }}>
                  {prediction
                    ? `${formatPercent(prediction.confidence)} confidence across ${prediction.sampled_frames} sampled frames from ${prediction.filename}.`
                    : 'Results will appear here after the analysis job completes.'}
                </Typography>
              </Box>
              <Stack spacing={2.5}>
                <ProbabilityRow label="Manipulated / fake" value={prediction ? prediction.probabilities.fake : null} color="error" />
                <ProbabilityRow label="Authentic / real" value={prediction ? prediction.probabilities.real : null} color="success" />
                <Divider />
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} divider={<Divider orientation="vertical" flexItem />}>
                  <Box sx={{ flex: 1 }}>
                    <Typography variant="caption" color="text.secondary">Frames read</Typography>
                    <Typography sx={{ fontWeight: 700 }}>{prediction?.frame_count ?? '--'}</Typography>
                  </Box>
                  <Box sx={{ flex: 1 }}>
                    <Typography variant="caption" color="text.secondary">Frames sampled</Typography>
                    <Typography sx={{ fontWeight: 700 }}>{prediction?.sampled_frames ?? '--'}</Typography>
                  </Box>
                  <Box sx={{ flex: 1 }}>
                    <Typography variant="caption" color="text.secondary">Processing</Typography>
                    <Typography sx={{ fontWeight: 700 }}>Async job</Typography>
                  </Box>
                </Stack>
              </Stack>
            </Box>
          </CardContent>
        </Card>
      </Stack>
    </Container>
  );
}

export default function App() {
  return (
    <Box sx={{
      minHeight: '100vh',
      background: 'radial-gradient(circle at 15% 0%, rgba(124,140,248,.15), transparent 38%), radial-gradient(circle at 85% 85%, rgba(77,208,177,.09), transparent 34%), #0b1120',
    }}>
      <Nav />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/analyze" element={<Analyze />} />
        <Route path="/how-it-works" element={<About />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Box>
  );
}
