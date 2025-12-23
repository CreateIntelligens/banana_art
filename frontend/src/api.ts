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
  started_at?: string;
  completed_at?: string;
  source_images: UploadedImage[];
  aspect_ratio?: string;
}

export interface Template {
  id: number;
  name: string;
  prompt_template: string;
  created_at: string;
  reference_images: UploadedImage[];
  aspect_ratio: string;
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

export const deleteImage = async (id: number) => {
  const response = await api.delete(`/images/${id}`);
  return response.data;
};

export const generateContent = async (prompt: string, imageIds: number[] = [], aspectRatio: string = "1:1") => {
  const formData = new FormData();
  formData.append('prompt', prompt);
  imageIds.forEach(id => formData.append('image_ids', id.toString()));
  formData.append('aspect_ratio', aspectRatio);
  const response = await api.post<Generation>('/generate', formData);
  return response.data;
};

export const generateFromTemplate = async (templateId: number, imageIds: number[] = []) => {
    const formData = new FormData();
    formData.append('template_id', templateId.toString());
    imageIds.forEach(id => formData.append('image_ids', id.toString()));
    const response = await api.post<Generation>('/generations/from-template', formData);
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

// Template APIs
export const createTemplate = async (name: string, promptTemplate: string, referenceImageIds: number[], aspectRatio: string) => {
    const response = await api.post<Template>('/templates', {
        name,
        prompt_template: promptTemplate,
        reference_image_ids: referenceImageIds,
        aspect_ratio: aspectRatio,
    });
    return response.data;
};

export const updateTemplate = async (id: number, name: string, promptTemplate: string, referenceImageIds: number[], aspectRatio: string) => {
    const response = await api.put<Template>(`/templates/${id}`, {
        name,
        prompt_template: promptTemplate,
        reference_image_ids: referenceImageIds,
        aspect_ratio: aspectRatio,
    });
    return response.data;
};

export const getTemplates = async () => {
    const response = await api.get<Template[]>('/templates');
    return response.data;
};

export const deleteTemplate = async (id: number) => {
    const response = await api.delete(`/templates/${id}`);
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
