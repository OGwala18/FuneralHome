import React from 'react';
// @ts-ignore — Vite supports JSON imports
import founder from '../data/founder.json';

export default function Founder() {
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
          <p style={{ marginTop: '.25rem', color: '#555' }}>{founder.tagline}</p>
        </div>
      </header>

      <section aria-label="Founder story" style={{ display: 'grid', gap: '1rem', marginBottom: '2rem' }}>
        {founder.longFormStory.map((para: string, idx: number) => (
          <p key={idx} style={{ margin: 0 }}>{para}</p>
        ))}
      </section>

      <section aria-label="Milestones" style={{ borderTop: '1px solid #eee', paddingTop: '1rem' }}>
        <h2>Journey Milestones</h2>
        <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: '.5rem' }}>
          {founder.milestones.map((m: { year: string; text: string }, idx: number) => (
            <li key={idx} style={{ display: 'flex', gap: '.5rem' }}>
              <strong style={{ minWidth: 64 }}>{m.year}</strong>
              <span>{m.text}</span>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
