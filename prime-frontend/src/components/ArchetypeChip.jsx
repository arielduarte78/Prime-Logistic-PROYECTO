//prime-frontend/src/components/ArchetypeChip.jsx
export default function ArchetypeChip({ archetype, onClick, isSelected }) {
  return (
    <button
      id={`chip-${archetype.key}`}
      onClick={() => onClick(archetype.key)}
      className="group relative flex items-center gap-2 px-5 py-2.5 rounded-full border-2 transition-all duration-300 cursor-pointer select-none bg-white"
      style={{
        borderColor: isSelected ? archetype.color : '#E5E7EB',
        backgroundColor: isSelected ? `${archetype.color}12` : 'white',
        boxShadow: isSelected ? `0 0 16px ${archetype.color}25` : '0 1px 2px rgba(0,0,0,0.05)',
      }}
    >
      <span className="text-lg">{archetype.emoji}</span>
      <span
        className="text-sm font-medium transition-colors"
        style={{ color: isSelected ? archetype.color : '#374151' }}
      >
        {archetype.label}
      </span>
      {isSelected && (
        <span className="absolute -top-1 -right-1 w-3 h-3 rounded-full animate-pulse" style={{ backgroundColor: archetype.color }} />
      )}
    </button>
  );
}
