//prime-frontend/src/pages/LoginPage.jsx
import { useState } from 'react';
import { supabase } from '../services/supabaseClient';
import { useNavigate } from 'react-router-dom';

export default function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [companyName, setCompanyName] = useState('');
  const [isSignUp, setIsSignUp] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  const handleGoogle = async () => {
    setLoading(true);
    setError('');
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: `${window.location.origin}/app` },
    });
    if (error) setError(error.message);
    setLoading(false);
  };

  const handleEmailAuth = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setSuccessMsg('');

    if (isSignUp) {
      if (password !== confirmPassword) {
        setError('Las contraseñas no coinciden.');
        setLoading(false);
        return;
      }
      if (password.length < 6) {
        setError('La contraseña debe tener al menos 6 caracteres.');
        setLoading(false);
        return;
      }
      const { error } = await supabase.auth.signUp({
        email,
        password,
        options: {
          data: { company_name: companyName || undefined },
        },
      });
      if (error) {
        setError(error.message);
      } else {
        setSuccessMsg('Revisá tu email para confirmar tu cuenta.');
      }
      setLoading(false);
      return;
    }

    // Login
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) {
      setError(error.message);
      setLoading(false);
    } else {
      navigate('/app');
    }
  };

  return (
    <div className="min-h-screen bg-white flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-10">
          <h1 className="text-3xl font-extrabold text-[#0F172A] tracking-tight">Abbey</h1>
          <p className="text-gray-500 text-sm mt-2">
            {isSignUp ? 'Creá tu cuenta para empezar a optimizar' : 'Motor logístico para flotas en Buenos Aires'}
          </p>
        </div>

        {/* Google OAuth */}
        <button onClick={handleGoogle} disabled={loading}
          className="w-full flex items-center justify-center gap-3 px-4 py-3 rounded-xl border-2 border-gray-200 hover:border-gray-300 bg-white hover:bg-gray-50 transition-all text-gray-700 font-medium text-sm mb-6">
          <svg className="w-5 h-5" viewBox="0 0 24 24">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/>
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
          </svg>
          {isSignUp ? 'Registrarse con Google' : 'Continuar con Google'}
        </button>

        {/* Divider */}
        <div className="flex items-center gap-3 mb-6">
          <div className="flex-1 h-px bg-gray-200" />
          <span className="text-xs text-gray-400">o con email</span>
          <div className="flex-1 h-px bg-gray-200" />
        </div>

        {/* Form */}
        <form onSubmit={handleEmailAuth} className="space-y-3">
          {/* Sign-up only: Company name */}
          {isSignUp && (
            <input type="text" placeholder="Nombre de empresa" value={companyName}
              onChange={e => setCompanyName(e.target.value)}
              className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-[#1F9D6A] focus:ring-2 focus:ring-[#1F9D6A]/20 outline-none text-sm text-gray-900 transition-all" />
          )}

          <input type="email" placeholder="tu@empresa.com" value={email}
            onChange={e => setEmail(e.target.value)}
            className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-[#1F9D6A] focus:ring-2 focus:ring-[#1F9D6A]/20 outline-none text-sm text-gray-900 transition-all" />

          <input type="password" placeholder="Contraseña" value={password}
            onChange={e => setPassword(e.target.value)}
            className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-[#1F9D6A] focus:ring-2 focus:ring-[#1F9D6A]/20 outline-none text-sm text-gray-900 transition-all" />

          {/* Sign-up only: Confirm password */}
          {isSignUp && (
            <input type="password" placeholder="Confirmar contraseña" value={confirmPassword}
              onChange={e => setConfirmPassword(e.target.value)}
              className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-[#1F9D6A] focus:ring-2 focus:ring-[#1F9D6A]/20 outline-none text-sm text-gray-900 transition-all" />
          )}

          {error && (
            <div className="px-4 py-3 rounded-lg bg-red-50 border border-red-200 text-red-600 text-xs">{error}</div>
          )}
          {successMsg && (
            <div className="px-4 py-3 rounded-lg bg-green-50 border border-green-200 text-[#1F9D6A] text-xs">{successMsg}</div>
          )}

          <button type="submit" disabled={loading || !email || !password}
            className={`w-full py-3 rounded-xl font-semibold text-sm transition-all disabled:opacity-50 ${
              isSignUp
                ? 'bg-[#1F9D6A] hover:bg-[#178a5c] text-white'
                : 'bg-[#0F172A] hover:bg-[#1e293b] text-white'
            }`}>
            {loading ? 'Procesando...' : isSignUp ? 'Crear cuenta' : 'Iniciar sesión'}
          </button>
        </form>

        {/* Toggle */}
        <p className="text-center text-xs text-gray-400 mt-6">
          {isSignUp ? '¿Ya tenés cuenta?' : '¿No tenés cuenta?'}{' '}
          <button onClick={() => { setIsSignUp(!isSignUp); setError(''); setSuccessMsg(''); }}
            className="text-[#1F9D6A] font-medium hover:underline">
            {isSignUp ? 'Iniciá sesión' : 'Registrate'}
          </button>
        </p>

        <p className="text-center text-xs text-gray-300 mt-10">© 2026 Aphira</p>
      </div>
    </div>
  );
}
