const { test } = require('node:test');
const assert = require('node:assert/strict');
const { parseJson, stringify, numberToken } = require('../out/json');
test('scientific integer and float tokens survive editor rendering exactly', () => {
    const raw = '{"large":9223372036854775807,"small":-9223372036854775808,"negative_zero":-0.0,"float":1.2345678901234567,"exponent":1e20,"array":[1e-20,0.0,9007199254740991]}';
    const value = parseJson(raw);
    assert.equal(value.large, 9223372036854775807n);
    assert.equal(value.small, -9223372036854775808n);
    assert.equal(Object.isFrozen(value), true);
    assert.equal(Object.isFrozen(value.array), true);
    assert.equal(numberToken(value, 'negative_zero'), '-0.0');
    assert.equal(stringify(value), raw);
    assert.match(stringify(value, 2), /"large": 9223372036854775807/);
    assert.equal(stringify(value.large), '9223372036854775807');
});
test('nonfinite and oversized numeric representations refuse before expensive conversion', () => {
    assert.throws(() => parseJson('{"n":1e9999}'));
    assert.throws(() => parseJson('{"n":' + '1'.repeat(129) + '}'));
});
