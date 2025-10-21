import React, { useMemo, useState } from 'react';
// @ts-ignore — Vite supports JSON imports
import testimonialsData from '../data/testimonials.json';

interface Testimonial {
  id: string;
  name?: string;
  relation: string;
  message: string;
  rating: number; // 1-5
  dateISO?: string;
}

export default function Testimonials() {
  const approved = testimonialsData as Testimonial[];
  const [form, setForm] = useState({ name: '', relation: '', rating: 5, message: '' });
  const [submitted, setSubmitted] = useState(false);

  const averageRating = useMemo(() => {
    if (!approved.length) return 0;
    const sum = approved.reduce((acc, t) => acc + (Number(t.rating) || 0), 0);
    return Math.round((sum / approved.length) * 10) / 10;
  }, [approved]);

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.relation.trim() || !form.message.trim() || !form.rating) {
      alert('Please provide relation, rating, and a message.');
      return;
    }
    // For now, just log — no API/database
    console.log('Testimonial submission:', form);
    setSubmitted(true);
    setForm({ name: '', relation: '', rating: 5, message: '' });
  };

  return (
    <main style={{ padding: '2rem 1rem', maxWidth: 1100, margin: '0 auto' }}>
      <header style={{ marginBottom: '1rem' }}>
        <h1 style={{ margin: 0 }}>Testimonials</h1>
        <p style={{ marginTop: '.5rem', color: '#555' }}>
          Average rating: <strong>{averageRating}</strong> / 5
        </p>
      </header>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '2rem' }}>
        {/* List */}
        <section aria-label="Approved testimonials" style={{ display: 'grid', gap: '1rem' }}>
          {approved.map((t) => (
            <article key={t.id} style={{ border: '1px solid #eee', borderRadius: 8, padding: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <h3 style={{ margin: 0 }}>{t.name && t.name !== '—' ? t.name : 'Anonymous'}</h3>
                <span aria-label={`${t.rating} out of 5 stars`} title={`${t.rating} out of 5`}>
                  {'★'.repeat(t.rating)}{'☆'.repeat(5 - t.rating)}
                </span>
              </div>
              <p style={{ margin: '.25rem 0 0', color: '#777', fontSize: 14 }}>{t.relation}</p>
              <p style={{ marginTop: '.5rem' }}>{t.message}</p>
              {t.dateISO && (
                <p style={{ margin: 0, fontSize: 12, color: '#999' }}>{new Date(t.dateISO).toLocaleDateString()}</p>
              )}
            </article>
          ))}
        </section>

        {/* Form */}
        <section aria-label="Submit testimonial" style={{ border: '1px solid #eee', borderRadius: 8, padding: '1rem' }}>
          <h2 style={{ marginTop: 0 }}>Add your story</h2>
          <p style={{ marginTop: '.25rem', color: '#555' }}>
            By submitting, you consent to us publishing your testimonial (name optional),
            and storing it for moderation and display on this website.
          </p>

          <form onSubmit={onSubmit} style={{ display: 'grid', gap: '0.75rem' }}>
            <label>
              <span>Name (optional)</span>
              <input
                type="text"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="e.g., Nomsa M."
                style={{ width: '100%', padding: '.5rem', border: '1px solid #ddd', borderRadius: 6 }}
              />
            </label>

            <label>
              <span>Relation to client *</span>
              <input
                type="text"
                value={form.relation}
                onChange={(e) => setForm({ ...form, relation: e.target.value })}
                placeholder="Family member, friend, etc."
                required
                style={{ width: '100%', padding: '.5rem', border: '1px solid #ddd', borderRadius: 6 }}
              />
            </label>

            <label>
              <span>Star rating (1–5) *</span>
              <input
                type="number"
                min={1}
                max={5}
                value={form.rating}
                onChange={(e) => setForm({ ...form, rating: Math.max(1, Math.min(5, Number(e.target.value))) })}
                required
                style={{ width: '100%', padding: '.5rem', border: '1px solid #ddd', borderRadius: 6 }}
              />
            </label>

            <label>
              <span>Message *</span>
              <textarea
                value={form.message}
                onChange={(e) => setForm({ ...form, message: e.target.value })}
                placeholder="Share your experience…"
                required
                rows={5}
                style={{ width: '100%', padding: '.5rem', border: '1px solid #ddd', borderRadius: 6 }}
              />
            </label>

            <div>
              <button type="submit" aria-label="Submit testimonial" style={{ padding: '.6rem 1rem', borderRadius: 6, border: '1px solid #111', background: '#111', color: '#fff', cursor: 'pointer' }}>
                Submit
              </button>
              {submitted && (
                <span style={{ marginLeft: '.75rem', color: 'green' }}>Thank you! Your message has been received.</span>
              )}
            </div>
          </form>
        </section>
      </div>
    </main>
  );
}
