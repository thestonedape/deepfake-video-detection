export interface VideoResult {
  predicted_label: 'fake' | 'real'; confidence: number;
  probabilities: {fake: number; real: number}; frame_count: number; sampled_frames: number;
}
export function submitVideo(apiUrl: string, formData: FormData, onStatus: (status: string) => void): Promise<VideoResult>;
