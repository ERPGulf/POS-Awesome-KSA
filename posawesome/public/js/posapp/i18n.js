// import { createI18n } from 'vue-i18n';
// import enPOS from '../locales/en/pos.json';
// import arPOS from '../locales/ar/pos.json';

// const savedLang = localStorage.getItem('lang') || 'en';

// const i18n = createI18n({
//   legacy: false,
//   locale: savedLang,
//   fallbackLocale: 'en',
//   globalInjection: true,
//   messages: {
//     en: { ...enPOS },
//     ar: { ...arPOS }
//   }
// });

// export default i18n;


import { createI18n } from 'vue-i18n'

import enPOS from './locales/en/pos.json'
import arPOS from './locales/ar/pos.json'

const savedLang = localStorage.getItem('lang') || 'en'

const messages = {
  en: { ...enPOS },
  ar: { ...arPOS }
}

const i18n = createI18n({
  legacy: false,
  locale: savedLang,
  fallbackLocale: 'en',
  globalInjection: true,
  messages
})

export default i18n
