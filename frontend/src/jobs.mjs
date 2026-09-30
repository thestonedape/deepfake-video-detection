const states = new Set(['queued', 'processing', 'completed', 'failed']);

export async function submitVideo(apiUrl, formData, onStatus, options = {}) {
  const request = options.fetch || fetch;
  const now = options.now || Date.now;
  const sleep = options.sleep || (ms => new Promise(resolve => setTimeout(resolve, ms)));
  const acceptedResponse = await request(`${apiUrl}/jobs`, {
    method: 'POST', body: formData, signal: AbortSignal.timeout(180_000),
  });
  if (!acceptedResponse.ok) {
    const payload = await acceptedResponse.json().catch(() => null);
    throw new Error(typeof payload?.detail === 'string' ? payload.detail : 'Video upload failed. Please try again later.');
  }
  const accepted = await acceptedResponse.json();
  if (typeof accepted.job_id !== 'string' || !accepted.job_id || typeof accepted.job_token !== 'string' || !accepted.job_token) {
    throw new Error('The service returned an invalid job.');
  }
  let job = accepted;
  const deadline = now() + 15 * 60_000;
  let delay = 1000;
  while (true) {
    if (!states.has(job.status)) throw new Error('The service returned an invalid job status.');
    if (job.status === 'failed') throw new Error('This video could not be analyzed. Try a shorter, playable clip.');
    if (job.status === 'completed') {
      const result = job.result;
      if (!result || !['fake', 'real'].includes(result.predicted_label) || !Number.isFinite(result.confidence) ||
          !Number.isFinite(result.probabilities?.fake) || !Number.isFinite(result.probabilities?.real)) {
        throw new Error('The service returned an invalid prediction.');
      }
      return result;
    }
    if (now() >= deadline) throw new Error('The job is taking longer than expected. Please try again later.');
    onStatus(job.status === 'processing' ? 'Analyzing your video…' : 'Your video is queued…');
    await sleep(delay);
    delay = Math.min(10_000, delay * 1.5);
    if (now() >= deadline) throw new Error('The job is taking longer than expected. Please try again later.');
    try {
      const response = await request(`${apiUrl}/jobs/${encodeURIComponent(accepted.job_id)}`, {
        headers: {'X-Job-Token': accepted.job_token}, signal: AbortSignal.timeout(30_000),
      });
      if (response.status >= 500) {onStatus('Waiting for the service to recover…'); continue;}
      if (!response.ok) throw new Error('Unable to retrieve this job.');
      job = await response.json();
    } catch (error) {
      if (error instanceof TypeError || (error instanceof DOMException && error.name === 'TimeoutError')) {
        onStatus('Reconnecting to the service…'); continue;
      }
      throw error;
    }
  }
}
