import React, { useState, useEffect, useRef } from 'react';
import { Upload, Image as ImageIcon, Send, History, RefreshCcw, Terminal, Trash2, Download, X, Maximize2, ZoomIn, ArrowRight, Ratio } from 'lucide-react';
import * as api from './api';

function App() {
  const [activeTab, setActiveTab] = useState<'generate' | 'gallery'>('generate');
  const [prompt, setPrompt] = useState('');
  const [uploadedImages, setUploadedImages] = useState<api.UploadedImage[]>([]);
  const [selectedImageId, setSelectedImageId] = useState<number | null>(null);
  const [aspectRatio, setAspectRatio] = useState('1:1'); // New State
  const [generations, setGenerations] = useState<api.Generation[]>([]);
  const [logs, setLogs] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [latestGeneration, setLatestGeneration] = useState<api.Generation | null>(null);
  
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
      addLog(`Fetched ${imgs.length} uploaded images.`);
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

  useEffect(() => {
    fetchImages();
    fetchHistory();
    addLog("Application started.");
  }, []);

  // Clear resolution when modal opens/changes
  useEffect(() => {
      setImageResolution('');
  }, [viewingItem]);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      addLog(`Uploading file: ${file.name}`);
      try {
        const result = await api.uploadImage(file);
        setUploadedImages(prev => [result, ...prev]);
        setSelectedImageId(result.id);
        addLog(`Upload success. ID: ${result.id}`);
      } catch (e) {
        addLog(`Upload failed: ${e}`);
      }
    }
  };

  const handleImageToggle = (id: number) => {
      setSelectedImageId(prev => prev === id ? null : id);
  };

  const handleGenerate = async () => {
    if (!prompt) {
      alert("Please enter a prompt.");
      return;
    }

    setLoading(true);
    setLatestGeneration(null);
    
    // Log intent
    const mode = selectedImageId ? "Img2Img" : "Txt2Img";
    addLog(`Sending generation request (${mode}, AR: ${aspectRatio})...`);
    
    const startTime = Date.now();

    try {
      // 1. Start Generation
      const initialGen = await api.generateContent(prompt, selectedImageId, aspectRatio);
      addLog(`Request sent (ID: ${initialGen.id}). Processing...`);
      
      // 2. Poll for result
      const pollInterval = setInterval(async () => {
        try {
          const genStatus = await api.getGeneration(initialGen.id);
          
          if (genStatus.output_image_path) {
            clearInterval(pollInterval);
            setLoading(false);
            setLatestGeneration(genStatus);
            fetchHistory(); // Refresh gallery
            
            const duration = ((Date.now() - startTime) / 1000).toFixed(1);

            if (genStatus.output_image_path === 'error') {
               addLog(`Generation ${initialGen.id} failed.`);
            } else {
               addLog(`Generation ${initialGen.id} complete! (${duration}s)`);
            }
          }
        } catch (e) {
          console.error("Polling error", e);
        }
      }, 2000);
      
      // Safety timeout after 60s
      setTimeout(() => {
          if (loading) {
              clearInterval(pollInterval);
              setLoading(false);
              addLog("Generation timed out (client-side). Check gallery later.");
          }
      }, 60000);

    } catch (e) {
      addLog(`Generation request failed: ${e}`);
      setLoading(false);
    }
  };

  const handleDelete = async (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    if (confirm("Are you sure you want to delete this generation?")) {
      try {
        await api.deleteGeneration(id);
        setGenerations(prev => prev.filter(g => g.id !== id));
        if (latestGeneration?.id === id) setLatestGeneration(null);
        if (viewingItem?.data.id === id && viewingItem.type === 'generation') setViewingItem(null);
        addLog(`Deleted generation #${id}`);
      } catch (e) {
        addLog(`Failed to delete generation: ${e}`);
      }
    }
  };

  const selectedImage = uploadedImages.find(img => img.id === selectedImageId);

  // Helper to extract image path safely
  const getModalImageSrc = () => {
      if (!viewingItem) return '';
      if (viewingItem.type === 'upload') {
          return (viewingItem.data as api.UploadedImage).filepath;
      }
      return (viewingItem.data as api.Generation).output_image_path || '';
  };

  const getModalTitle = () => {
      if (!viewingItem) return '';
      if (viewingItem.type === 'upload') {
          return (viewingItem.data as api.UploadedImage).filename;
      }
      return (viewingItem.data as api.Generation).prompt;
  };

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
                
                {/* Resolution Badge */}
                {imageResolution && (
                    <div className="absolute bottom-4 bg-black/60 text-white px-3 py-1 rounded-full text-xs font-mono backdrop-blur-sm">
                        {imageResolution} px
                    </div>
                )}
             </div>
             
             <div className="bg-gray-900/50 backdrop-blur text-white p-4 rounded-xl flex justify-between items-center">
                <p className="text-sm opacity-90 truncate max-w-xl font-mono">{getModalTitle()}</p>
                <div className="flex gap-4 items-center">
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
        <nav className="flex gap-4">
          <button 
            onClick={() => setActiveTab('generate')}
            className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${activeTab === 'generate' ? 'bg-gray-900 text-white' : 'text-gray-500 hover:bg-gray-100'}`}
          >
            Create
          </button>
          <button 
            onClick={() => { setActiveTab('gallery'); fetchHistory(); }}
            className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${activeTab === 'gallery' ? 'bg-gray-900 text-white' : 'text-gray-500 hover:bg-gray-100'}`}
          >
            Gallery
          </button>
        </nav>
      </header>

      <main className="flex-1 container mx-auto p-4 md:p-8 flex gap-8">
        {/* Main Content Area */}
        <div className="flex-1">
          {activeTab === 'generate' ? (
            <div className="space-y-8 max-w-4xl mx-auto">
              
              {/* Image Selection Section */}
              <section className="space-y-4">
                <div className="flex justify-between items-end">
                    <h2 className="text-lg font-medium flex items-center gap-2">
                      <ImageIcon size={20} /> Select Input Image <span className="text-gray-400 text-sm font-normal">(Optional)</span>
                    </h2>
                    {selectedImageId && (
                        <button onClick={() => setSelectedImageId(null)} className="text-xs text-red-500 hover:underline">
                            Deselect
                        </button>
                    )}
                </div>
                
                <div className="flex flex-col md:flex-row gap-4 h-64">
                   {/* Left: Upload Block */}
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

                   {/* Right: History Grid */}
                   <div className="flex-1 border rounded-xl bg-gray-50 p-3 overflow-y-auto">
                      <div className="grid grid-cols-3 md:grid-cols-4 gap-3">
                        {uploadedImages.map(img => (
                          <div 
                            key={img.id}
                            onClick={() => handleImageToggle(img.id)}
                            className={`aspect-square relative rounded-lg overflow-hidden cursor-pointer border-2 transition-all group ${selectedImageId === img.id ? 'border-yellow-400 ring-2 ring-yellow-200' : 'border-transparent hover:border-gray-300'}`}
                          >
                            <img src={img.filepath} alt={img.filename} className="w-full h-full object-cover" />
                            
                            <button
                               onClick={(e) => {
                                   e.stopPropagation();
                                   setViewingItem({ type: 'upload', data: img });
                               }}
                               className="absolute top-1 right-1 bg-black/50 hover:bg-black/70 text-white p-1 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
                               title="Zoom"
                            >
                                <ZoomIn size={14} />
                            </button>
                            
                            {selectedImageId === img.id && (
                                <div className="absolute inset-0 border-4 border-yellow-400/50 rounded-lg pointer-events-none flex items-center justify-center">
                                    <div className="bg-yellow-400 text-white rounded-full p-1 shadow-sm">
                                        <ArrowRight size={16} className="-rotate-45" />
                                    </div>
                                </div>
                            )}
                          </div>
                        ))}
                        {uploadedImages.length === 0 && (
                            <div className="col-span-full flex items-center justify-center h-full text-gray-400 text-sm italic py-10">
                                No uploaded images yet.
                            </div>
                        )}
                      </div>
                   </div>
                </div>

                {/* Selected Image Preview */}
                {selectedImage && (
                   <div className="w-full p-4 bg-gray-50 rounded-xl border border-gray-200 flex flex-col items-center animate-in fade-in slide-in-from-top-2">
                      <div className="flex justify-between w-full items-center mb-2 px-2">
                          <span className="text-xs text-gray-500 font-medium uppercase tracking-wide">Selected Input</span>
                          <button 
                             onClick={() => setViewingItem({ type: 'upload', data: selectedImage })}
                             className="text-xs flex items-center gap-1 text-blue-600 hover:underline"
                          >
                             <ZoomIn size={12} /> View Full
                          </button>
                      </div>
                      <img 
                        src={selectedImage.filepath} 
                        alt="Selected Preview" 
                        className="max-h-64 object-contain rounded-lg shadow-sm bg-white cursor-pointer" 
                        onClick={() => setViewingItem({ type: 'upload', data: selectedImage })}
                      />
                   </div>
                )}
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
                    placeholder="Describe what you want to generate..."
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
                  disabled={loading || !prompt}
                  className="bg-gray-900 text-white px-8 py-3 rounded-xl font-medium flex items-center gap-2 hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg hover:shadow-xl transform active:scale-95"
                >
                  {loading ? <RefreshCcw className="animate-spin" size={20} /> : <Send size={20} />}
                  {loading ? 'Generating...' : 'Generate'}
                </button>
              </div>

              {/* Result Area */}
              {(loading || latestGeneration) && (
                <div className="mt-8 border-t pt-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
                   <h2 className="text-lg font-medium mb-4 flex items-center gap-2">
                      <Maximize2 size={20} /> Result
                   </h2>
                   
                   {loading ? (
                     <div className="w-full aspect-video bg-gray-50 border border-dashed border-gray-200 rounded-xl flex flex-col items-center justify-center text-gray-400">
                        <div className="relative">
                            <RefreshCcw className="animate-spin mb-4 text-yellow-400" size={40} />
                            <div className="absolute inset-0 flex items-center justify-center">
                                <span className="w-2 h-2 bg-yellow-400 rounded-full animate-ping" />
                            </div>
                        </div>
                        <p className="font-medium text-gray-500">Creating your masterpiece...</p>
                        <p className="text-xs text-gray-400 mt-2">This usually takes about 5-10 seconds</p>
                     </div>
                   ) : latestGeneration ? (
                     <div className="w-full bg-gray-50 p-4 rounded-xl border border-gray-200 flex flex-col items-center">
                        {latestGeneration.output_image_path === 'error' ? (
                           <div className="text-red-500 py-10 flex flex-col items-center gap-2">
                               <X size={40} />
                               <span>Generation Failed</span>
                           </div>
                        ) : latestGeneration.output_image_path?.endsWith('.txt') ? (
                           <div className="p-6 bg-white border rounded w-full font-mono text-sm whitespace-pre-wrap">
                              Result saved as text. Check Gallery.
                           </div>
                        ) : (
                           <img 
                             src={latestGeneration.output_image_path!} 
                             alt="Result" 
                             className="max-h-[500px] object-contain rounded-lg shadow-lg cursor-zoom-in hover:shadow-xl transition-shadow"
                             onClick={() => setViewingItem({ type: 'generation', data: latestGeneration })}
                           />
                        )}
                        <div className="flex gap-3 mt-4">
                           <button 
                               onClick={() => setViewingItem({ type: 'generation', data: latestGeneration })} 
                               className="text-sm px-4 py-2 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 font-medium shadow-sm transition-colors"
                            >
                               View Fullscreen
                           </button>
                        </div>
                     </div>
                   ) : null}
                </div>
              )}

            </div>
          ) : (
            /* Gallery Tab */
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {generations.map(gen => (
                <div 
                  key={gen.id} 
                  className="bg-white border border-gray-100 rounded-xl overflow-hidden shadow-sm hover:shadow-md transition-shadow group relative flex flex-col"
                >
                  <div className="flex-1 bg-gray-50 relative cursor-pointer overflow-hidden flex" onClick={() => setViewingItem({ type: 'generation', data: gen })}>
                     
                     {/* Dual View if Source exists */}
                     {gen.source_image ? (
                         <>
                            <div className="w-1/3 h-full border-r border-white/20 relative">
                                <img src={gen.source_image.filepath} className="w-full h-full object-cover opacity-80" alt="Input" />
                                <div className="absolute bottom-1 left-1 bg-black/50 text-white text-[10px] px-1 rounded">IN</div>
                            </div>
                            <div className="w-2/3 h-full relative">
                                {gen.output_image_path && !gen.output_image_path.endsWith('.txt') && gen.output_image_path !== 'error' ? (
                                    <img src={gen.output_image_path} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" alt="Output" />
                                ) : (
                                    <div className="w-full h-full flex items-center justify-center text-xs text-gray-400">Failed/Text</div>
                                )}
                                <div className="absolute bottom-1 right-1 bg-yellow-400 text-black font-bold text-[10px] px-1 rounded">OUT</div>
                            </div>
                         </>
                     ) : (
                         /* Single View */
                         <div className="w-full h-full relative">
                            {gen.output_image_path && !gen.output_image_path.endsWith('.txt') && gen.output_image_path !== 'error' ? (
                                <img src={gen.output_image_path} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" alt="Output" />
                            ) : (
                                <div className="w-full h-full flex items-center justify-center text-xs text-gray-400">Failed/Text</div>
                            )}
                         </div>
                     )}

                     {/* Overlay */}
                     <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors flex items-center justify-center opacity-0 group-hover:opacity-100 pointer-events-none">
                        <span className="bg-white/90 px-3 py-1 rounded-full text-xs font-medium shadow-sm flex items-center gap-1">
                            <ZoomIn size={12} /> View
                        </span>
                     </div>
                  </div>
                  
                  <div className="p-4 relative flex flex-col justify-between border-t border-gray-100">
                    <p className="text-sm text-gray-600 line-clamp-2 mb-4" title={gen.prompt}>{gen.prompt}</p>
                    <div className="text-xs text-gray-400 flex justify-between items-end">
                      <span>{new Date(gen.created_at).toLocaleDateString()}</span>
                      <button 
                        onClick={(e) => handleDelete(e, gen.id)}
                        className="text-gray-400 hover:text-red-500 p-1.5 hover:bg-red-50 rounded-md transition-all"
                        title="Delete"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
              {generations.length === 0 && (
                <div className="col-span-full text-center text-gray-400 py-20 flex flex-col items-center gap-4">
                  <div className="w-16 h-16 bg-gray-50 rounded-full flex items-center justify-center">
                      <ImageIcon size={32} className="opacity-20" />
                  </div>
                  <p>No generations yet. Create your first art!</p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Sidebar Log Panel */}
        <aside className="w-80 hidden xl:flex flex-col border-l border-gray-100 pl-8 h-[calc(100vh-100px)] sticky top-24">
          <h3 className="text-sm font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <History size={16} /> Activity Log
          </h3>
          <div className="flex-1 overflow-y-auto pr-2 space-y-3 font-mono text-xs text-gray-500 custom-scrollbar">
            {logs.map((log, idx) => (
              <div key={idx} className="border-b border-gray-50 pb-2 last:border-0 break-words leading-relaxed">
                {log}
              </div>
            ))}
            {logs.length === 0 && <span className="text-gray-300 italic">Logs will appear here...</span>}
          </div>
        </aside>
      </main>
    </div>
  );
}

export default App;