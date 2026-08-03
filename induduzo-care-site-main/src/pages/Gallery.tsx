import React, { useMemo, useState } from 'react';
import galleryData from '../data/gallery.json';
import { useLanguage } from '@/lib/i18n';

type GalleryItem = {
  id: string;
  title_en: string;
  title_zu: string;
  category: 'Our Work' | 'Services' | 'Happy Families' | string;
  image: string;
  alt_en: string;
  alt_zu: string;
  shortDescription_en?: string;
  shortDescription_zu?: string;
};

const CATEGORIES = ['All', 'Our Work', 'Services', 'Happy Families'] as const;

export default function Gallery() {
  const { language, t } = useLanguage();
  const items = galleryData as GalleryItem[];
  const [active, setActive] = useState<(typeof CATEGORIES)[number]>('All');

  const filtered = useMemo(() => {
    if (active === 'All') return items;
    return items.filter((it) => it.category === active);
  }, [active, items]);

  return (
    <main style={{ padding: '2rem 1rem', maxWidth: 1200, margin: '0 auto' }}>
      <header style={{ marginBottom: '1rem' }}>
        <h1 style={{ margin: 0 }}>{t('gallery_title')}</h1>
        <p style={{ marginTop: '.5rem', color: '#555' }}>
          {t('gallery_subtitle')}
        </p>
      </header>

      <nav aria-label={t('gallery_title')} style={{ display: 'flex', gap: '.5rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
        {CATEGORIES.map((cat) => (
          <button
            key={cat}
            onClick={() => setActive(cat)}
            aria-pressed={(active === cat).toString()}
            style={{
              padding: '.5rem .75rem',
              borderRadius: '999px',
              border: '1px solid #ddd',
              background: active === cat ? '#111' : '#fff',
              color: active === cat ? '#fff' : '#111',
              cursor: 'pointer'
            }}
          >
            {cat === 'All'
              ? t('gallery_filter_all')
              : cat === 'Our Work'
                ? t('gallery_filter_work')
                : cat === 'Services'
                  ? t('gallery_filter_services')
                  : t('gallery_filter_families')}
          </button>
        ))}
      </nav>

      <section
        aria-live="polite"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
          gap: '1rem'
        }}
      >
        {filtered.map((card) => (
          <article key={card.id} style={{ border: '1px solid #eee', borderRadius: 8, overflow: 'hidden' }}>
            <img
              src={card.image} // TODO: replace with real path under src/assets/
              alt={language === 'en' ? card.alt_en : card.alt_zu}
              loading="lazy"
              style={{ width: '100%', height: 180, objectFit: 'cover' }}
            />
            <div style={{ padding: '0.75rem 0.75rem 1rem' }}>
              <h3 style={{ margin: '0 0 .25rem' }}>
                {language === 'en' ? card.title_en : card.title_zu}
              </h3>
              {(language === 'en' ? card.shortDescription_en : card.shortDescription_zu) && (
                <p style={{ margin: 0, color: '#555', fontSize: 14 }}>
                  {language === 'en' ? card.shortDescription_en : card.shortDescription_zu}
                </p>
              )}
              <p style={{ margin: '.5rem 0 0', fontSize: 12, color: '#777' }}>
                {card.category === 'Our Work'
                  ? t('gallery_filter_work')
                  : card.category === 'Services'
                    ? t('gallery_filter_services')
                    : t('gallery_filter_families')}
              </p>
            </div>
          </article>
        ))}
      </section>
    </main>
  );
}
