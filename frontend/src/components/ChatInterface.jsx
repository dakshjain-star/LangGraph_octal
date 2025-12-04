import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, Bot, User as UserIcon, LogOut, Loader2, RotateCcw } from 'lucide-react';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const ChatInterface = ({ user, onLogout }) => {
  const [messages, setMessages] = useState([
    { role: 'bot', content: `Hello ${user.user_name}! I'm your Task Assistant. How can I help you today?` }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [resetting, setResetting] = useState(false);
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Auto-resize textarea when input changes
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    // reset height to measure scrollHeight correctly
    ta.style.height = 'auto';
    const newHeight = Math.min(ta.scrollHeight, 192); // limit around 48 * 4 = 192px (max-h-48)
    ta.style.height = `${newHeight}px`;
  }, [input]);

  const handleResetChat = async () => {
    if (loading || resetting) return;
    setResetting(true);

    try {
      await axios.post('http://localhost:8081/reset_chat', {
        token: user.token,
      });
    } catch (err) {
      if (err.response?.status === 401) {
        // Token expired, logout
        onLogout();
        return;
      }
      // Even if backend fails, still clear local history for UX
    } finally {
      setMessages([
        {
          role: 'bot',
          content: `Hello ${user.user_name}! I've cleared our previous conversation. How can I help you now?`,
        },
      ]);
      setResetting(false);
    }
  };

  const handleSend = async (e) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMsg = input;
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setLoading(true);

    try {
      const res = await axios.post('http://localhost:8081/chat', {
        message: userMsg,
        token: user.token
      });

      setMessages(prev => [...prev, { role: 'bot', content: res.data.response }]);
    } catch (err) {
      if (err.response?.status === 401) {
        // Token expired, logout
        setMessages(prev => [...prev, { role: 'bot', content: "Your session has expired. Please login again." }]);
        setTimeout(() => onLogout(), 2000);
      } else {
        setMessages(prev => [...prev, { role: 'bot', content: "Sorry, I encountered an error processing your request." }]);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-primary">
      {/* Header */}
      <header className="bg-secondary border-b border-slate-700 p-4 flex justify-between items-center shadow-lg z-10">
        <div className="flex items-center gap-3">
          <div className="bg-accent/20 p-2 rounded-lg">
            <Bot className="w-6 h-6 text-accent" />
          </div>
          <div>
            <h1 className="font-bold text-white">Task Assistant</h1>
            <p className="text-xs text-slate-400">
              {user.user_name} ({user.email})
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleResetChat}
            disabled={loading || resetting}
            className="p-2 hover:bg-slate-700 rounded-lg text-slate-400 hover:text-white transition-colors disabled:opacity-50"
            title="Reset chat history"
          >
            {resetting ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              <RotateCcw className="w-5 h-5" />
            )}
          </button>
          <button 
            onClick={onLogout}
            className="p-2 hover:bg-slate-700 rounded-lg text-slate-400 hover:text-white transition-colors"
            title="Logout"
          >
            <LogOut className="w-5 h-5" />
          </button>
        </div>
      </header>

      {/* Chat Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-6 custom-scrollbar">
        <AnimatePresence>
          {messages.map((msg, idx) => (
            <motion.div
              key={idx}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div className={`flex gap-3 max-w-[80%] ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
                <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
                  msg.role === 'user' ? 'bg-accent' : 'bg-slate-700'
                }`}>
                  {msg.role === 'user' ? <UserIcon className="w-5 h-5 text-white" /> : <Bot className="w-5 h-5 text-accent" />}
                </div>
                
                <div className={`p-4 rounded-2xl ${
                  msg.role === 'user' 
                    ? 'bg-accent text-white rounded-tr-none' 
                    : 'bg-secondary text-slate-200 rounded-tl-none border border-slate-700'
                }`}>
                  <div className="prose prose-invert max-w-none text-sm" style={{ wordBreak: 'break-word', overflowWrap: 'anywhere' }}>
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                  </div>
                </div>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
        
        {loading && (
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex justify-start"
          >
            <div className="flex gap-3">
              <div className="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center">
                <Bot className="w-5 h-5 text-accent" />
              </div>
              <div className="bg-secondary p-4 rounded-2xl rounded-tl-none border border-slate-700 flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin text-accent" />
                <span className="text-sm text-slate-400">Thinking...</span>
              </div>
            </div>
          </motion.div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="p-4 bg-secondary border-t border-slate-700">
        <form onSubmit={handleSend} className="max-w-4xl mx-auto relative">
          {/* Toolbar removed - keep only textarea for newline support */}
          <textarea
            ref={(el) => textareaRef.current = el}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              // Enter sends message, Shift+Enter inserts newline
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend(e);
              }
            }}
            placeholder="Type your message..."
            className="w-full bg-slate-800 border border-slate-700 rounded-xl py-3 pl-4 pr-14 text-white focus:outline-none focus:ring-2 focus:ring-accent transition-all shadow-inner resize-none overflow-auto max-h-48"
            disabled={loading}
            rows={2}
          />

          <button
            type="submit"
            disabled={!input.trim() || loading}
            className="absolute right-2 top-1/2 transform -translate-y-1/2 p-2 bg-accent hover:bg-blue-600 text-white rounded-lg transition-all disabled:opacity-50 disabled:hover:bg-accent"
            title="Send (Enter)"
          >
            <Send className="w-5 h-5" />
          </button>
        </form>
      </div>
    </div>
  );
};

export default ChatInterface;