/**
 * Producción: el mini-PC del local.
 *
 * La IP fija del mini-PC en la red del establecimiento. Si se cambia el
 * router, hay que actualizarla aquí y volver a compilar el APK, así que
 * conviene reservar la IP por DHCP en el router.
 */
export const environment = {
  production: true,
  apiBaseUrl: 'http://192.168.1.50:8000',
};
