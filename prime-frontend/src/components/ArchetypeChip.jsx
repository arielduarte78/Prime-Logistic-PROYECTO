//prime-frontend/src/components/ArchetypeChip.jsx
export default function ArchetypeChip({ archetype, onClick, isSelected }) {
  return (
    <button
      id={`chip-${archetype.key}`}
      onClick={() => onClick(archetype.key)}
      className="group relative flex items-center gap-2 px-5 py-2.5 rounded-full border-2 transition-all duration-300 cursor-pointer select-none"
      style={{
        borderColor: isSelected ? archetype.color : 'rgba(255,255,255,0.15)',
        backgroundColor: isSelected ? `${archetype.color}18` : 'transparent',
        boxShadow: isSelected ? `0 0 20px ${archetype.color}30` : 'none',
      }}
    >
      <span className="text-lg">{archetype.emoji}</span>
      <span
        className="text-sm font-medium transition-colors"
        style={{ color: isSelected ? archetype.color : '#d4d4d8' }}
      >
        {archetype.label}
      </span>
      {isSelected && (
        <span
          className="absolute -top-1 -right-1 w-3 h-3 rounded-full animate-pulse"
          style={{ backgroundColor: archetype.color }}
        />
      )}
    </button>
  );
}
