//prime-frontend/src/pages/Landing.jsx
import { useNavigate } from 'react-router-dom';
import { supabase } from '../services/supabaseClient';
import ExcelTemplateButton from '../components/ExcelTemplateButton';

export default function Landing() {
  const navigate = useNavigate();

  const handleComenzar = async () => {
    const { data: { session } } = await supabase.auth.getSession();
    if (session) {
      navigate('/app');
    } else {
      navigate('/login');
    }
  };

  return (
    <div id="landing-page" className="min-h-screen bg-white flex flex-col">
      {/* ─── NAV ─── */}
      <nav className="w-full px-6 py-4 border-b border-gray-200 flex items-center justify-between sticky top-0 bg-white/90 backdrop-blur-sm z-50">
        <span className="text-2xl font-bold text-[#0F172A] tracking-tight">Abbey</span>
        <button onClick={handleComenzar}
          className="px-5 py-2 bg-[#1F9D6A] hover:bg-[#178a5c] text-white rounded-lg font-medium text-sm transition-colors">
          Comenzar →
        </button>
      </nav>

      {/* ─── HERO ─── */}
      <section className="flex flex-col items-center text-center px-6 py-32 bg-white">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-green-50 border border-green-200 mb-8">
          <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
          <span className="text-xs font-medium text-green-700">Abbey 1.5 — Motor logístico para el AMBA</span>
        </div>
        <h1 className="text-5xl md:text-6xl font-extrabold tracking-tight text-gray-900 max-w-3xl mx-auto leading-tight">
          Optimización logística para flotas en Buenos Aires
        </h1>
        <p className="text-xl text-gray-500 max-w-2xl mx-auto mt-6 leading-relaxed">
          Abbey evalúa simultáneamente seguridad vial, costos operativos y ventanas horarias.
          Subí tu Excel, elegí tu estrategia, recibí el plan en segundos.
        </p>
        <div className="flex items-center gap-6 mt-10">
          <button id="cta-comenzar" onClick={handleComenzar}
            className="group px-8 py-4 bg-[#1F9D6A] hover:bg-[#178a5c] rounded-xl text-white font-semibold text-lg transition-all duration-300 shadow-lg shadow-green-500/20 hover:shadow-green-500/30 hover:scale-[1.02]">
            Comenzar<span className="inline-block ml-2 transition-transform group-hover:translate-x-1">→</span>
          </button>
          <ExcelTemplateButton className="text-gray-500 hover:text-[#1F9D6A]" />
        </div>
      </section>

      {/* ─── CÓMO FUNCIONA ─── */}
      <section className="bg-gray-50 py-24 px-6">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-3xl font-bold text-gray-900 text-center">Cómo funciona</h2>
          <p className="text-gray-500 text-center mt-3 mb-16">Tres pasos. Sin configuración.</p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <StepCard number="01" title="Subís tu Excel" description="Dos hojas: vehículos con origen y capacidad, destinos con coordenadas y demanda." />
            <StepCard number="02" title="Abbey evalúa" description="El motor analiza seguridad vial, costos de peajes, combustible y ventanas horarias simultáneamente." />
            <StepCard number="03" title="Elegís tu estrategia" description="Ruta más segura, menor costo o equilibrio óptimo. Cada una con mapa, cronograma y PDF para el chofer." />
          </div>
        </div>
      </section>

      {/* ─── EVIDENCIA ─── */}
      <section className="bg-white py-20 px-6">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl font-bold text-gray-900 text-center mb-14">El motor</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <MetricCard value="185.112" label="Nodos en el grafo vial del AMBA" />
            <MetricCard value="4" label="Estrategias simultáneas por corrida" />
            <MetricCard value="< 30s" label="Tiempo promedio de cálculo" />
          </div>
        </div>
      </section>

      {/* ─── CTA FINAL ─── */}
      <section className="bg-[#0F172A] py-24 px-6 text-center">
        <h2 className="text-4xl font-bold text-white mb-4">Empezá a optimizar hoy</h2>
        <p className="text-gray-400 text-lg mb-10">Sin instalación. Sin configuración. Solo subí tu Excel.</p>
        <button onClick={handleComenzar}
          className="px-8 py-4 bg-white text-[#0F172A] font-bold rounded-xl text-lg hover:bg-gray-100 transition-colors">
          Abrir Abbey →
        </button>
      </section>

      {/* ─── FOOTER ─── */}
      <footer className="w-full px-6 py-8 border-t border-gray-200 bg-white">
        <div className="max-w-5xl mx-auto grid grid-cols-1 md:grid-cols-3 items-center gap-4">
          <div>
            <span className="font-bold text-[#0F172A]">Abbey</span>
            <p className="text-sm text-gray-400 mt-1">© 2026 Aphira</p>
          </div>
          <p className="text-sm text-gray-400 text-center">Motor Abbey 1.5</p>
          <div className="flex justify-end"><ExcelTemplateButton /></div>
        </div>
      </footer>
    </div>
  );
}

function StepCard({ number, title, description }) {
  return (
    <div className="bg-white border border-gray-200 rounded-2xl p-8 shadow-sm">
      <span className="text-5xl font-black text-[#1F9D6A] opacity-80">{number}</span>
      <h3 className="text-lg font-semibold text-gray-900 mt-4 mb-2">{title}</h3>
      <p className="text-sm text-gray-500 leading-relaxed">{description}</p>
    </div>
  );
}

function MetricCard({ value, label }) {
  return (
    <div className="text-center p-8 rounded-2xl border border-gray-200 shadow-sm">
      <p className="text-5xl font-black text-gray-900">{value}</p>
      <p className="text-sm text-gray-500 mt-2">{label}</p>
    </div>
  );
}
