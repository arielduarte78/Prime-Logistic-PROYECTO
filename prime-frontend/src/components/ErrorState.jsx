//prime-frontend/src/components/ErrorState.jsx
export default function ErrorState({ message, onRetry }) {
  return (
    <div id="error-state" className="flex flex-col items-center justify-center min-h-[60vh] gap-6">
      <div className="w-20 h-20 rounded-full bg-red-500/10 flex items-center justify-center">
        <svg className="w-10 h-10 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"
          />
        </svg>
      </div>

      <div className="text-center max-w-md">
        <h3 className="text-lg font-semibold text-white mb-2">Algo salió mal</h3>
        <p className="text-zinc-400 text-sm leading-relaxed">{message}</p>
      </div>

      <button
        id="retry-button"
        onClick={onRetry}
        className="px-6 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-medium transition-colors text-sm"
      >
        Intentar de nuevo
      </button>
    </div>
  );
}
