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
    const finalPayload = {
      ...payload,
      departure_time: advConfig?.departure_time,
      stochastic_mode: advConfig?.stochastic_mode || false,
      economic_profile: {
        precio_gasoil_ars: advConfig?.precio_gasoil_ars,
        tarifa_hora_ars: advConfig?.tarifa_hora_ars,
        consumo_l_por_km: advConfig?.consumo_l_por_km,
        dolar_mep_ars: advConfig?.dolar_mep,
        factor_friccion: advConfig?.factor_friccion
      }
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
          archetypes: finalPayload.allowed_archetypes,
          response_json: response,
          shift_start_minutes: finalPayload.shift_start_minutes,
          departure_time: finalPayload.departure_time,
          costo_total_ars: summary.total_expected_cost || 0,
          distancia_km: firstPlan.assignments?.[0]?.cost_breakdown?.distancia_km || 0
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
    <div id="app-page" className="min-h-screen bg-gray-50">
      {appState !== 'map' && (
        <header className="w-full px-6 py-4 border-b border-gray-200 bg-white flex items-center justify-between">
          <a href="/" className="text-lg font-bold text-[#0F172A] tracking-tight hover:text-[#1F9D6A] transition-colors">
            Abbey
          </a>
          <div className="flex items-center gap-4">
            <span className="text-xs text-gray-400 hidden sm:block">{user?.email}</span>
            <button onClick={signOut}
              className="text-xs text-gray-400 hover:text-gray-700 transition-colors px-3 py-1.5 rounded-lg border border-gray-200 hover:border-gray-300">
              Salir
            </button>
          </div>
        </header>
      )}

      {appState === 'idle' && (
        <div className="flex flex-col gap-4">
          <AdvancedConfig onChange={setAdvConfig} />
          <ExcelUploader onParsed={handleParsed} />
        </div>
      )}
      {appState === 'loading' && <LoadingState startTime={loadingStart} />}
      {appState === 'result' && (
        <ChatResult fleetResponse={fleetResponse} parsedPayload={parsedPayload} onSelectArchetype={handleSelectArchetype} />
      )}
      {appState === 'map' && (
        <MapView fleetResponse={fleetResponse} selectedArchetype={selectedArchetype}
          parsedPayload={parsedPayload} onChangeArchetype={handleChangeArchetype} onBack={handleBackToResults} />
      )}
      {appState === 'error' && <ErrorState message={errorMessage} onRetry={handleRetry} />}
    </div>
  );
}
