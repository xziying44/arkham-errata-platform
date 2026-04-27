import assert from 'node:assert/strict';

const {
  buildErrataDiff,
  buildJsonStringDecorations,
} = await import('../src/components/workbench/errataDiff.ts');

const original = {
  name: '重返黑色王座',
  subtitle: '原始副标题',
  traits: ['场景', '远古'],
  body: '每位调查员抽取1张遭遇牌。',
  flavor: '',
  encounter_group: 'core',
};

const modified = {
  name: '重返黑色王座',
  subtitle: '勘误副标题',
  traits: ['场景', '远古'],
  body: '每位调查员抽取1张遭遇牌。然后放置1个线索。',
  flavor: '王座上的阴影正在注视你。',
  encounter_group: 'return_to_core',
};

const diff = buildErrataDiff(original, modified);
assert.equal(diff.changedFields.length, 4);
assert.equal(diff.changedFieldKeys.has('subtitle'), true);
assert.equal(diff.changedFieldKeys.has('body'), true);
assert.equal(diff.changedFieldKeys.has('flavor'), true);
assert.equal(diff.changedFieldKeys.has('encounter_group'), true);

const bodyDiff = diff.changedFields.find((item) => item.key === 'body');
assert.deepEqual(bodyDiff?.segments, [
  { kind: 'equal', text: '每位调查员抽取1张遭遇牌。' },
  { kind: 'added', text: '然后放置1个线索。' },
]);

const json = JSON.stringify(modified, null, 2);
const decorations = buildJsonStringDecorations(json, diff.changedFields);
const bodyDecoration = decorations.find((item) => item.key === 'body' && item.kind === 'added');
assert(bodyDecoration, 'body 新增片段需要有字符级高亮');
assert.equal(json.slice(bodyDecoration.startOffset, bodyDecoration.endOffset), '然后放置1个线索。');

const escapedDiff = buildErrataDiff(
  { body: '第一行' },
  { body: '第一行\n第二行' },
);
const escapedJson = JSON.stringify({ body: '第一行\n第二行' }, null, 2);
const escapedDecorations = buildJsonStringDecorations(escapedJson, escapedDiff.changedFields);
const escapedBodyDecoration = escapedDecorations.find((item) => item.key === 'body' && item.kind === 'added');
assert(escapedBodyDecoration, '转义换行的新增片段需要有字符级高亮');
assert.equal(escapedJson.slice(escapedBodyDecoration.startOffset, escapedBodyDecoration.endOffset), '\\n第二行');

const pictureOnlyDiff = buildErrataDiff(
  { name: '图片卡', picture_base64: 'data:image/png;base64,AAA' },
  { name: '图片卡', picture_base64: 'data:image/png;base64,BBB' },
);
assert.equal(pictureOnlyDiff.changedFields.length, 0, 'picture_base64 差异不应显示为勘误内容');

const pictureWithBodyDiff = buildErrataDiff(
  { body: '旧正文', picture_base64: 'data:image/png;base64,AAA' },
  { body: '新正文', picture_base64: 'data:image/png;base64,BBB' },
);
assert.deepEqual(pictureWithBodyDiff.changedFields.map((item) => item.key), ['body']);

console.log('勘误差异计算检查通过');
