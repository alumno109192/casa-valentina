import type { CapacitorConfig } from '@capacitor/cli';

/**
 * Empaquetado Android de la app del TPV (proyecto `pos` del workspace).
 *
 * `webDir` apunta a la compilación de producción de `pos`, así que antes de
 * `npx cap sync` hay que ejecutar `npm run build:pos`.
 *
 * El backend vive en el mini-PC del local y se sirve por HTTP en la red
 * interna. Android bloquea el tráfico en claro por defecto, de ahí
 * `androidScheme: 'http'` y la excepción de red del manifiesto.
 */
const config: CapacitorConfig = {
  appId: 'es.casavalentina.tpv',
  appName: 'TPV Casa Valentina',
  webDir: 'dist/pos/browser',
  android: {
    allowMixedContent: true,
  },
  server: {
    androidScheme: 'http',
  },
};

export default config;
