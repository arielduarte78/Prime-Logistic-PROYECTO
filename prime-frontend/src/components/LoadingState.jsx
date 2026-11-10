//prime-frontend/src/components/LoadingState.jsx
import { useEffect, useState } from 'react';

export default function LoadingState({ startTime, status }) {
  const [dots, setDots] = useState('');
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const dotsInterval = setInterval(() => {
      setDots((prev) => (prev.length >= 3 ? '' : prev + '.'));
    }, 500);
    const elapsedInterval = setInterval(() => {
      if (startTime) setElapsed(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);
    return () => { clearInterval(dotsInterval); clearInterval(elapsedInterval); };
  }, [startTime]);

  return (
    <div id="loading-state" className="flex flex-col items-center justify-center min-h-[60vh] gap-8 bg-gray-50">
      <div className="relative">
        <div className="w-16 h-16 border-4 border-gray-200 rounded-full" />
        <div className="absolute top-0 left-0 w-16 h-16 border-4 border-transparent border-t-[#1F9D6A] rounded-full animate-spin" />
      </div>
      <div className="text-center">
        <p className="text-lg text-gray-700 font-medium">Calculando rutas óptimas{dots}</p>
        <p className="text-sm text-gray-400 mt-2">{elapsed}s transcurridos</p>
      </div>
      {status && (
        <p className="text-sm text-blue-700 bg-blue-50 rounded-lg px-4 py-2 max-w-sm text-center">{status}</p>
      )}
      {!status && elapsed > 20 && (
        <p className="text-sm text-amber-600 bg-amber-50 rounded-lg px-4 py-2 max-w-sm text-center">
          Un cálculo suele tardar 30 segundos. Si hay otras solicitudes antes que la tuya,
          espera su turno: puede tardar hasta 2 minutos. No cierres la página.
        </p>
      )}
    </div>
  );
}
