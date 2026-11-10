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
    const { user, isGuest, signOut } = useAuth();
    const [appState, setAppState] = useState('idle');
    const [fleetResponse, setFleetResponse] = useState(null);
    const [selectedArchetype, setSelectedArchetype] = useState(null);
    const [errorMessage, setErrorMessage] = useState('');
    const [parsedPayload, setParsedPayload] = useState(null);
    const [loadingStart, setLoadingStart] = useState(null);
    const [advConfig, setAdvConfig] = useState(null);
    const [loadingStatus, setLoadingStatus] = useState(null);

    const handleParsed = async (payload) => {
        const [h, m] = (advConfig?.departure_time || "08:00").split(':').map(Number);
        const shiftMin = h * 60 + m;

        // 🔥 EL FIX ESTÁ ACÁ: Pasamos el JSON anidado de la configuración financiera directo al Backend
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
        setLoadingStatus(null);

        try {
            const response = await sendFleetRequest(finalPayload, { onStatus: setLoadingStatus });
            setFleetResponse(response);
            setAppState('result');

            // M4: Guardar en Historial (Supabase) — Solo para usuarios autenticados
            if (user && !isGuest) {
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
            {/* ─── Guest Banner ─── */}
            {isGuest && (
                <div className="w-full bg-gradient-to-r from-amber-500 via-amber-400 to-amber-500 text-amber-950 px-4 py-2.5 text-center text-sm font-semibold shadow-sm flex items-center justify-center gap-2">
                    <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
                    </svg>
                    <span>Modo Invitado — Los datos no se guardarán al cerrar sesión.</span>
                    <button
                        onClick={() => window.location.href = '/login'}
                        className="ml-3 px-3 py-0.5 bg-amber-950/10 hover:bg-amber-950/20 rounded-md text-xs font-bold transition-colors"
                    >
                        Crear cuenta
                    </button>
                </div>
            )}

            {appState !== 'map' && (
                <header className="w-full px-6 py-4 border-b border-slate-200 bg-white flex items-center justify-between shadow-sm">
                    <a href="/" className="text-xl font-black text-slate-900 tracking-tighter hover:text-emerald-600 transition-colors">
                        Abbey <span className="text-emerald-500">1.5</span>
                    </a>
                    <div className="flex items-center gap-4">
                        {isGuest ? (
                            <span className="text-xs font-bold text-amber-600 bg-amber-50 px-3 py-1 rounded-full border border-amber-200">
                                👤 Invitado
                            </span>
                        ) : (
                            <span className="text-xs font-bold text-slate-400 hidden sm:block">{user?.email}</span>
                        )}
                        <button onClick={signOut}
                            className="text-xs font-bold text-slate-500 hover:text-slate-900 transition-colors px-4 py-2 rounded-xl border border-slate-200 hover:bg-slate-50">
                            Salir
                        </button>
                    </div>
                </header>
            )}

            {appState === 'idle' && (
                <div className="max-w-4xl mx-auto px-6 py-12">
                    <div className="mb-12 text-center flex flex-col items-center">
                        <span className="inline-block px-3 py-1 mb-6 text-[10px] font-black uppercase tracking-[0.2em] text-emerald-600 bg-emerald-50 border border-emerald-200 rounded-full shadow-sm">
                            ⚡ Simulación sobre tu operación real
                        </span>
                        <h1 className="text-4xl md:text-5xl font-black text-slate-900 tracking-tight mb-4">
                            Cargá tu operación
                        </h1>
                        <p className="text-base md:text-lg text-slate-500 max-w-2xl mx-auto leading-relaxed font-medium">
                            Subí tu planilla con flota y destinos. Abbey utiliza tus datos para calcular costos, rutas y tiempos de trabajo. Ajustá tus parámetros y obtené resultados listos para analizar y ejecutar.
                        </p>
                    </div>

                    <div className="flex flex-col gap-10">
                        <AdvancedConfig onChange={setAdvConfig} />
                        <ExcelUploader onParsed={handleParsed} />
                    </div>
                </div>
            )}
            {appState === 'loading' && <LoadingState startTime={loadingStart} status={loadingStatus} />}
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