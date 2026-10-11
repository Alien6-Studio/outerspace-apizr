/* Exercise the vendor call sites affected by the reviewed security overrides. */
const assert = require('node:assert/strict');
const { createRequire } = require('node:module');
const { readFileSync, existsSync } = require('node:fs');
const { join, dirname } = require('node:path');

function installedVersion(vendorRequire, dependency) {
  let directory = dirname(vendorRequire.resolve(dependency));
  while (dirname(directory) !== directory) {
    const metadata = join(directory, 'package.json');
    if (existsSync(metadata)) {
      const value = JSON.parse(readFileSync(metadata));
      if (value.name === dependency) return value.version;
    }
    directory = dirname(directory);
  }
  throw new Error(`No installed metadata for ${dependency}`);
}

async function main() {
  const manifest = require('./package.json');
  const checked = {};
  for (const [parent, dependencies] of Object.entries(manifest.overrides)) {
    const split = parent.lastIndexOf('@');
    const name = parent.slice(0, split);
    const expected = parent.slice(split + 1);
    const parentFile = join(__dirname, 'node_modules', name, 'package.json');
    assert.equal(JSON.parse(readFileSync(parentFile)).version, expected);
    const vendorRequire = createRequire(parentFile);
    for (const [dependency, version] of Object.entries(dependencies)) {
      assert.equal(installedVersion(vendorRequire, dependency), version);
      checked[`${parent} -> ${dependency}`] = version;
    }
  }

  // Bruno's actual callback parser: BOM, Unicode, quoted delimiters and blanks.
  const cliRequire = createRequire(join(__dirname, 'node_modules/@usebruno/cli/package.json'));
  const { parseCSV } = cliRequire('./src/utils/filesystem.js');
  assert.deepEqual(await parseCSV('\uFEFFname,value\n"café,one", 2\n\n'), [
    { name: 'café,one', value: '2' }
  ]);

  const jsRequire = createRequire(join(__dirname, 'node_modules/@usebruno/js/package.json'));
  const uuid = jsRequire('uuid');
  assert.equal(uuid.version(uuid.v4()), 4);
  assert.equal(uuid.version(uuid.v7()), 7);
  const id = uuid.v5('apizr', uuid.v5.DNS);
  assert.equal(uuid.stringify(uuid.parse(id)), id);
  assert.throws(() => uuid.v5('apizr', uuid.v5.DNS, new Uint8Array(1)));
  assert.equal(jsRequire('handlebars').compile('{{name}}')({ name: '<apizr>' }), '&lt;apizr&gt;');

  // Faker 10 is ESM; Node 22.22.2 must support Bruno's CommonJS interop.
  const requestsRequire = createRequire(join(__dirname, 'node_modules/@usebruno/requests/package.json'));
  const { faker } = requestsRequire('@faker-js/faker');
  faker.seed(45);
  assert.equal(typeof faker.number.int({ min: 1, max: 3 }), 'number');
  assert.equal(typeof faker.number.float({ min: 0, max: 1000, precision: 0.01 }), 'number');
  assert.equal(typeof faker.datatype.boolean(), 'boolean');
  assert.equal(typeof faker.lorem.word(), 'string');
  assert.equal(typeof faker.string.alpha({ length: { min: 5, max: 10 } }), 'string');

  const value = { name: 'café', values: [0, false, ''] };
  const yaml = jsRequire('yaml');
  assert.deepEqual(yaml.parse(yaml.stringify(value)), value);
  const jsYaml = cliRequire('js-yaml');
  assert.deepEqual(jsYaml.load(jsYaml.dump(value)), value);
  const FormData = cliRequire('form-data');
  const form = new FormData();
  form.append('name', 'apizr');
  assert.match(form.getHeaders()['content-type'], /^multipart\/form-data; boundary=/);
  assert.match(form.getBuffer().toString(), /name="name"/);
  assert.equal(typeof cliRequire('axios').create().request, 'function');

  // Real HTTP/YAML/CLI execution is qualified separately by client_collections_proof.py.
  process.stdout.write(JSON.stringify({ node: process.version, overrides: checked, compatibility: 'passed' }, null, 2) + '\n');
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
