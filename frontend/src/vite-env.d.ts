/// <reference types="vite/client" />

interface ImportMetaEnv {
  /**
   * Optional. Blank falls back to the keyless Google Maps embed — see
   * `src/lib/location.ts`. Public by design, so restrict it by referrer.
   */
  readonly VITE_GOOGLE_MAPS_API_KEY?: string;
}
