//prime-frontend/src/pages/AppPage.jsx
import { useState } from 'react';
import ExcelUploader from '../components/ExcelUploader';
import LoadingState from '../components/LoadingState';
import ChatResult from '../components/ChatResult';
import MapView from '../components/MapView';
import ErrorState from '../components/ErrorState';
import { sendFleetRequest } from '../services/fleetApi';

export default function AppPage() {
  const [appState, setAppState] = useState('idle');       // idle | loading | result | map | error
  const [fleetResponse, setFleetResponse] = useState(null);
  const [selectedArchetype, setSelectedArchetype] = useState(null);
  const [errorMessage, setErrorMessage] = useState('');
  const [parsedPayload, setParsedPayload] = useState(null);
  const [loadingStart, setLoadingStart] = useState(null);

  // Called by ExcelUploader after successful parse
  const handleParsed = async (payload) => {
    setParsedPayload(payload);
    setAppState('loading');
    setLoadingStart(Date.now());

    try {
      const response = await sendFleetRequest(payload);
      setFleetResponse(response);
      setAppState('result');
    } catch (err) {
      setErrorMessage(err.message);
      setAppState('error');
    }
  };

  // Called by ChatResult when a chip is clicked
  const handleSelectArchetype = (key) => {
    setSelectedArchetype(key);
    setAppState('map');
  };

  // Called from MapView to change archetype without going back
  const handleChangeArchetype = (key) => {
    setSelectedArchetype(key);
  };

  const handleRetry = () => {
    setErrorMessage('');
    setFleetResponse(null);
    setAppState('idle');
  };

  const handleBackToResults = () => {
    setAppState('result');
  };

  return (
    <div id="app-page" className="min-h-screen bg-zinc-950">
      {/* Simple header (shown on non-map states) */}
      {appState !== 'map' && (
        <header className="w-full px-6 py-4 border-b border-zinc-900/50">
          <a href="/" className="text-lg font-bold text-white tracking-tight hover:text-blue-400 transition-colors">
            [NOMBRE]
          </a>
        </header>
      )}

      {appState === 'idle' && (
        <ExcelUploader onParsed={handleParsed} />
      )}

      {appState === 'loading' && (
        <LoadingState startTime={loadingStart} />
      )}

      {appState === 'result' && (
        <ChatResult
          fleetResponse={fleetResponse}
          parsedPayload={parsedPayload}
          onSelectArchetype={handleSelectArchetype}
        />
      )}

      {appState === 'map' && (
        <MapView
          fleetResponse={fleetResponse}
          selectedArchetype={selectedArchetype}
          parsedPayload={parsedPayload}
          onChangeArchetype={handleChangeArchetype}
          onBack={handleBackToResults}
        />
      )}

      {appState === 'error' && (
        <ErrorState message={errorMessage} onRetry={handleRetry} />
      )}
    </div>
  );
}
