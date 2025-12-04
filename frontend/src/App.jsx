import React, { useState, useEffect } from 'react';
import axios from 'axios';
import Login from './components/Login';
import ChatInterface from './components/ChatInterface';

function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // Check for stored token on mount
  useEffect(() => {
    const verifyStoredToken = async () => {
      const storedToken = localStorage.getItem('chatbot_token');
      
      if (storedToken) {
        try {
          const res = await axios.post('http://localhost:8081/verify_token', {
            token: storedToken
          });
          
          // Token is valid, restore user session
          setUser({
            token: storedToken,
            user_id: res.data.user_id,
            user_name: res.data.user_name,
            email: res.data.email
          });
        } catch (err) {
          // Token invalid or expired, clear it
          localStorage.removeItem('chatbot_token');
        }
      }
      
      setLoading(false);
    };

    verifyStoredToken();
  }, []);

  const handleLogin = (userData) => {
    // Store token in localStorage
    localStorage.setItem('chatbot_token', userData.token);
    setUser(userData);
  };

  const handleLogout = async () => {
    // Call logout endpoint to invalidate token
    if (user?.token) {
      try {
        await axios.post('http://localhost:8081/logout', {
          token: user.token
        });
      } catch (err) {
        console.error('Logout error:', err);
      }
    }
    
    // Clear local storage and state
    localStorage.removeItem('chatbot_token');
    setUser(null);
  };

  // Show loading state while verifying token
  if (loading) {
    return (
      <div className="bg-primary min-h-screen text-white flex items-center justify-center">
        <div className="text-slate-400">Loading...</div>
      </div>
    );
  }

  return (
    <div className="bg-primary min-h-screen text-white">
      {!user ? (
        <Login onLogin={handleLogin} />
      ) : (
        <ChatInterface user={user} onLogout={handleLogout} />
      )}
    </div>
  );
}

export default App;
