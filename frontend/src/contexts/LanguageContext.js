import { createContext, useContext, useState } from 'react';
import { translations } from '../lib/i18n';

const LanguageContext = createContext(null);

export function LanguageProvider({ children }) {
  const [language, setLanguage] = useState(() => localStorage.getItem('mf_lang') || 'de');

  const t = (key) => translations[language]?.[key] || translations.en[key] || key;

  const toggleLanguage = () => {
    const next = language === 'en' ? 'de' : 'en';
    setLanguage(next);
    localStorage.setItem('mf_lang', next);
  };

  const setLang = (lang) => {
    setLanguage(lang);
    localStorage.setItem('mf_lang', lang);
  };

  return (
    <LanguageContext.Provider value={{ language, setLanguage: setLang, t, toggleLanguage }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() { return useContext(LanguageContext); }
