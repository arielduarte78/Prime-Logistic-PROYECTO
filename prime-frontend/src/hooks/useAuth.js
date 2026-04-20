//prime-frontend/src/hooks/useAuth.js
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { supabase } from '../services/supabaseClient';

export function useAuth() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isGuest, setIsGuest] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    // Check guest state first
    const guestFlag = localStorage.getItem('isGuest') === 'true';
    setIsGuest(guestFlag);

    if (guestFlag) {
      // Guest users get a synthetic user object for display purposes
      setUser({ email: 'Invitado', id: null });
      setLoading(false);
      return;
    }

    supabase.auth.getSession().then(({ data: { session } }) => {
      setUser(session?.user ?? null);
      setLoading(false);
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ?? null);
    });

    return () => subscription.unsubscribe();
  }, []);

  const signOut = async () => {
    // Always clear guest flag
    localStorage.removeItem('isGuest');
    setIsGuest(false);

    // Only call supabase signOut for real users
    if (!isGuest) {
      await supabase.auth.signOut();
    }

    navigate('/login', { replace: true });
  };

  return { user, loading, isGuest, signOut };
}
