//prime-frontend/src/pages/Landing.jsx
import { useNavigate } from 'react-router-dom';
import ExcelTemplateButton from '../components/ExcelTemplateButton';

export default function Landing() {
  const navigate = useNavigate();

  return (
    <div id="landing-page" className="min-h-screen bg-zinc-950 flex flex-col">
      {/* Header */}
      <header className="w-full px-6 py-5">
        <span className="text-xl font-bold text-white tracking-tight">[NOMBRE]</span>
      </header>

      {/* Hero */}
      <main className="flex-1 flex flex-col items-center justify-center px-6 py-16 max-w-5xl mx-auto text-center">
        <div className="mb-4">
          <span className="inline-block px-3 py-1 rounded-full text-xs font-medium bg-blue-500/10 text-blue-400 border border-blue-500/20">
            Motor V1.4 — Buenos Aires Metro
          </span>
        </div>

        <h1 className="text-5xl md:text-6xl font-extrabold text-white leading-tight mb-6">
          Optimizá tus rutas de{' '}
          <span className="bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-blue-600">
            entrega en segundos
          </span>
        </h1>

        <p className="text-lg text-zinc-400 max-w-2xl leading-relaxed mb-10">
          [NOMBRE] calcula simultáneamente las rutas más seguras, las de menor costo
          y el equilibrio óptimo para tu flota. Subí tu Excel y recibí el plan de
          ruteo en menos de 30 segundos.
        </p>

        <button
          id="cta-comenzar"
          onClick={() => navigate('/app')}
          className="group px-8 py-4 bg-blue-600 hover:bg-blue-500 rounded-xl text-white font-semibold text-lg transition-all duration-300 shadow-lg shadow-blue-500/20 hover:shadow-blue-500/30 hover:scale-[1.02]"
        >
          Comenzar
          <span className="inline-block ml-2 transition-transform group-hover:translate-x-1">→</span>
        </button>

        {/* Benefits */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mt-20 w-full">
          <BenefitCard
            icon="🛡️"
            title="Seguridad vial"
            description="Evalúa zonas de riesgo con datos reales de siniestros y genera rutas que minimizan la exposición."
          />
          <BenefitCard
            icon="💰"
            title="Costo operativo"
            description="Optimiza combustible, peajes y horas de conducción. Cada ruta tiene costo calculado en pesos."
          />
          <BenefitCard
            icon="⚖️"
            title="Estrategias múltiples"
            description="No una ruta: cuatro estrategias simultáneas. Vos elegís el equilibrio entre costo y seguridad."
          />
        </div>
      </main>

      {/* Footer */}
      <footer className="w-full px-6 py-6 border-t border-zinc-900 flex flex-col md:flex-row items-center justify-between gap-4">
        <ExcelTemplateButton />
        <p className="text-xs text-zinc-600">
          © 2026 [NOMBRE]. Producto en desarrollo.
        </p>
      </footer>
    </div>
  );
}

function BenefitCard({ icon, title, description }) {
  return (
    <div className="p-6 rounded-2xl bg-zinc-900/50 border border-zinc-800/50 hover:border-zinc-700/50 transition-colors text-center">
      <div className="text-4xl mb-4">{icon}</div>
      <h3 className="text-lg font-semibold text-white mb-2">{title}</h3>
      <p className="text-sm text-zinc-400 leading-relaxed">{description}</p>
    </div>
  );
}
