import React from 'react';
import founder from '../data/founder.json';
import { useLanguage } from '@/lib/i18n';

export default function Founder() {
  const { language, t } = useLanguage();
  const story = language === 'en' ? founder.longFormStory_en : founder.longFormStory_zu;

  return (
    <main style={{ padding: '2rem 1rem', maxWidth: 900, margin: '0 auto' }}>
      <header style={{ display: 'grid', gap: '1rem', justifyItems: 'center', textAlign: 'center', marginBottom: '1rem' }}>
        <img
          src={founder.photo} // TODO: replace with real path under src/assets/
          alt={`Portrait of ${founder.name}`}
          style={{ width: 160, height: 160, objectFit: 'cover', borderRadius: '50%', border: '2px solid #eee' }}
        />
        <div>
          <h1 style={{ margin: 0 }}>{founder.name}</h1>
          <p style={{ marginTop: '.25rem', color: '#555' }}>
            {language === 'en' ? founder.tagline_en : founder.tagline_zu}
          </p>
        </div>
      </header>

      <section aria-label={t('founder_story')} style={{ display: 'grid', gap: '1rem', marginBottom: '2rem' }}>
        {story.map((para: string, idx: number) => (
          <p key={idx} style={{ margin: 0 }}>{para}</p>
        ))}
      </section>

      <section aria-label={t('journey_milestones')} style={{ borderTop: '1px solid #eee', paddingTop: '1rem' }}>
        <h2>{t('journey_milestones')}</h2>
        <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: '.5rem' }}>
          {founder.milestones.map((m, idx: number) => (
            <li key={idx} style={{ display: 'flex', gap: '.5rem' }}>
              <strong style={{ minWidth: 64 }}>{m.year}</strong>
              <span>{language === 'en' ? m.text_en : m.text_zu}</span>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
