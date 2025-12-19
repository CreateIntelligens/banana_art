import axios from 'axios';

const api = axios.create({
  baseURL: '/api', // Proxy in vite.config.ts handles this
});

export interface UploadedImage {
  id: number;
  filename: string;
  filepath: string;
  upload_time: string;
}

export interface Generation {
  id: number;
  prompt: string;
  source_image_id: number | null;
  output_image_path: string | null;
  created_at: string;
  source_image?: UploadedImage | null;
}

export const uploadImage = async (file: File) => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await api.post<UploadedImage>('/upload', formData);
  return response.data;
};

export const getImages = async () => {
  const response = await api.get<UploadedImage[]>('/images');
  return response.data;
};

export const generateContent = async (prompt: string, imageId?: number | null, aspectRatio: string = "1:1") => {
  const formData = new FormData();
  formData.append('prompt', prompt);
  if (imageId) {
    formData.append('image_id', imageId.toString());
  }
  formData.append('aspect_ratio', aspectRatio);
  const response = await api.post<Generation>('/generate', formData);
  return response.data;
};

export const getHistory = async () => {
  const response = await api.get<Generation[]>('/history');
  return response.data;
};

export const getGeneration = async (id: number) => {
  const response = await api.get<Generation>(`/generations/${id}`);
  return response.data;
};

export const deleteGeneration = async (id: number) => {
  const response = await api.delete(`/generations/${id}`);
  return response.data;
};

export const sendLog = async (message: string, level: string = 'INFO') => {
  const timestamp = new Date().toISOString();
  console.log(`[${level}] ${timestamp}: ${message}`);
  try {
    await api.post('/client-log', { message, level, timestamp });
  } catch (e) {
    console.error("Failed to send log to backend", e);
  }
};
