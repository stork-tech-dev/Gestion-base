// Punto de entrada para `node --test backend/tests_js/`: en Node 22 un
// directorio pasado a --test se carga como módulo (este index.js), así que
// acá se importan todos los *.test.mjs de la carpeta.
const { readdirSync } = require('node:fs');
const { join } = require('node:path');
const { pathToFileURL } = require('node:url');

for (const archivo of readdirSync(__dirname).filter((f) => f.endsWith('.test.mjs')).sort()) {
  import(pathToFileURL(join(__dirname, archivo)).href);
}
