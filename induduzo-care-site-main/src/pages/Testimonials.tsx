import React, { useMemo, useState } from 'react';

import { useLanguage } from '@/lib/i18n';
import { CONTACT_EMAIL_LINK } from '@/lib/contact';
import testimonialsData from '../data/testimonials.json';

interface Testimonial {
  id: string;
  name?: string;
  relation_en: string;
  relation_zu: string;
  message_en: string;
  message_zu: string;
  rating: number;
  dateISO?: string;
}

export default function Testimonials() {
  const { language, t } = useLanguage();
  const approved = testimonialsData as Testimonial[];
  const [form, setForm] = useState({ name: '', relation: '', rating: 5, message: '' });
  const [submitted, setSubmitted] = useState(false);

  const averageRating = useMemo(() => {
    if (!approved.length) return 0;
    const sum = approved.reduce((acc, testimonial) => acc + (Number(testimonial.rating) || 0), 0);
    return Math.round((sum / approved.length) * 10) / 10;
  }, [approved]);

  const onSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!form.relation.trim() || !form.message.trim() || !form.rating) {
      alert(t('testimonial_validation'));
      return;
    }

    const displayName = form.name || t('anonymous');
    const subject = encodeURIComponent(
      language === 'en'
        ? `Testimonial submission from ${displayName}`
        : `Ubufakazi obuvela ku-${displayName}`,
    );
    const body = encodeURIComponent(
      [
        `${language === 'en' ? 'Name' : 'Igama'}: ${displayName}`,
        `${language === 'en' ? 'Relation' : 'Ubudlelwano'}: ${form.relation}`,
        `${language === 'en' ? 'Rating' : 'Isilinganiso'}: ${form.rating}/5`,
        '',
        form.message,
      ].join('\n'),
    );

    window.location.href = `${CONTACT_EMAIL_LINK}?subject=${subject}&body=${body}`;
    setSubmitted(true);
    setForm({ name: '', relation: '', rating: 5, message: '' });
  };

  return (
    <main style={{ padding: '2rem 1rem', maxWidth: 1100, margin: '0 auto' }}>
      <header style={{ marginBottom: '1rem' }}>
        <h1 style={{ margin: 0 }}>{t('nav_testimonials')}</h1>
        <p style={{ marginTop: '.5rem', color: '#555' }}>
          {t('average_rating')}: <strong>{averageRating}</strong> / 5
        </p>
      </header>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '2rem' }}>
        <section aria-label={t('testimonials_title')} style={{ display: 'grid', gap: '1rem' }}>
          {approved.map((testimonial) => (
            <article key={testimonial.id} style={{ border: '1px solid #eee', borderRadius: 8, padding: '1rem' }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '.5rem', alignItems: 'center', justifyContent: 'space-between' }}>
                <h3 style={{ margin: 0 }}>
                  {testimonial.name && testimonial.name !== '—' ? testimonial.name : t('anonymous')}
                </h3>
                <span aria-label={`${testimonial.rating} out of 5 stars`} title={`${testimonial.rating} out of 5`}>
                  {'★'.repeat(testimonial.rating)}{'☆'.repeat(5 - testimonial.rating)}
                </span>
              </div>
              <p style={{ margin: '.25rem 0 0', color: '#777', fontSize: 14 }}>
                {language === 'en' ? testimonial.relation_en : testimonial.relation_zu}
              </p>
              <p style={{ marginTop: '.5rem' }}>
                {language === 'en' ? testimonial.message_en : testimonial.message_zu}
              </p>
              {testimonial.dateISO && (
                <p style={{ margin: 0, fontSize: 12, color: '#999' }}>
                  {new Date(testimonial.dateISO).toLocaleDateString(language === 'en' ? 'en-ZA' : 'zu-ZA')}
                </p>
              )}
            </article>
          ))}
        </section>

        <section aria-label={t('add_your_story')} style={{ border: '1px solid #eee', borderRadius: 8, padding: '1rem' }}>
          <h2 style={{ marginTop: 0 }}>{t('add_your_story')}</h2>
          <p style={{ marginTop: '.25rem', color: '#555' }}>{t('testimonial_notice')}</p>

          <form onSubmit={onSubmit} style={{ display: 'grid', gap: '0.75rem' }}>
            <label>
              <span>{t('form_name')} ({language === 'en' ? 'optional' : 'uyazikhethela'})</span>
              <input
                type="text"
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                placeholder="e.g., Nomsa M."
                style={{ width: '100%', padding: '.5rem', border: '1px solid #ddd', borderRadius: 6 }}
              />
            </label>

            <label>
              <span>{t('relation_to_client')} *</span>
              <input
                type="text"
                value={form.relation}
                onChange={(event) => setForm({ ...form, relation: event.target.value })}
                placeholder={t('relation_placeholder')}
                required
                style={{ width: '100%', padding: '.5rem', border: '1px solid #ddd', borderRadius: 6 }}
              />
            </label>

            <label>
              <span>{t('star_rating')} *</span>
              <input
                type="number"
                min={1}
                max={5}
                value={form.rating}
                onChange={(event) => setForm({ ...form, rating: Math.max(1, Math.min(5, Number(event.target.value))) })}
                required
                style={{ width: '100%', padding: '.5rem', border: '1px solid #ddd', borderRadius: 6 }}
              />
            </label>

            <label>
              <span>{t('form_message')} *</span>
              <textarea
                value={form.message}
                onChange={(event) => setForm({ ...form, message: event.target.value })}
                placeholder={t('testimonial_message_placeholder')}
                required
                rows={5}
                style={{ width: '100%', padding: '.5rem', border: '1px solid #ddd', borderRadius: 6 }}
              />
            </label>

            <div>
              <button
                type="submit"
                aria-label={t('testimonial_submit')}
                style={{ padding: '.6rem 1rem', borderRadius: 6, border: '1px solid #111', background: '#111', color: '#fff', cursor: 'pointer' }}
              >
                {t('testimonial_submit')}
              </button>
              {submitted && (
                <span style={{ marginLeft: '.75rem', color: 'green' }}>{t('testimonial_email_opened')}</span>
              )}
            </div>
          </form>
        </section>
      </div>
    </main>
  );
}
