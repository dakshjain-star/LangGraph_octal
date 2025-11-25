import React, { useState } from 'react';
import Login from './components/Login';
import ChatInterface from './components/ChatInterface';

function App() {
  const [user, setUser] = useState(null);

  const handleLogin = (userData) => {
    setUser(userData);
  };

  const handleLogout = () => {
    setUser(null);
  };

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
