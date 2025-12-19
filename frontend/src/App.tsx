import React, { useState, useEffect, useRef } from 'react';
import { Upload, Image as ImageIcon, Send, History, RefreshCcw, Terminal, Trash2, Download, X, Maximize2, ZoomIn, Ratio, CheckCircle2, LayoutTemplate, Plus, Wand2, Edit } from 'lucide-react';
import * as api from './api';

// Helper Component for Result Display
const ResultDisplay = ({ generation, onZoom, copyToClipboard }: { generation: api.Generation, onZoom: () => void, copyToClipboard: (text: string) => void }) => {
    if (!generation || !generation.output_image_path) return null; // Ensure generation and path exist
    
    const promptToCopy = generation.prompt;

    return (
        <div className="w-full bg-gray-50 p-4 rounded-xl border border-gray-200 flex flex-col items-center">
            {generation.output_image_path === 'error' ? (
                <div className="text-red-500 py-10 flex flex-col items-center gap-2">
                    <X size={40} />
                    <span>Generation Failed</span>
                </div>
            ) : generation.output_image_path?.endsWith('.txt') ? (
                <div className="p-6 bg-white border rounded w-full font-mono text-sm whitespace-pre-wrap">
                    Result saved as text. Check Gallery.
                </div>
            ) : (
                <div className="relative group cursor-zoom-in" onClick={onZoom}>
                    <img 
                        src={generation.output_image_path!} 
                        alt="Result" 
                        className="max-h-[500px] object-contain rounded-lg shadow-lg hover:shadow-xl transition-shadow"
                    />
                    <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity bg-black/10 rounded-lg pointer-events-none">
                         <Maximize2 className="text-white drop-shadow-md" size={32} />
                    </div>
                </div>
            )}
        </div>
    );
};

function App() {
  const [activeTab, setActiveTab] = useState<'generate' | 'apply-template' | 'templates' | 'gallery'>('generate');
  const [prompt, setPrompt] = useState('');
  const [uploadedImages, setUploadedImages] = useState<api.UploadedImage[]>([]);
  
  // Selection States
  const [selectedImageIds, setSelectedImageIds] = useState<number[]>([]); 
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null);

  const [aspectRatio, setAspectRatio] = useState('1:1');
  const [generations, setGenerations] = useState<api.Generation[]>([]); // Full history
  const [templates, setTemplates] = useState<api.Template[]>([]);
  const [logs, setLogs] = useState<string[]>([]);
  const [createLoading, setCreateLoading] = useState(false);
  const [applyLoading, setApplyLoading] = useState(false);

  // Separate latest results for each generation tab
  const [latestCreateResult, setLatestCreateResult] = useState<api.Generation | null>(null);
  const [latestApplyResult, setLatestApplyResult] = useState<api.Generation | null>(null);

  // Template Creation State
  const [newTemplateName, setNewTemplateName] = useState('');
  const [newTemplatePrompt, setNewTemplatePrompt] = useState('');
  const [newTemplateImages, setNewTemplateImages] = useState<number[]>([]);
  const [newTemplateAspectRatio, setNewTemplateAspectRatio] = useState('1:1');
  const [editingTemplateId, setEditingTemplateId] = useState<number | null>(null);

  // Modal State
  const [viewingItem, setViewingItem] = useState<{ 
      type: 'generation' | 'upload', 
      data: api.Generation | api.UploadedImage 
  } | null>(null);
  
  const [imageResolution, setImageResolution] = useState<string>('');

  const fileInputRef = useRef<HTMLInputElement>(null);

  const ASPECT_RATIOS = [
      { label: "Square (1:1)", value: "1:1" },
      { label: "Portrait (3:4)", value: "3:4" },
      { label: "Landscape (4:3)", value: "4:3" },
      { label: "Tall (9:16)", value: "9:16" },
      { label: "Wide (16:9)", value: "16:9" },
  ];

  const addLog = (msg: string) => {
    const timestamp = new Date().toLocaleTimeString();
    const logEntry = `[${timestamp}] ${msg}`;
    setLogs(prev => [logEntry, ...prev]);
    api.sendLog(msg);
  };

  const fetchImages = async () => {
    try {
      const imgs = await api.getImages();
      setUploadedImages(imgs);
    } catch (e) {
      addLog(`Error fetching images: ${e}`);
    }
  };

  const fetchHistory = async () => {
    try {
      const hist = await api.getHistory();
      setGenerations(hist);
    } catch (e) {
      addLog(`Error fetching history: ${e}`);
    }
  };

  const fetchTemplates = async () => {
      try {
          const tmpls = await api.getTemplates();
          setTemplates(tmpls);
      } catch (e) {
          addLog(`Error fetching templates: ${e}`);
      }
  };

  useEffect(() => {
    fetchImages();
    fetchHistory();
    fetchTemplates();
    addLog("Application started.");
  }, []);
  
  // When active tab changes, clear selections and results to avoid confusion
  useEffect(() => {
    setSelectedImageIds([]);
    setSelectedTemplateId(null);
    setPrompt(''); // Clear prompt on tab change
    // No need to clear AR, it's global to current workflow
  }, [activeTab]);

  useEffect(() => {
      setImageResolution('');
  }, [viewingItem]);

  const copyToClipboard = async (text: string) => {
      try {
          if (navigator.clipboard && window.isSecureContext) {
              await navigator.clipboard.writeText(text);
          } else {
              const textArea = document.createElement("textarea");
              textArea.value = text;
              textArea.style.position = "fixed";
              textArea.style.left = "-9999px";
              textArea.style.top = "0";
              document.body.appendChild(textArea);
              textArea.focus();
              textArea.select();
              document.execCommand('copy');
              textArea.remove();
          }
          alert("Prompt copied!");
      } catch (err) {
          console.error('Failed to copy:', err);
          alert("Failed to copy prompt.");
      }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      addLog(`Uploading file: ${file.name}`);
      try {
        const result = await api.uploadImage(file);
        setUploadedImages(prev => [result, ...prev]);
        
        if (activeTab === 'generate' || activeTab === 'apply-template') {
            setSelectedImageIds(prev => [...prev, result.id]);
        } else if (activeTab === 'templates') { // For template creation
            setNewTemplateImages(prev => [...prev, result.id]);
        }
        addLog(`Upload success. ID: ${result.id}`);
      } catch (e) {
        addLog(`Upload failed: ${e}`);
      }
    }
  };

  const handleImageToggle = (id: number, targetStateSetter: React.Dispatch<React.SetStateAction<number[]>>) => {
      targetStateSetter(prev => {
          if (prev.includes(id)) {
              return prev.filter(i => i !== id);
          } else {
              return [...prev, id];
          }
      });
  };

  const startPolling = (genId: number, startTime: number, contextTab: 'generate' | 'apply-template') => {
      const pollInterval = setInterval(async () => {
        try {
          const genStatus = await api.getGeneration(genId);
          if (genStatus.output_image_path) {
            clearInterval(pollInterval);
            
            if (contextTab === 'generate') setCreateLoading(false);
            else setApplyLoading(false);

            setGenerations(prev => [genStatus, ...prev.filter(g => g.id !== genId)]); // Update full history
            
            // Set latest result based on the context tab
            if (contextTab === 'generate') {
                setLatestCreateResult(genStatus);
            } else if (contextTab === 'apply-template') {
                setLatestApplyResult(genStatus);
            }
            
            const duration = ((Date.now() - startTime) / 1000).toFixed(1);
            if (genStatus.output_image_path === 'error') {
               addLog(`Generation ${genId} failed.`);
            } else {
               addLog(`Generation ${genId} complete! (${duration}s)`);
            }
          }
        } catch (e) { console.error("Polling error", e); }
      }, 2000);
      
      setTimeout(() => {
          if ((contextTab === 'generate' && createLoading) || (contextTab === 'apply-template' && applyLoading)) {
              clearInterval(pollInterval);
              if (contextTab === 'generate') setCreateLoading(false);
              else setApplyLoading(false);
              addLog("Generation timed out (client-side). Check gallery later.");
          }
      }, 60000);
  };
  
  const handleGenerateFromTemplate = async () => {
      if (!selectedTemplateId) {
          alert("Please select a template first.");
          return;
      }
      setApplyLoading(true);
      setLatestApplyResult(null); // Clear previous result
      addLog(`Applying template #${selectedTemplateId} with ${selectedImageIds.length} images...`);

      const startTime = Date.now();
      try {
          const initialGen = await api.generateFromTemplate(selectedTemplateId, selectedImageIds);
          startPolling(initialGen.id, startTime, 'apply-template');
      } catch(e) {
          addLog(`Template generation failed: ${e}`);
          setApplyLoading(false);
      }
  };

  const handleGenerate = async () => {
    if (!prompt) { alert("Please enter a prompt."); return; }
    setCreateLoading(true);
    setLatestCreateResult(null); // Clear previous result
    const startTime = Date.now();
    try {
      const initialGen = await api.generateContent(prompt, selectedImageIds, aspectRatio);
      startPolling(initialGen.id, startTime, 'generate');
    } catch (e) {
      addLog(`Generation request failed: ${e}`);
      setCreateLoading(false);
    }
  };

  const handleSaveTemplate = async () => {
      if (!newTemplateName || !newTemplatePrompt) {
          alert("Name and Prompt are required.");
          return;
      }
      try {
          if (editingTemplateId) {
             await api.updateTemplate(editingTemplateId, newTemplateName, newTemplatePrompt, newTemplateImages, newTemplateAspectRatio);
             addLog(`Template '${newTemplateName}' updated.`);
          } else {
             await api.createTemplate(newTemplateName, newTemplatePrompt, newTemplateImages, newTemplateAspectRatio);
             addLog(`Template '${newTemplateName}' created.`);
          }
          setNewTemplateName(''); setNewTemplatePrompt(''); setNewTemplateImages([]); setNewTemplateAspectRatio('1:1');
          setEditingTemplateId(null);
          fetchTemplates();
      } catch (e) { addLog(`Failed to save template: ${e}`); }
  };
  
  const handleStartEdit = (tmpl: api.Template) => {
      setNewTemplateName(tmpl.name);
      setNewTemplatePrompt(tmpl.prompt_template);
      setNewTemplateAspectRatio(tmpl.aspect_ratio);
      setNewTemplateImages(tmpl.reference_images.map(img => img.id));
      setEditingTemplateId(tmpl.id);
      
      // Scroll to top of form
      window.scrollTo({ top: 0, behavior: 'smooth' });
  };
  
  const handleCancelEdit = () => {
      setNewTemplateName(''); setNewTemplatePrompt(''); setNewTemplateImages([]); setNewTemplateAspectRatio('1:1');
      setEditingTemplateId(null);
  };

  const handleDeleteTemplate = async (id: number) => {
      if (confirm("Delete this template?")) {
          try {
              await api.deleteTemplate(id);
              fetchTemplates();
              if (selectedTemplateId === id) setSelectedTemplateId(null);
              addLog(`Template #${id} deleted.`);
          } catch (e) { addLog(`Failed to delete template: ${e}`); }
      }
  };

  const handleDeleteImage = async (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    if (confirm("Are you sure you want to delete this image?")) {
        try {
            await api.deleteImage(id);
            setUploadedImages(prev => prev.filter(img => img.id !== id));
            setSelectedImageIds(prev => prev.filter(i => i !== id));
            setNewTemplateImages(prev => prev.filter(i => i !== id));
            if (viewingItem?.data.id === id && viewingItem.type === 'upload') setViewingItem(null);
            addLog(`Deleted image #${id}`);
        } catch (e) {
            addLog(`Failed to delete image: ${e}`);
        }
    }
  };

  const handleDelete = async (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    if (confirm("Are you sure you want to delete this generation?")) {
      try {
        await api.deleteGeneration(id);
        setGenerations(prev => prev.filter(g => g.id !== id));
        if (latestCreateResult?.id === id) setLatestCreateResult(null); // Clear if deleted from result area
        if (latestApplyResult?.id === id) setLatestApplyResult(null);   // Clear if deleted from result area
        if (viewingItem?.data.id === id && viewingItem.type === 'generation') setViewingItem(null);
        addLog(`Deleted generation #${id}`);
      } catch (e) {
        addLog(`Failed to delete generation: ${e}`);
      }
    }
  };

  // Resolve selected image objects (for preview strip)
  const selectedImages = selectedImageIds
    .map(id => uploadedImages.find(img => img.id === id))
    .filter((img): img is api.UploadedImage => !!img);

  // Helper to extract image path safely for modal
  const getModalImageSrc = () => {
      if (!viewingItem) return '';
      if (viewingItem.type === 'upload') {
          return (viewingItem.data as api.UploadedImage).filepath;
      }
      return (viewingItem.data as api.Generation).output_image_path || '';
  };

  // Helper to extract title/prompt for modal
  const getModalTitle = () => {
      if (!viewingItem) return '';
      if (viewingItem.type === 'upload') {
          return (viewingItem.data as api.UploadedImage).filename;
      }
      return (viewingItem.data as api.Generation).prompt;
  };

  // Helper component for Image Selection Grid
  const ImageSelectionGrid = ({ onToggle, selection }: { onToggle: (id: number) => void, selection: number[] }) => (
    <div className="flex-1 border rounded-xl bg-gray-50 p-3 overflow-y-auto custom-scrollbar">
        <div className="grid grid-cols-3 md:grid-cols-4 gap-3">
            {uploadedImages.map(img => {
                const selectionIndex = selection.indexOf(img.id);
                const isSelected = selectionIndex !== -1;
                return (
                    <div key={img.id} onClick={() => onToggle(img.id)} className={`aspect-square relative rounded-lg overflow-hidden cursor-pointer border-2 transition-all group ${isSelected ? 'border-yellow-400 ring-2 ring-yellow-200' : 'border-transparent hover:border-gray-300'}`}>
                        <img src={img.filepath} alt={img.filename} className="w-full h-full object-cover" />
                        
                        {/* Action Buttons */}
                        <button 
                            onClick={(e) => { e.stopPropagation(); setViewingItem({ type: 'upload', data: img }); }} 
                            className="absolute top-1 right-1 bg-black/50 hover:bg-black/70 text-white p-1 rounded-full opacity-0 group-hover:opacity-100 transition-opacity z-10" 
                            title="Zoom"
                        >
                            <ZoomIn size={14} />
                        </button>
                        
                        <button 
                            onClick={(e) => handleDeleteImage(e, img.id)} 
                            className="absolute bottom-1 right-1 bg-red-500/80 hover:bg-red-600 text-white p-1 rounded-full opacity-0 group-hover:opacity-100 transition-opacity z-10 shadow-sm" 
                            title="Delete"
                        >
                            <Trash2 size={14} />
                        </button>

                        {isSelected && (
                             <div className="absolute inset-0 flex items-center justify-center bg-black/40 animate-in fade-in duration-200">
                                <div className="w-8 h-8 rounded-full bg-yellow-400 border-2 border-white flex items-center justify-center text-black font-bold text-lg shadow-lg">
                                    {selectionIndex + 1}
                                </div>
                            </div>
                        )}
                    </div>
                );
            })}
            {uploadedImages.length === 0 && (
                <div className="col-span-full flex items-center justify-center h-full text-gray-400 text-sm italic py-10">
                    No uploaded images yet.
                </div>
            )}
        </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-white text-gray-800 font-sans flex flex-col relative">
      
      {/* Universal Modal */}
      {viewingItem && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/95 p-4 animate-in fade-in duration-200">
          <button 
            onClick={() => setViewingItem(null)} 
            className="absolute top-4 right-4 text-white hover:text-gray-300 transition-colors"
          >
            <X size={32} />
          </button>
          
          <div className="max-w-7xl w-full max-h-screen flex flex-col gap-4">
             <div className="flex-1 flex items-center justify-center overflow-hidden relative">
                {getModalImageSrc() && !getModalImageSrc().endsWith('.txt') && getModalImageSrc() !== 'error' ? (
                   <img 
                     src={getModalImageSrc()} 
                     alt="Full View" 
                     className="max-w-full max-h-[85vh] object-contain rounded-lg shadow-2xl" 
                     onLoad={(e) => {
                         const img = e.currentTarget;
                         setImageResolution(`${img.naturalWidth} x ${img.naturalHeight}`);
                     }}
                   />
                ) : (
                   <div className="bg-white p-8 rounded text-center">Cannot display preview</div>
                )}
                
                {imageResolution && (
                    <div className="absolute bottom-4 bg-black/60 text-white px-3 py-1 rounded-full text-xs font-mono backdrop-blur-sm">
                        {imageResolution} px
                    </div>
                )}
             </div>
             
             <div className="bg-gray-900/80 backdrop-blur text-white p-6 rounded-xl flex flex-col gap-4 max-h-[30vh]">
                <div className="flex justify-between items-start gap-4">
                    <div className="flex-1 overflow-y-auto custom-scrollbar pr-2 max-h-[20vh]">
                        <p className="text-sm font-mono leading-relaxed whitespace-pre-wrap">{getModalTitle()}</p>
                    </div>
                    {viewingItem.type === 'generation' && (
                        <div className="flex flex-col gap-2 flex-shrink-0">
                            <button
                                onClick={(e) => {
                                    e.stopPropagation();
                                    copyToClipboard(getModalTitle());
                                }}
                                className="p-2 bg-white/10 hover:bg-white/20 rounded-lg transition-colors text-gray-300 hover:text-white"
                                title="Copy Prompt"
                            >
                                <Terminal size={18} />
                            </button>
                        </div>
                    )}
                </div>
                
                <div className="flex gap-4 items-center justify-end border-t border-white/10 pt-4">
                  {getModalImageSrc() && !getModalImageSrc().endsWith('.txt') && (
                     <a 
                       href={getModalImageSrc()} 
                       download={`image_${viewingItem.data.id}.png`}
                       className="flex items-center gap-2 px-4 py-2 bg-blue-600 rounded-lg hover:bg-blue-700 transition font-medium text-sm"
                       onClick={(e) => e.stopPropagation()}
                     >
                       <Download size={16} /> Download
                     </a>
                  )}
                </div>
             </div>
          </div>
        </div>
      )}

      {/* Header */}
      <header className="border-b border-gray-200 p-4 flex items-center justify-between sticky top-0 bg-white/90 backdrop-blur z-10 shadow-sm">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-yellow-400 rounded-full flex items-center justify-center font-bold text-white text-xl shadow-sm">B</div>
          <h1 className="text-xl font-semibold tracking-tight">Banana Art</h1>
        </div>
        <nav className="flex gap-2 bg-gray-100 p-1 rounded-full">
          <button 
            onClick={() => setActiveTab('generate')}
            className={`px-4 py-1.5 rounded-full text-sm font-medium transition-all ${activeTab === 'generate' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-900'}`}
          >
            Create
          </button>
           <button 
            onClick={() => setActiveTab('apply-template')}
            className={`px-4 py-1.5 rounded-full text-sm font-medium transition-all ${activeTab === 'apply-template' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-900'}`}
          >
            Apply Template
          </button>
          <button 
            onClick={() => { setActiveTab('templates'); fetchTemplates(); }}
            className={`px-4 py-1.5 rounded-full text-sm font-medium transition-all ${activeTab === 'templates' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-900'}`}
          >
            Templates
          </button>
          <button 
            onClick={() => { setActiveTab('gallery'); fetchHistory(); }}
            className={`px-4 py-1.5 rounded-full text-sm font-medium transition-all ${activeTab === 'gallery' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-900'}`}
          >
            Gallery
          </button>
        </nav>
      </header>

      <main className="flex-1 container mx-auto p-4 md:p-8 flex gap-8">
        {/* Main Content Area */}
        <div className="flex-1">
          {activeTab === 'generate' && (
            <div className="space-y-8 max-w-4xl mx-auto">
              
              {/* Image Selection Section */}
              <section className="space-y-4">
                <div className="flex justify-between items-end">
                    <h2 className="text-lg font-medium flex items-center gap-2">
                      <ImageIcon size={20} /> Input Images <span className="text-gray-400 text-sm font-normal">({selectedImageIds.length} selected)</span>
                    </h2>
                    {selectedImageIds.length > 0 && (
                        <button onClick={() => setSelectedImageIds([])} className="text-xs text-red-500 hover:underline">
                            Clear Selection
                        </button>
                    )}
                </div>
                
                <div className="flex flex-col md:flex-row gap-4 h-64">
                   <div 
                      onClick={() => fileInputRef.current?.click()}
                      className="w-full md:w-48 h-full flex-shrink-0 border-2 border-dashed border-gray-300 rounded-xl flex flex-col items-center justify-center cursor-pointer hover:border-gray-500 hover:bg-gray-50 transition-colors group"
                    >
                      <div className="w-12 h-12 bg-gray-100 rounded-full flex items-center justify-center group-hover:bg-gray-200 transition-colors mb-3">
                         <Upload size={24} className="text-gray-500" />
                      </div>
                      <span className="text-sm font-medium text-gray-600">Upload New</span>
                      <span className="text-xs text-gray-400 mt-1">JPG, PNG</span>
                      <input type="file" ref={fileInputRef} onChange={handleFileUpload} className="hidden" accept="image/*" />
                   </div>
                   <ImageSelectionGrid onToggle={(id) => handleImageToggle(id, setSelectedImageIds)} selection={selectedImageIds} />
                </div>
              </section>

              {/* Prompt Section */}
              <section className="space-y-4">
                <div className="flex justify-between items-center">
                    <h2 className="text-lg font-medium flex items-center gap-2">
                      <Terminal size={20} /> Enter Prompt
                    </h2>
                    
                    {/* Aspect Ratio Selector */}
                    <div className="flex items-center gap-2 bg-gray-100 rounded-lg p-1">
                        <Ratio size={16} className="text-gray-500 ml-2" />
                        <select 
                            value={aspectRatio} 
                            onChange={(e) => setAspectRatio(e.target.value)}
                            className="bg-transparent text-sm font-medium text-gray-700 outline-none p-1 cursor-pointer"
                        >
                            {ASPECT_RATIOS.map(r => (
                                <option key={r.value} value={r.value}>{r.label}</option>
                            ))}
                        </select>
                    </div>
                </div>

                <div className="relative group">
                  <textarea
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    placeholder={"Describe what you want to generate..."}
                    className="w-full p-4 rounded-xl border border-gray-200 focus:border-yellow-400 focus:ring-2 focus:ring-yellow-100 outline-none min-h-[100px] resize-none text-base transition-shadow"
                  />
                  <button 
                      onClick={() => setPrompt('')} 
                      className="absolute bottom-4 right-4 text-xs text-gray-400 hover:text-gray-600 underline opacity-0 group-hover:opacity-100 transition-opacity"
                  >
                      Clear
                  </button>
                </div>
              </section>

              {/* Action */}
              <div className="flex justify-end">
                <button
                  onClick={handleGenerate}
                  disabled={createLoading || !prompt}
                  className="bg-gray-900 text-white px-8 py-3 rounded-xl font-medium flex items-center gap-2 hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg hover:shadow-xl transform active:scale-95"
                >
                  {createLoading ? <RefreshCcw className="animate-spin" size={20} /> : <Send size={20} />}
                  {createLoading ? 'Generating...' : 'Generate'}
                </button>
              </div>

              {/* Result Area */}
              {(createLoading || (latestCreateResult)) && (
                <div className="mt-8 border-t pt-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
                   <h2 className="text-lg font-medium mb-4 flex items-center gap-2">
                      <Maximize2 size={20} /> Result
                   </h2>
                   
                   {createLoading ? (
                     <div className="w-full aspect-video bg-gray-50 border border-dashed border-gray-200 rounded-xl flex flex-col items-center justify-center text-gray-400">
                        <div className="relative">
                            <RefreshCcw className="animate-spin mb-4 text-yellow-400" size={40} />
                        </div>
                        <p className="font-medium text-gray-500">Creating your masterpiece...</p>
                     </div>
                   ) : latestCreateResult ? (
                     <ResultDisplay generation={latestCreateResult} onZoom={() => setViewingItem({ type: 'generation', data: latestCreateResult })} copyToClipboard={copyToClipboard} />
                   ) : null}
                </div>
              )}
            </div>
          )}
          {activeTab === 'apply-template' && (
            <div className="space-y-8 max-w-4xl mx-auto">
                {templates.length === 0 ? (
                    <div className="text-center py-20 bg-gray-50 rounded-xl border border-dashed">
                        <p className="text-gray-500 mb-4">No templates found.</p>
                        <button
                            onClick={() => setActiveTab('templates')}
                            className="bg-black text-white px-6 py-2 rounded-lg font-medium"
                        >
                            Create Your First Template
                        </button>
                    </div>
                ) : (
                    <>
                        <section> <h2 className="text-lg font-medium mb-4">1. Select a Template</h2> <div className="grid grid-cols-2 md:grid-cols-4 gap-4"> {templates.map(tmpl => ( <div key={tmpl.id} onClick={() => setSelectedTemplateId(tmpl.id)} className={`p-4 border rounded-xl cursor-pointer transition-all ${selectedTemplateId === tmpl.id ? 'border-yellow-400 ring-2 ring-yellow-200' : 'bg-white hover:border-gray-300'}`}> <div className="w-full aspect-square bg-gray-100 rounded-lg mb-2 overflow-hidden grid grid-cols-2 gap-[1px]"> {tmpl.reference_images.slice(0, 4).map((img) => ( <img key={img.id} src={img.filepath} className="w-full h-full object-cover" /> ))} </div> <h3 className="font-medium text-sm truncate">{tmpl.name}</h3> <p className="text-xs text-gray-400">{tmpl.aspect_ratio}</p> </div> ))} </div> </section>
                        <section className="space-y-4">
                            <h2 className="text-lg font-medium flex items-center gap-2"> <ImageIcon size={20} /> 2. Add Your Images <span className="text-gray-400 text-sm font-normal">({selectedImageIds.length} selected)</span> </h2>
                            <div className="flex flex-col md:flex-row gap-4 h-64"> <div onClick={() => fileInputRef.current?.click()} className="w-full md:w-48 h-full flex-shrink-0 border-2 border-dashed rounded-xl flex flex-col items-center justify-center cursor-pointer hover:bg-gray-50"> <Upload size={24} /> <span className="text-sm mt-2">Upload</span> <input type="file" ref={fileInputRef} onChange={handleFileUpload} className="hidden" accept="image/*" /> </div> <ImageSelectionGrid onToggle={(id) => handleImageToggle(id, setSelectedImageIds)} selection={selectedImageIds} /> </div>
                        </section>
                        <div className="flex justify-end"> <button onClick={handleGenerateFromTemplate} disabled={applyLoading || !selectedTemplateId} className="bg-gray-900 text-white px-8 py-3 rounded-xl font-medium flex items-center gap-2 hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed"> {applyLoading ? <RefreshCcw className="animate-spin" /> : <Wand2 />} Apply Template </button> </div>
                    </>
                )}
                 {(applyLoading || latestApplyResult) && ( <div className="mt-8 border-t pt-8"> <h2 className="text-lg font-medium mb-4">Result</h2> {applyLoading && <div className="w-full aspect-video bg-gray-100 rounded-xl flex items-center justify-center text-gray-400 animate-pulse">Processing...</div>} {latestApplyResult && <ResultDisplay generation={latestApplyResult} onZoom={() => setViewingItem({ type: 'generation', data: latestApplyResult })} copyToClipboard={copyToClipboard} />} </div> )}
            </div>
          )}
          {activeTab === 'templates' && (
            <div className="space-y-8 max-w-4xl mx-auto">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                    <div className="bg-gray-50 border rounded-xl p-6 space-y-4 h-fit sticky top-24">
                        <h2 className="text-lg font-semibold flex items-center gap-2">
                            <LayoutTemplate size={20}/> {editingTemplateId ? 'Edit Template' : 'Create New Template'}
                        </h2>
                        <div> <label className="text-xs font-bold text-gray-500 uppercase">Template Name</label> <input className="w-full mt-1 p-2 border rounded-lg" placeholder="e.g. Cyberpunk Style" value={newTemplateName} onChange={e => setNewTemplateName(e.target.value)} /> </div>
                        <div> <label className="text-xs font-bold text-gray-500 uppercase">Default Prompt</label> <textarea className="w-full mt-1 p-2 border rounded-lg h-24 text-sm" placeholder="Style description... Use {{prompt}} to insert user input." value={newTemplatePrompt} onChange={e => setNewTemplatePrompt(e.target.value)} /> </div>
                         <div> <label className="text-xs font-bold text-gray-500 uppercase">Aspect Ratio</label> <select value={newTemplateAspectRatio} onChange={(e) => setNewTemplateAspectRatio(e.target.value)} className="w-full mt-1 p-2 border rounded-lg bg-white"> {ASPECT_RATIOS.map(r => ( <option key={r.value} value={r.value}>{r.label}</option> ))} </select> </div>
                        <div> <label className="text-xs font-bold text-gray-500 uppercase mb-2 block">Reference Images ({newTemplateImages.length})</label> <div className="grid grid-cols-4 gap-2 h-40 overflow-y-auto p-2 border rounded-xl bg-white custom-scrollbar"> <div onClick={() => fileInputRef.current?.click()} className="aspect-square border-2 border-dashed border-gray-300 rounded-lg flex items-center justify-center cursor-pointer hover:bg-gray-100"> <Upload size={16} className="text-gray-400" /> <input type="file" ref={fileInputRef} onChange={handleFileUpload} className="hidden" accept="image/*" /> </div> {uploadedImages.map(img => { const selectionIndex = newTemplateImages.indexOf(img.id); const isSelected = selectionIndex !== -1; return ( <div key={img.id} onClick={() => handleImageToggle(img.id, setNewTemplateImages)} className={`aspect-square relative rounded-lg overflow-hidden cursor-pointer border-2 ${isSelected ? 'border-yellow-400 ring-2 ring-yellow-200' : 'border-transparent opacity-70 hover:opacity-100'}`}> <img src={img.filepath} className="w-full h-full object-cover" /> {isSelected && ( <div className="absolute inset-0 flex items-center justify-center bg-black/40"> <div className="w-6 h-6 rounded-full bg-yellow-400 border-2 border-white flex items-center justify-center text-black font-bold text-xs shadow-lg"> {selectionIndex + 1} </div> </div> )} </div> ); })} </div> </div>
                        <div className="flex gap-2">
                            {editingTemplateId && (
                                <button onClick={handleCancelEdit} className="flex-1 bg-white border border-gray-300 text-gray-700 py-2 rounded-lg font-medium hover:bg-gray-50"> Cancel </button>
                            )}
                            <button onClick={handleSaveTemplate} className="flex-1 bg-black text-white py-2 rounded-lg font-medium hover:bg-gray-800"> {editingTemplateId ? 'Update Template' : 'Save Template'} </button>
                        </div>
                    </div>
                    <div className="space-y-4">
                        <h2 className="text-lg font-semibold">Saved Templates</h2>
                        {templates.length === 0 && <p className="text-gray-400 italic">No templates yet.</p>}
                        {templates.map(tmpl => {
                            const hasImages = tmpl.reference_images && tmpl.reference_images.length > 0;
                            return (
                                <div key={tmpl.id} className={`border rounded-xl p-4 flex gap-4 hover:shadow-sm bg-white transition-shadow relative group ${!hasImages ? 'border-red-300 bg-red-50' : ''}`}>
                                    <div className={`w-20 h-20 rounded-lg flex-shrink-0 overflow-hidden grid grid-cols-2 gap-[1px] ${hasImages ? 'bg-gray-100' : 'bg-red-100 flex items-center justify-center'}`}> 
                                        {hasImages ? (
                                            tmpl.reference_images.slice(0, 4).map((img) => ( <img key={img.id} src={img.filepath} className="w-full h-full object-cover" /> ))
                                        ) : (
                                            <div className="text-red-400 text-xs text-center px-1">No Images</div>
                                        )}
                                    </div>
                                    <div className="flex-1 min-w-0"> 
                                        <div className="flex justify-between items-start"> 
                                            <h3 className={`font-medium ${!hasImages ? 'text-red-700' : 'text-gray-900'}`}>{tmpl.name}</h3> 
                                            <span className="text-xs bg-gray-100 text-gray-500 font-mono px-2 py-0.5 rounded-full z-0">{tmpl.aspect_ratio}</span> 
                                        </div> 
                                        <p className="text-xs text-gray-500 mt-1 line-clamp-2 font-mono">{tmpl.prompt_template}</p> 
                                        <div className="mt-2 text-xs text-gray-400 flex items-center justify-between">
                                            <div className="flex items-center gap-2">
                                                <span>{new Date(tmpl.created_at).toLocaleDateString()}</span>
                                                {!hasImages && <span className="text-red-500 font-bold flex items-center gap-1 text-[10px] uppercase tracking-wider"><X size={10}/> Missing Images</span>}
                                            </div>
                                            <div className="flex gap-1">
                                                <button onClick={() => handleStartEdit(tmpl)} className="p-1.5 text-gray-400 hover:text-blue-500 hover:bg-blue-50 rounded-lg transition-colors flex items-center gap-1" title="Edit"> 
                                                    <Edit size={14} /> <span className="text-[10px] font-bold uppercase">Edit</span>
                                                </button>
                                                <button onClick={() => handleDeleteTemplate(tmpl.id)} className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors flex items-center gap-1" title="Delete"> 
                                                    <Trash2 size={14} /> <span className="text-[10px] font-bold uppercase">Delete</span>
                                                </button>
                                            </div>
                                        </div> 
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            </div>
          )}
          {activeTab === 'gallery' && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {generations.map(gen => (
                <div key={gen.id} className="bg-white border border-gray-100 rounded-xl overflow-hidden shadow-sm hover:shadow-md transition-shadow group relative flex flex-col">
                  <div className="flex-1 bg-gray-50 relative cursor-pointer overflow-hidden flex" onClick={() => setViewingItem({ type: 'generation', data: gen })}>
                     {gen.source_images && gen.source_images.length > 0 ? (
                         <>
                            <div className="w-1/3 h-full border-r border-white/20 flex flex-col"> {gen.source_images.map((srcImg, idx) => ( <div key={srcImg.id} className="relative flex-1 w-full border-b border-white/10 last:border-b-0 overflow-hidden group/in"> <img src={srcImg.filepath} className="w-full h-full object-cover opacity-80" alt={`Input ${idx + 1}`} /> <div className="absolute bottom-1 left-1 bg-black/50 text-white text-[10px] px-1.5 py-0.5 rounded backdrop-blur-sm">IN {idx + 1}</div> </div> ))} </div>
                            <div className="w-2/3 h-full relative"> {gen.output_image_path && !gen.output_image_path.endsWith('.txt') && gen.output_image_path !== 'error' ? ( <img src={gen.output_image_path} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" alt="Output" /> ) : ( <div className="w-full h-full flex items-center justify-center text-xs text-gray-400">Failed/Text</div> )} <div className="absolute bottom-1 right-1 bg-yellow-400 text-black font-bold text-[10px] px-1 rounded shadow-sm">OUT</div> </div>
                         </>
                     ) : (
                         <div className="w-full h-full relative"> {gen.output_image_path && !gen.output_image_path.endsWith('.txt') && gen.output_image_path !== 'error' ? ( <img src={gen.output_image_path} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" alt="Output" /> ) : ( <div className="w-full h-full flex items-center justify-center text-xs text-gray-400">Failed/Text</div> )} </div>
                     )}
                     <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors flex items-center justify-center opacity-0 group-hover:opacity-100 pointer-events-none"> <span className="bg-white/90 px-3 py-1 rounded-full text-xs font-medium shadow-sm flex items-center gap-1"> <ZoomIn size={12} /> View </span> </div>
                  </div>
                  <div className="p-4 relative flex flex-col justify-between border-t border-gray-100">
                    <p className="text-sm text-gray-600 line-clamp-2 mb-4" title={gen.prompt}>{gen.prompt}</p>
                    <div className="text-xs text-gray-400 flex justify-between items-end"> <span>{new Date(gen.created_at).toLocaleDateString()}</span> <button onClick={(e) => handleDelete(e, gen.id)} className="text-gray-400 hover:text-red-500 p-1.5 hover:bg-red-50 rounded-md transition-all" title="Delete"> <Trash2 size={16} /> </button> </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        <aside className="w-80 hidden xl:flex flex-col border-l border-gray-100 pl-8 h-[calc(100vh-100px)] sticky top-24">
          <h3 className="text-sm font-semibold text-gray-900 mb-4 flex items-center gap-2"> <History size={16} /> Activity Log </h3>
          <div className="flex-1 overflow-y-auto pr-2 space-y-3 font-mono text-xs text-gray-500 custom-scrollbar"> {logs.map((log, idx) => ( <div key={idx} className="border-b border-gray-50 pb-2 last:border-0 break-words leading-relaxed"> {log} </div> ))} {logs.length === 0 && <span className="text-gray-300 italic">Logs will appear here...</span>} </div>
        </aside>
      </main>
    </div>
  );
}

export default App;