//prime-frontend/src/pages/AppPage.jsx
import { useState } from 'react';
import { useAuth } from '../hooks/useAuth';
import ExcelUploader from '../components/ExcelUploader';
import LoadingState from '../components/LoadingState';
import ChatResult from '../components/ChatResult';
import MapView from '../components/MapView';
import ErrorState from '../components/ErrorState';
import AdvancedConfig from '../components/AdvancedConfig';
import { sendFleetRequest } from '../services/fleetApi';
import { supabase } from '../services/supabaseClient';

export default function AppPage() {
  const { user, signOut } = useAuth();
  const [appState, setAppState] = useState('idle');
  const [fleetResponse, setFleetResponse] = useState(null);
  const [selectedArchetype, setSelectedArchetype] = useState(null);
  const [errorMessage, setErrorMessage] = useState('');
  const [parsedPayload, setParsedPayload] = useState(null);
  const [loadingStart, setLoadingStart] = useState(null);
  const [advConfig, setAdvConfig] = useState(null);

  const handleParsed = async (payload) => {
    const [h, m] = (advConfig?.departure_time || "08:00").split(':').map(Number);
    const shiftMin = h * 60 + m;

    // 🔥 EL FIX ESTÁ ACÁ: Pasamos el JSON anidado del CFO directo al Backend
    const finalPayload = {
      ...payload,
      departure_time: advConfig?.departure_time || "08:00",
      shift_start_minutes: shiftMin,
      stochastic_mode: advConfig?.stochastic_mode || false,
      economic_profile: advConfig?.economic_profile
    };

    setParsedPayload(finalPayload);
    setAppState('loading');
    setLoadingStart(Date.now());

    try {
      const response = await sendFleetRequest(finalPayload);
      setFleetResponse(response);
      setAppState('result');

      // M4: Guardar en Historial (Supabase)
      if (user) {
        const firstPlan = Object.values(response.plans || {})[0] || {};
        const summary = firstPlan.plan_financial_summary || {};

        await supabase.from('consultas').insert({
          user_id: user.id,
          n_vehiculos: finalPayload.vehicles.length,
          n_destinos: finalPayload.destinations.length,
          archetypes: finalPayload.allowed_archetypes || ["equilibrista"],
          response_json: response,
          shift_start_minutes: finalPayload.shift_start_minutes,
          departure_time: finalPayload.departure_time,
          costo_total_ars: summary.total_expected_cost || 0,
          distancia_km: summary.distancia_km || 0
        });
      }

    } catch (err) {
      setErrorMessage(err.message);
      setAppState('error');
    }
  };

  const handleSelectArchetype = (key) => { setSelectedArchetype(key); setAppState('map'); };
  const handleChangeArchetype = (key) => { setSelectedArchetype(key); };
  const handleRetry = () => { setErrorMessage(''); setFleetResponse(null); setAppState('idle'); };
  const handleBackToResults = () => { setAppState('result'); };

  return (
    <div id="app-page" className="min-h-screen bg-slate-50">
      {appState !== 'map' && (
        <header className="w-full px-6 py-4 border-b border-slate-200 bg-white flex items-center justify-between shadow-sm">
          <a href="/" className="text-xl font-black text-slate-900 tracking-tighter hover:text-emerald-600 transition-colors">
            Abbey <span className="text-emerald-500">1.5</span>
          </a>
          <div className="flex items-center gap-4">
            <span className="text-xs font-bold text-slate-400 hidden sm:block">{user?.email}</span>
            <button onClick={signOut}
              className="text-xs font-bold text-slate-500 hover:text-slate-900 transition-colors px-4 py-2 rounded-xl border border-slate-200 hover:bg-slate-50">
              Salir
            </button>
          </div>
        </header>
      )}

      {appState === 'idle' && (
        <div className="max-w-4xl mx-auto px-6 py-12">
          <div className="mb-12 text-center">
            <h1 className="text-4xl font-black text-slate-900 tracking-tight mb-4">
              Inteligencia de Márgenes Logísticos para el AMBA
            </h1>
            <p className="text-lg text-slate-600 font-medium mb-6">
              Auditoría financiera y optimización de rutas basada en Unit Economics reales.
            </p>
            <p className="text-sm text-slate-500 max-w-2xl mx-auto leading-relaxed">
              Abbey cruza simultáneamente exposición al riesgo, topología urbana (peajes) y fricción operativa.
              Subí tu Excel de despachos, ajustá la matriz financiera y obtené un plan auditable CFO-Grade en segundos.
            </p>
          </div>

          <div className="flex flex-col gap-10">
            <AdvancedConfig onChange={setAdvConfig} />
            <ExcelUploader onParsed={handleParsed} />
          </div>
        </div>
      )}
      {appState === 'loading' && <LoadingState startTime={loadingStart} />}
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
      {appState === 'error' && <ErrorState message={errorMessage} onRetry={handleRetry} />}
    </div>
  );
}