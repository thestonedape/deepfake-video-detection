import { useEffect, useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import Container from '@mui/material/Container';
import Divider from '@mui/material/Divider';
import LinearProgress from '@mui/material/LinearProgress';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import CloudUploadOutlinedIcon from '@mui/icons-material/CloudUploadOutlined';
import GppGoodOutlinedIcon from '@mui/icons-material/GppGoodOutlined';
import GppBadOutlinedIcon from '@mui/icons-material/GppBadOutlined';
import MovieOutlinedIcon from '@mui/icons-material/MovieOutlined';
import ShieldOutlinedIcon from '@mui/icons-material/ShieldOutlined';

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

const MAX_UPLOAD_BYTES = 100 * 1024 * 1024;

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

function ProbabilityRow({
  label,
  value,
  color,
}: {
  label: string;
  value: number | null;
  color: 'error' | 'success';
}) {
  return (
    <Box>
      <Stack
        direction="row"
        sx={{ justifyContent: 'space-between', mb: 0.5 }}
      >
        <Typography variant="body2" color="text.secondary">
          {label}
        </Typography>
        <Typography variant="body2" sx={{ fontWeight: 600 }}>
          {value === null ? '--' : formatPercent(value)}
        </Typography>
      </Stack>
      <LinearProgress
        variant="determinate"
        color={color}
        value={value === null ? 0 : value * 100}
      />
    </Box>
  );
}

export default function App() {
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

  function handleFileChange(file: File | null) {
    setPrediction(null);
    setJobStatus('Waking the service and uploading your video…');
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

      const response = await fetch(`${API_URL}/jobs`, {
        method: 'POST',
        body: formData,
        signal: AbortSignal.timeout(180_000),
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? 'Prediction request failed.');
      }

      const accepted = await response.json();
      let job = accepted;
      const deadline = Date.now() + 15 * 60_000;
      let delay = 1000;
      while (job.status !== 'completed') {
        if (job.status === 'failed') throw new Error('This video could not be analyzed. Try a shorter, playable clip.');
        if (Date.now() >= deadline) throw new Error('The job is taking longer than expected. Please try again later.');
        setJobStatus(job.status === 'processing' ? 'Analyzing your video…' : 'Your video is queued…');
        await new Promise((resolve) => setTimeout(resolve, delay));
        delay = Math.min(10_000, delay * 1.5);
        try {
          const poll = await fetch(`${API_URL}/jobs/${accepted.job_id}`, {
            headers: { 'X-Job-Token': accepted.job_token },
            signal: AbortSignal.timeout(30_000),
          });
          if (poll.status >= 500) { setJobStatus('Waiting for the service to recover…'); continue; }
          if (!poll.ok) throw new Error('Unable to retrieve this job.');
          job = await poll.json();
        } catch (pollError) {
          if (pollError instanceof TypeError || (pollError instanceof DOMException && pollError.name === 'TimeoutError')) {
            setJobStatus('Reconnecting to the service…'); continue;
          }
          throw pollError;
        }
      }
      setPrediction({ filename: selectedFile.name, ...job.result });
    } catch (submissionError) {
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : 'Unexpected error.',
      );
    } finally {
      setLoading(false);
      setJobStatus('');
    }
  }

  const isFake = prediction?.predicted_label === 'fake';

  return (
    <Box
      sx={{
        minHeight: '100vh',
        background:
          'radial-gradient(circle at 15% 0%, rgba(124, 140, 248, 0.14), transparent 45%), radial-gradient(circle at 90% 100%, rgba(77, 208, 177, 0.10), transparent 40%)',
        py: { xs: 4, md: 8 },
      }}
    >
      <Container maxWidth="lg">
        <Stack spacing={4}>
          {loading && jobStatus && <Typography role="status" color="text.secondary">{jobStatus}</Typography>}
          <Stack spacing={1.5} sx={{ alignItems: 'flex-start' }}>
            <Chip
              icon={<ShieldOutlinedIcon />}
              label="Deepfake Video Scanner"
              color="primary"
              variant="outlined"
            />
            <Typography variant="h1">
              Upload a clip and get a frame-level model verdict in seconds.
            </Typography>
            <Typography
              variant="body1"
              color="text.secondary"
              sx={{ maxWidth: 560 }}
            >
              The backend samples 10 frames from your video, runs them through
              the saved PyTorch checkpoint, and averages the predictions at
              video level.
            </Typography>
          </Stack>

          <Box
            sx={{
              display: 'grid',
              gap: 3,
              gridTemplateColumns: { xs: '1fr', md: '1.1fr 0.9fr' },
              alignItems: 'stretch',
            }}
          >
            <Card>
              <CardContent
                component="form"
                onSubmit={handleSubmit}
                sx={{ display: 'flex', flexDirection: 'column', gap: 2.5, p: 3 }}
              >
                <Box
                  component="label"
                  sx={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 1,
                    px: 3,
                    py: 6,
                    borderRadius: 3,
                    border: '1.5px dashed',
                    borderColor: selectedFile ? 'primary.main' : 'divider',
                    cursor: 'pointer',
                    textAlign: 'center',
                    transition: 'border-color 120ms ease, background 120ms ease',
                    '&:hover': {
                      borderColor: 'primary.main',
                      backgroundColor: 'rgba(124, 140, 248, 0.06)',
                    },
                  }}
                >
                  <input
                    type="file"
                    accept="video/*"
                    hidden
                    onChange={(event) =>
                      handleFileChange(event.target.files?.[0] ?? null)
                    }
                  />
                  <CloudUploadOutlinedIcon
                    color={selectedFile ? 'primary' : 'disabled'}
                    sx={{ fontSize: 44 }}
                  />
                  <Typography sx={{ fontWeight: 600 }}>
                    {selectedFile
                      ? selectedFile.name
                      : 'Drop a video or click to browse'}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    MP4, MOV, WEBM, and AVI up to 100 MB.
                  </Typography>
                </Box>

                <Stack
                  direction={{ xs: 'column', sm: 'row' }}
                  spacing={2}
                  sx={{ alignItems: { xs: 'stretch', sm: 'center' } }}
                >
                  <Button
                    type="submit"
                    variant="contained"
                    size="large"
                    disabled={!selectedFile || loading}
                    startIcon={
                      loading ? (
                        <CircularProgress size={18} color="inherit" />
                      ) : (
                        <MovieOutlinedIcon />
                      )
                    }
                  >
                    {loading ? 'Analyzing…' : 'Run prediction'}
                  </Button>
                  <Chip
                    label={`API: ${API_URL}`}
                    size="small"
                    variant="outlined"
                    sx={{ maxWidth: '100%' }}
                  />
                </Stack>

                {error ? <Alert severity="error">{error}</Alert> : null}
                {prediction ? (
                  <Alert
                    severity={isFake ? 'error' : 'success'}
                    icon={
                      isFake ? <GppBadOutlinedIcon /> : <GppGoodOutlinedIcon />
                    }
                  >
                    <strong>{prediction.predicted_label.toUpperCase()}</strong>{' '}
                    with {formatPercent(prediction.confidence)} confidence.
                  </Alert>
                ) : null}
              </CardContent>
            </Card>

            <Card>
              <CardContent
                sx={{ display: 'flex', flexDirection: 'column', gap: 2, p: 3 }}
              >
                <Box
                  sx={{
                    flexGrow: 1,
                    minHeight: 240,
                    borderRadius: 3,
                    overflow: 'hidden',
                    backgroundColor: 'rgba(2, 6, 23, 0.6)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  {previewUrl ? (
                    <Box
                      component="video"
                      src={previewUrl}
                      controls
                      sx={{ width: '100%', height: '100%', display: 'block' }}
                    />
                  ) : (
                    <Stack spacing={0.5} sx={{ alignItems: 'center', p: 3 }}>
                      <Typography sx={{ fontWeight: 600 }}>
                        Video preview appears here.
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        Pick a file to inspect it before sending the request.
                      </Typography>
                    </Stack>
                  )}
                </Box>

                <Divider />

                <Stack
                  direction="row"
                  spacing={2}
                  sx={{ justifyContent: 'space-around' }}
                >
                  {[
                    ['Backend', 'FastAPI'],
                    ['Checkpoint', 'best_model.pt'],
                    ['Sampling', '10 frames'],
                  ].map(([label, value]) => (
                    <Stack
                      key={label}
                      spacing={0.25}
                      sx={{ alignItems: 'center' }}
                    >
                      <Typography variant="caption" color="text.secondary">
                        {label}
                      </Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {value}
                      </Typography>
                    </Stack>
                  ))}
                </Stack>
              </CardContent>
            </Card>
          </Box>

          <Box
            sx={{
              display: 'grid',
              gap: 3,
              gridTemplateColumns: { xs: '1fr', md: 'repeat(3, 1fr)' },
            }}
          >
            <Card>
              <CardContent sx={{ p: 3 }}>
                <Typography variant="overline" color="text.secondary">
                  Prediction
                </Typography>
                <Typography variant="h2" sx={{ mt: 1, mb: 1 }}>
                  {prediction ? prediction.predicted_label : 'Awaiting upload'}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {prediction
                    ? `The model inspected ${prediction.sampled_frames} sampled frames from ${prediction.filename}.`
                    : 'Submit a video to see the model verdict and probability breakdown.'}
                </Typography>
              </CardContent>
            </Card>

            <Card>
              <CardContent sx={{ p: 3 }}>
                <Typography variant="overline" color="text.secondary">
                  Probability
                </Typography>
                <Stack spacing={2} sx={{ mt: 2 }}>
                  <ProbabilityRow
                    label="Fake"
                    value={prediction ? prediction.probabilities.fake : null}
                    color="error"
                  />
                  <ProbabilityRow
                    label="Real"
                    value={prediction ? prediction.probabilities.real : null}
                    color="success"
                  />
                </Stack>
              </CardContent>
            </Card>

            <Card>
              <CardContent sx={{ p: 3 }}>
                <Typography variant="overline" color="text.secondary">
                  Metadata
                </Typography>
                <Stack spacing={1.5} sx={{ mt: 2 }} divider={<Divider />}>
                  {[
                    ['Frames read', prediction ? prediction.frame_count : '--'],
                    [
                      'Frames sampled',
                      prediction ? prediction.sampled_frames : '--',
                    ],
                    ['API route', '/predict'],
                  ].map(([label, value]) => (
                    <Stack
                      key={String(label)}
                      direction="row"
                      sx={{ justifyContent: 'space-between' }}
                    >
                      <Typography variant="body2" color="text.secondary">
                        {label}
                      </Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {value}
                      </Typography>
                    </Stack>
                  ))}
                </Stack>
              </CardContent>
            </Card>
          </Box>
        </Stack>
      </Container>
    </Box>
  );
}
