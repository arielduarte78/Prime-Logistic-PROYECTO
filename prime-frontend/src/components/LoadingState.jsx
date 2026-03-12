//prime-frontend/src/components/LoadingState.jsx
import { useEffect, useState } from 'react';

export default function LoadingState({ startTime }) {
  const [dots, setDots] = useState('');
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const dotsInterval = setInterval(() => {
      setDots((prev) => (prev.length >= 3 ? '' : prev + '.'));
    }, 500);

    const elapsedInterval = setInterval(() => {
      if (startTime) {
        setElapsed(Math.floor((Date.now() - startTime) / 1000));
      }
    }, 1000);

    return () => {
      clearInterval(dotsInterval);
      clearInterval(elapsedInterval);
    };
  }, [startTime]);

  return (
    <div id="loading-state" className="flex flex-col items-center justify-center min-h-[60vh] gap-8">
      {/* Spinner */}
      <div className="relative">
        <div className="w-16 h-16 border-4 border-zinc-700 rounded-full" />
        <div className="absolute top-0 left-0 w-16 h-16 border-4 border-transparent border-t-blue-500 rounded-full animate-spin" />
      </div>

      {/* Animated text */}
      <div className="text-center">
        <p className="text-lg text-zinc-300 font-medium">
          Calculando rutas óptimas{dots}
        </p>
        <p className="text-sm text-zinc-500 mt-2">
          {elapsed}s transcurridos
        </p>
      </div>

      {/* Long-wait notice */}
      {elapsed > 30 && (
        <p className="text-sm text-amber-400/80 max-w-sm text-center animate-pulse">
          El motor está procesando una solicitud compleja. Puede tomar hasta 60 segundos.
        </p>
      )}
    </div>
  );
}
